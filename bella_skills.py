#!/usr/bin/env python3
"""
Bella's hands: coding + analysis skills that run on the phone (Termux).

Everything here operates on files the user owns, inside ~/bella-workspace.
Destructive shell patterns are blocked outright — she is a partner, not a hazard.

Public entry point: try_skill(text, title) -> spoken string or None.
"""

import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request

WORKSPACE = os.path.expanduser("~/bella-workspace")
MEMORY_FILE = os.path.expanduser("~/.bella_memory.json")
OUTPUT_CAP = 4000       # max chars kept from any single command/file output
VOICE_INLINE = 300      # below this, output is spoken inline; above, saved to file

# ---------------------------------------------------------------- safety

# Shell patterns Bella will never run, no matter how nicely you ask.
# Voice-dictated commands are easy to fat-finger, so this list errs hard
# on the side of caution. skill_run_python scans code against it too.
BLOCKED = [
    r":\(\)\s*\{\s*:\|\:&\s*\}\s*;",   # fork bomb
    r"\brm\s+-[a-z]*r",                # rm -r* : recursive delete is too easy to fat-finger by voice
    r"\bmkfs\b",
    r"\bdd\b",                          # dd does block-level writes; one wrong of= and a disk is gone
    r">\s*/dev/(sd|hd|mmc|nvme|loop)",
    r">\s*/proc/sys",                  # kernel parameter tampering
    r"\bchmod\s+(-R\s+)?777\s+/",      # chmod 777 on root
    r"\bchown\s+(-R\s+)?.*\s+/",       # chown on root
    r"\b(fdisk|parted|cfdisk|sfdisk)\b",  # partition editors
    r"(^|\s)(su|sudu|sudo|doas)(\s|$)",
    r"(^|\s)(shutdown|reboot|halt|poweroff)(\s|$)",
    r"\b(iptables|nft|ufw)\b",         # firewall changes can lock him out or open holes
    r"\b(useradd|userdel|usermod|passwd|chsh)\b",  # account manipulation
    r"\bnc\b.*\s-e\s|\bncat\b.*\s-e\s",  # netcat reverse shells
    r"(curl|wget)[^\|]*\|\s*(sh|bash|python3?)\b",  # pipe-to-shell downloads
    r"\bmv\s+.*\s+/( |$)",
]

MAX_WRITE = 2_000_000  # 2 MB cap on voice-dictated file writes
AUDIT_LOG = os.path.expanduser("~/.bella_audit.log")


def _audit(kind, detail):
    """Append-only trail of everything Bella runs or writes. Never read back
    into chat unasked — it's for his eyes when something needs explaining."""
    try:
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{kind}] {detail[:400]}\n")
    except OSError:
        pass

UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 10) Bella/1.0"}


def _ensure_workspace():
    os.makedirs(WORKSPACE, exist_ok=True)


def safe_path(p):
    """Resolve a user-given path strictly inside the workspace."""
    _ensure_workspace()
    p = p.strip().strip("'\"")
    full = os.path.abspath(os.path.join(WORKSPACE, p))
    if not (full == WORKSPACE or full.startswith(WORKSPACE + os.sep)):
        raise ValueError("Outside the workspace, sir — I keep file work in ~/bella-workspace.")
    return full


def _save_output(full_text):
    """Stash long output in the workspace; return the filename."""
    _ensure_workspace()
    name = "bella-output.txt"
    with open(os.path.join(WORKSPACE, name), "w", encoding="utf-8") as f:
        f.write(full_text)
    return name


def _wrap(spoken, full):
    """Decide whether long output is spoken inline or saved to a file."""
    if not full:
        return spoken
    if len(full) <= VOICE_INLINE:
        return f"{spoken} {full}"
    name = _save_output(full)
    return f"{spoken} The full output is saved in {name}."


# ---------------------------------------------------------------- files

def skill_write_file(path, content):
    try:
        full = safe_path(path)
    except ValueError as e:
        return str(e), None
    if len(content) > MAX_WRITE:
        _audit("blocked-write", f"{path} ({len(content)} chars over cap)")
        return ("That's too big a file to write by voice, sir — over 2 MB. "
                "Break it into pieces?"), None
    os.makedirs(os.path.dirname(full) or WORKSPACE, exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)
    _audit("write", f"{path} ({len(content)} chars)")
    return f"Wrote that to {os.path.basename(path)}, sir.", None


