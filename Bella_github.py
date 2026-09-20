#!/usr/bin/env python3
"""
Bella's GitHub key: repo skills authenticated with the user's own
GitHub OAuth/PAT token (e.g. a 90-day token).

Lets her list repos, read files, and commit files — so she can work on
his code directly. Read/write only; no repo deletion, no settings changes.

Token: GITHUB_TOKEN env var only — never in config or code.
Keep the token scoped to the minimum it needs (repo).
"""

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from bella_skills import _save_output, VOICE_INLINE

UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 10) Bella/1.0"}
API = "https://api.github.com"

_token = None


def set_token(tok):
    global _token
    _token = tok or None


def _headers():
    return {**UA, "Authorization": f"Bearer {_token}",
            "Accept": "application/vnd.github+json"}


def _gh(path, method="GET", data=None):
    """Call the GitHub REST API. Returns (ok, payload_or_error)."""
    if not _token:
        return False, ("No GitHub token in the environment, sir — "
                       "set GITHUB_TOKEN and restart me.")
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(API + path, data=body,
                                 headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return True, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
            msg = err.get("message", "")
        except Exception:
            msg = ""
        if e.code == 401:
            return False, ("GitHub rejected the token, sir — it looks expired "
                           "or invalid. Time for a fresh one.")
        if e.code == 404:
            return False, f"Not found on GitHub, sir. {msg}"
        if e.code == 403 and "rate limit" in msg.lower():
            return False, "GitHub rate limit hit, sir — I'll try again later."
        return False, f"GitHub said HTTP {e.code}, sir. {msg}"
    except Exception as e:
        return False, f"Couldn't reach GitHub, sir: {e}"


def _wrap(spoken, full):
    if not full:
        return spoken
    if len(full) <= VOICE_INLINE:
        return f"{spoken} {full}"
    name = _save_output(full)
    return f"{spoken} Full details saved in {name}."


# ---------------------------------------------------------------- skills

def gh_repos():
    ok, data = _gh("/user/repos?per_page=100&sort=updated")
    if not ok:
        return data, None
    if not data:
        return "No repos on your GitHub account, sir.", None
    lines = [f"- {r['full_name']}{' (private)' if r['private'] else ''}"
             + (f" — {r['description'][:60]}" if r.get("description") else "")
             for r in data]
    names = ", ".join(r["full_name"] for r in data[:8])
    extra = f" and {len(data) - 8} more" if len(data) > 8 else ""
    return (f"{len(data)} repos, sir: {names}{extra}.",
            "\n".join(lines))


def gh_list(repo, path=""):
    repo = repo.strip()
    if "/" not in repo:
        return "Say it as owner/repo, sir — like edwardparkinson-star/bella.", None
    q = f"/repos/{repo}/contents/{path.strip('/')}" if path else f"/repos/{repo}/contents"
    ok, data = _gh(q)
    if not ok:
        return data, None
    if isinstance(data, dict):  # single file
        return f"{path} is a file, sir — say 'github read {repo} {path}'.", None
    lines = [f"- {e['name']}{'/' if e['type'] == 'dir' else ''}" for e in data]
    return (f"{len(lines)} items in {repo}, sir.", "\n".join(lines))


def gh_read(repo, path):
    repo, path = repo.strip(), path.strip().strip("'\"")
    if "/" not in repo:
        return "Say it as owner/repo, sir.", None
    ok, data = _gh(f"/repos/{repo}/contents/{path}")
    if not ok:
        return data, None
    if isinstance(data, list) or data.get("type") == "dir":
        return f"{path} is a folder, sir — say 'github list {repo} {path}'.", None
    if data.get("encoding") != "base64":
        return "That file isn't plain text, sir — I can't read it aloud.", None
    try:
        text = base64.b64decode(data["content"]).decode("utf-8", "replace")
    except Exception:
        return "Couldn't decode that file, sir.", None
    if len(text) > 4000:
        text = text[:4000] + "\n...[truncated]"
    return f"Here's {path} from {repo}, sir.", text


def gh_write(repo, path, content):
    repo, path = repo.strip(), path.strip().strip("'\"")
    if "/" not in repo:
        return "Say it as owner/repo, sir.", None
    # Fetch current SHA if the file exists (required for updates).
    ok, cur = _gh(f"/repos/{repo}/contents/{path}")
    sha = cur.get("sha") if ok and isinstance(cur, dict) else None
    payload = {"message": f"Update {path} via Bella",
               "content": base64.b64encode(content.encode()).decode()}
    if sha:
        payload["sha"] = sha
    ok, data = _gh(f"/repos/{repo}/contents/{path}", method="PUT", data=payload)
    if not ok:
        return data, None
    action = "Updated" if sha else "Created"
    commit = (data.get("commit") or {}).get("sha", "")[:7]
    return (f"{action} {path} in {repo}, sir."
            + (f" Commit {commit}." if commit else ""), None)


# ---------------------------------------------------------------- dispatcher

GH_HELP = (
    "With your GitHub token I can work your repos: 'github repos' lists them, "
    "'github list owner/repo' shows files, 'github read owner/repo path' reads "
    "a file, 'github write owner/repo path: ...' creates or updates a file."
)

GH_PATTERNS = [
    (re.compile(r"^github repos$", re.I),
     lambda m: gh_repos()),
    (re.compile(r"^github list (\S+)(?: (\S+))?$", re.I),
     lambda m: gh_list(m.group(1), m.group(2) or "")),
    (re.compile(r"^github read (\S+) (\S+)$", re.I),
     lambda m: gh_read(m.group(1), m.group(2))),
    (re.compile(r"^github write (\S+) (\S+?)\s*:\s*(.+)$", re.I | re.S),
     lambda m: gh_write(m.group(1), m.group(2), m.group(3).strip())),
]