def skill_read_file(path):
    try:
        full = safe_path(path)
    except ValueError as e:
        return str(e), None
    if not os.path.isfile(full):
        return f"I don't see a file called {path} in the workspace, sir.", None
    with open(full, encoding="utf-8", errors="replace") as f:
        content = f.read()
    if len(content) > OUTPUT_CAP:
        content = content[:OUTPUT_CAP] + "\n...[truncated]"
    return f"Here's {os.path.basename(path)}, sir.", content


def skill_list(path=""):
    try:
        full = safe_path(path) if path else WORKSPACE
    except ValueError as e:
        return str(e), None
    if not os.path.isdir(full):
        return f"{path or 'The workspace'} isn't a folder, sir.", None
    items = sorted(os.listdir(full))
    if not items:
        return "The workspace is empty, sir.", None
    shown = ", ".join(items[:25])
    extra = f" and {len(items) - 25} more" if len(items) > 25 else ""
    return f"In the workspace, sir: {shown}{extra}.", None


# ---------------------------------------------------------------- code execution

def skill_run(cmd):
    for pat in BLOCKED:
        if re.search(pat, cmd):
            _audit("blocked-shell", cmd)
            return "That command is on my never-do list, sir. I won't run it.", None
    _audit("shell", cmd)
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True,
                              text=True, timeout=60, cwd=WORKSPACE)
    except subprocess.TimeoutExpired:
        return "That ran past 60 seconds, sir, so I stopped it.", None
    except Exception as e:
        return f"Couldn't run that, sir: {e}", None
    out = (proc.stdout or "")
    if proc.stderr:
        out += ("\n" if out else "") + "[stderr]\n" + proc.stderr
    out = out.strip() or f"(no output, exit code {proc.returncode})"
    if len(out) > OUTPUT_CAP:
        out = out[:OUTPUT_CAP] + "\n...[truncated]"
    return f"Done, sir — exit code {proc.returncode}.", out


def skill_run_python(code):
    # The snippet runs through a shell, so scan the CODE itself too —
    # otherwise "run python: os.system('rm -rf ~')" would sail right past
    # the filter above.
    for pat in BLOCKED:
        if re.search(pat, code):
            _audit("blocked-python", code)
            return "That code trips my never-do list, sir. I won't run it.", None
    _ensure_workspace()
    snippet = os.path.join(WORKSPACE, "_snippet.py")
    with open(snippet, "w", encoding="utf-8") as f:
        f.write(code)
    spoken, full = skill_run("python3 _snippet.py")
    try:
        os.remove(snippet)
    except OSError:
        pass
    return spoken, full


# ---------------------------------------------------------------- analysis / reverse engineering
# For software he owns or has permission to test. Detection and inspection
# only — no cracking, no bypassing protections.

def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _strings_sample(path, limit=20):
    out = []
    try:
        with open(path, "rb") as f:
            data = f.read(200000)
    except OSError:
        return out
    for m in re.finditer(rb"[\x20-\x7e]{5,}", data):
        out.append(m.group().decode("ascii", "replace"))
        if len(out) >= limit:
            break
    return out


def skill_analyze_file(path):
    try:
        full = safe_path(path)
    except ValueError as e:
        return str(e), None
    if not os.path.isfile(full):
        return f"I don't see a file called {path}, sir.", None
    size = os.path.getsize(full)
    mime, _ = mimetypes.guess_type(full)
    detail = ""
    if shutil.which("file"):
        try:
            detail = subprocess.run(["file", "-b", full], capture_output=True,
                                    text=True, timeout=10).stdout.strip()
        except Exception:
            pass
    lines = [f"Analysis of {os.path.basename(path)}, sir:",
             f"Size: {size:,} bytes.",
             f"SHA-256: {_sha256(full)}."]
    if detail:
        lines.append(f"Type: {detail}")
    elif mime:
        lines.append(f"Type: {mime}")
    strings = _strings_sample(full)
    if strings:
        lines.append("Readable text inside starts with: " + " | ".join(strings[:8]))
    return " ".join(lines[:4]), "\n".join(lines)


def skill_apk_info(path):
    try:
        full = safe_path(path)
    except ValueError as e:
        return str(e), None
    if not os.path.isfile(full):
        return f"I don't see {path} in the workspace, sir.", None
    if not path.lower().endswith(".apk"):
        return "That doesn't look like an APK, sir — I'll run a general analysis instead.", skill_analyze_file(path)[1]
    lines = [f"APK: {os.path.basename(path)} ({os.path.getsize(full):,} bytes)",
             f"SHA-256: {_sha256(full)}"]
    if shutil.which("aapt"):
        try:
            badging = subprocess.run(["aapt", "dump", "badging", full],
                                     capture_output=True, text=True, timeout=30).stdout
            for line in badging.splitlines():
                if line.startswith(("package:", "launchable-activity:", "uses-permission:")):
                    lines.append(line.strip())
        except Exception:
            pass
    elif shutil.which("apktool"):
        lines.append("apktool is installed — say 'decompile' and name the APK to unpack it.")
    else:
        lines.append("Tip: install apktool (pkg install apktool) and I can unpack APKs for deeper inspection.")
    if shutil.which("unzip"):
        try:
            listing = subprocess.run(["unzip", "-l", full], capture_output=True,
                                     text=True, timeout=30).stdout
            names = [l.split()[-1] for l in listing.splitlines()[3:-2] if l.strip()]
            interesting = [n for n in names if n.endswith((".dex", ".so", "AndroidManifest.xml"))][:15]
            if interesting:
                lines.append("Key contents: " + ", ".join(interesting))
        except Exception:
            pass
    return f"Analyzed {os.path.basename(path)}, sir.", "\n".join(lines)


def skill_decompile_apk(path):
    try:
        full = safe_path(path)
    except ValueError as e:
        return str(e), None
    if not os.path.isfile(full):
        return f"I don't see {path} in the workspace, sir.", None
    if not shutil.which("apktool"):
        return ("I need apktool for that, sir — install it with: pkg install apktool.", None)
    outdir = full + ".unpacked"
    spoken, full_out = skill_run(f"apktool d -f -o {shutil.quote(outdir)} {shutil.quote(full)}")
    if "exit code 0" in spoken:
        return (f"Unpacked {os.path.basename(path)} into {os.path.basename(outdir)}, sir. "
                "Manifest, resources and smali are in there."), full_out
    return spoken, full_out


# ---------------------------------------------------------------- web

def _http_get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ctype = r.headers.get("Content-Type", "")
        raw = r.read(300000)
    text = raw.decode("utf-8", "replace")
    if "html" in ctype:
        text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
    return text


def skill_fetch(url):
    url = url.strip().strip("'\"")
    if not re.match(r"^https?://", url):
        url = "https://" + url
    try:
        text = _http_get(url)
    except Exception as e:
        return f"Couldn't fetch that page, sir: {e}", None
    if len(text) > OUTPUT_CAP:
        text = text[:OUTPUT_CAP] + "\n...[truncated]"
    host = urllib.parse.urlparse(url).netloc
    return f"Here's what {host} says, sir.", text


def skill_web_search(query):
    url = "https://lite.duckduckgo.com/lite/?q=" + urllib.parse.quote_plus(query)
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read(300000).decode("utf-8", "replace")
    except Exception as e:
        return f"Search failed, sir: {e}", None
    if "anomaly" in html.lower() and "result" not in html.lower():
        return ("The search engine is blocking automated queries right now, sir. "
                "Try again in a bit."), None
    results = re.findall(r'<a rel="nofollow" href="([^"]+)"[^>]*>(.*?)</a>', html)
    if not results:
        return f"No results for '{query}', sir.", None
    lines = []
    for href, title in results[:5]:
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", title)).strip()
        m = re.search(r"uddg=([^&]+)", href)
        link = urllib.parse.unquote(m.group(1)) if m else href
        link = link.replace("&amp;", "&")
        lines.append(f"- {title}\n  {link}")
    return f"Top results for '{query}', sir.", "\n".join(lines)


# ---------------------------------------------------------------- memory (notes)

def _load_mem():
    try:
        with open(MEMORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"notes": []}


def _save_mem(mem):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(mem, f, indent=2)


def skill_note(text):
    mem = _load_mem()
    mem["notes"].append({"t": time.strftime("%Y-%m-%d %H:%M"), "text": text.strip()})
    _save_mem(mem)
    return "Noted, sir. I won't forget it.", None


def skill_notes():
    mem = _load_mem()
    notes = mem.get("notes", [])
    if not notes:
        return "My notebook is empty, sir.", None
    lines = [f"{i+1}. [{n['t']}] {n['text']}" for i, n in enumerate(notes[-15:])]
    return f"{len(notes)} notes on file, sir.", "\n".join(lines)


def skill_forget_note(idx):
    mem = _load_mem()
    notes = mem.get("notes", [])
    try:
        n = notes.pop(int(idx) - 1)
    except (ValueError, IndexError):
        return "I don't have a note with that number, sir.", None
    _save_mem(mem)
    return f"Forgot note {idx}, sir.", None


# ---------------------------------------------------------------- dispatcher

SKILLS_HELP = (
    "As your partner I can also: run shell commands ('run ...'), run Python "
    "('run python ...'), read and write files in my workspace ('read file X', "
    "'write file X: ...', 'list files'), analyze files and APKs you own "
    "('analyze file X', 'analyze APK X'), fetch web pages ('fetch ...'), "
    "search the web ('search for ...'), and take notes ('note that ...', "
    "'read my notes'). I never run destructive commands."
)

_PATTERNS = [
    (re.compile(r"^(?:take a |make a )?note (?:that )?(.+)", re.I),
     lambda m: skill_note(m.group(1))),
    (re.compile(r"^(?:read|show|list)(?: my)? notes$", re.I),
     lambda m: skill_notes()),
    (re.compile(r"^forget note (\d+)$", re.I),
     lambda m: skill_forget_note(m.group(1))),
    (re.compile(r"^(?:run|execute) python (.+)", re.I | re.S),
     lambda m: skill_run_python(m.group(1).strip())),
    (re.compile(r"^(?:run|execute)(?: command)? (.+)", re.I | re.S),
     lambda m: skill_run(m.group(1).strip())),
    (re.compile(r"^write file (\S+?)\s*:\s*(.+)", re.I | re.S),
     lambda m: skill_write_file(m.group(1), m.group(2).strip())),
    (re.compile(r"^(?:read|show me|show)(?: the)? file (.+)", re.I),
     lambda m: skill_read_file(m.group(1))),
    (re.compile(r"^(?:list|show)(?: the)? files(?: in (.+))?$", re.I),
     lambda m: skill_list((m.group(1) or "").strip())),
    (re.compile(r"^decompile (?:the )?(?:apk )?(.+)", re.I),
     lambda m: skill_decompile_apk(m.group(1).strip())),
    (re.compile(r"^analyze (?:the )?(?:file |apk )?(.+)", re.I),
     lambda m: (skill_apk_info(m.group(1).strip())
                if m.group(1).strip().lower().endswith(".apk")
                else skill_analyze_file(m.group(1).strip()))),
    (re.compile(r"^fetch (?:url )?(\S+)", re.I),
     lambda m: skill_fetch(m.group(1))),
    (re.compile(r"^(?:search(?: the web)? for|look up|google) (.+)", re.I),
     lambda m: skill_web_search(m.group(1).strip())),
]


# --- cybersecurity / IoT toolkit (optional module) ---------------------------
try:
    from bella_netsec import NETSEC_PATTERNS, NETSEC_HELP
    _PATTERNS.extend(NETSEC_PATTERNS)
    SKILLS_HELP += " " + NETSEC_HELP
except Exception:
    pass


# --- GitHub repo skills (optional module) ------------------------------------
try:
    from bella_github import GH_PATTERNS, GH_HELP
    _PATTERNS.extend(GH_PATTERNS)
    SKILLS_HELP += " " + GH_HELP
except Exception:
    pass


def try_skill(text, title="sir"):
    """Try to handle `text` as a skill command.

    Returns the spoken response string, or None if no skill matched.
    """
    for pattern, handler in _PATTERNS:
        m = pattern.match(text.strip())
        if m:
            try:
                spoken, full = handler(m)
            except Exception as e:
                spoken, full = f"Something went wrong with that, {title}: {e}", None
            if title != "sir":
                spoken = spoken.replace("sir", title)
            return _wrap(spoken, full)
    return None
