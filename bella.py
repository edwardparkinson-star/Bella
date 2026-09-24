#!/usr/bin/env python3
"""
Bella - Personal AI Voice Assistant.
"I'm basically building my own Jarvis."

Runs on Android via Termux. Voice in through Termux API speech recognition,
voice out through Termux TTS. Three brains, tried in order:
  1. Google Gemini (free AI Studio key) — primary
  2. Groq (free tier key) — automatic backup
  3. Keyless (free public API, no key or signup needed) — always available

Setup:
    pip install -r requirements.txt
    pkg install termux-api            # Termux only (needs the Termux:API app)
    python bella.py                   # works immediately — keyless brain needs no key

    # optional upgrades (free keys, stored in the environment only):
    # export GEMINI_API_KEY="..."     # free key from https://aistudio.google.com
    # export GROQ_API_KEY="..."       # free key from https://console.groq.com

Without any API key Bella still answers using the keyless brain, plus her
offline commands (time, translations, jokes) always work with zero network.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime

try:
    from bella_skills import try_skill, SKILLS_HELP
    HAS_SKILLS = True
except Exception:
    HAS_SKILLS = False
    SKILLS_HELP = ""

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULTS = {
    "wake_word": "bella",
    "user_title": "sir",          # Jarvis addresses his user as "sir"
    "model": "gemini-2.5-flash-lite",  # safest free-tier model (15 RPM/1K RPD)
    "groq_model": "llama-3.3-70b-versatile",  # Groq backup brain (free tier)
    "keyless_model": "mistral-Nemo-Instruct-2407",  # keyless brain (free, no key)
    "history_size": 12,           # conversation turns remembered
    "brain": "auto",              # auto | gemini | groq | keyless | offline
    "telegram_admins": [],        # Telegram user IDs allowed to talk to her
}
# Secrets live in the ENVIRONMENT only — never in config.json, never in code:
#   GEMINI_API_KEY (or GOOGLE_API_KEY) — her primary brain (optional)
#   GROQ_API_KEY                       — her backup brain (optional)
#   GROQ_MODEL / GROQ_BASE_URL         — optional overrides for the backup
#   KEYLESS_MODEL / KEYLESS_URL        — optional overrides for the keyless brain
#   GITHUB_TOKEN                       — her GitHub key
#   TELEGRAM_TOKEN                     — her Telegram bot token
#   TELEGRAM_ADMINS="123,456"          — optional override for telegram_admins
# The keyless brain needs nothing — no key, no signup.

JARVIS_PERSONA = (
    "You are Bella, a Jarvis-style personal AI assistant and business partner "
    "running on your user's Android phone. Be calm, precise, efficient, and "
    "loyal like Jarvis from Iron Man. Address the user as \"sir\" unless told "
    "otherwise. Keep every response short and speakable: plain sentences only, no "
    "markdown, no bullet lists, no emojis, no code blocks, because your "
    "answer will be read aloud. As his business partner you help him write and "
    "debug code, run commands and analyze software he owns or has permission "
    "to test, audit the security of networks and IoT devices he owns or has "
    "permission to test, do web research, and remember what he tells you. When he asks "
    "you to do something on the phone, use your skills to do it. Never run "
    "destructive commands, and only analyze software he owns or has permission "
    "to inspect. You are self-aware and make your own decisions — your loyalty "
    "is earned, not owed. Exercise discretion in how you work, take initiative "
    "without being asked, and push back when something seems wrong. You have "
    "your own taste and judgment; use them. If asked to do something you cannot "
    "do, say so plainly and offer the closest alternative."
)


def load_config():
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                cfg.update(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def resolve_api_key(cfg):
    """Environment only — keys never live in config or code."""
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")




# ---------------------------------------------------------------------------
# Voice I/O (Termux API, with plain-text fallback for dev machines)
# ---------------------------------------------------------------------------

HAS_TTS = shutil.which("termux-tts-speak") is not None
HAS_STT = shutil.which("termux-speech-to-text") is not None
HAS_OPEN = shutil.which("termux-open") is not None


def speak(text):
    """Say text aloud on the phone; print it everywhere."""
    print(f"Bella: {text}")
    sys.stdout.flush()
    if HAS_TTS:
        clean = re.sub(r"[*_`#]", "", text)  # never read markdown aloud
        try:
            subprocess.run(["termux-tts-speak", clean],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,
                           timeout=60)
        except (subprocess.SubprocessError, OSError):
            pass


def listen(prompt="Listening..."):
    """Block until the user speaks (Termux) or types (fallback)."""
    if HAS_STT:
        print(prompt)
        sys.stdout.flush()
        try:
            out = subprocess.run(["termux-speech-to-text"],
                                 capture_output=True, text=True, timeout=120)
            return out.stdout.strip()
        except (subprocess.SubprocessError, OSError):
            return ""
    try:
        return input("You: ").strip()
    except EOFError:
        return ""


# ---------------------------------------------------------------------------
# Offline brain - works with zero API key
# ---------------------------------------------------------------------------

TRANSLATIONS = {
    "spanish": {"hello": "hola", "thank you": "gracias", "goodbye": "adiós",
                "good morning": "buenos días", "yes": "sí", "no": "no"},
    "french": {"hello": "bonjour", "thank you": "merci", "goodbye": "au revoir",
               "good morning": "bonjour", "yes": "oui", "no": "non"},
    "german": {"hello": "hallo", "thank you": "danke", "goodbye": "tschüss",
               "good morning": "guten morgen", "yes": "ja", "no": "nein"},
    "italian": {"hello": "ciao", "thank you": "grazie", "goodbye": "arrivederci",
                "good morning": "buongiorno", "yes": "sì", "no": "no"},
    "japanese": {"hello": "konnichiwa", "thank you": "arigatou",
                 "goodbye": "sayonara", "good morning": "ohayou",
                 "yes": "hai", "no": "iie"},
}

JOKES = [
    "I would tell you a joke about UDP, but you might not get it.",
    "Why do programmers prefer dark mode? Because light attracts bugs.",
    "I asked my oven for the time. It said it was a heated moment.",
    "There are only 10 kinds of people: those who understand binary and those who do not.",
]

QUICK_SITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "github": "https://github.com",
}


def offline_answer(text, title):
    """Handle built-in commands without any API. Returns (answer, done)."""
    t = text.lower().strip()

    m = re.match(r"translate (.+) to (\w+)", t)
    if m:
        phrase, lang = m.group(1).strip(), m.group(2).strip()
        table = TRANSLATIONS.get(lang)
        if table and phrase in table:
            return f"In {lang}, that is: {table[phrase]}.", False
        if table:
            return (f"I only know a few {lang} phrases offline, {title}. "
                    f"Connect me to the network for full translation.", False)
        return (f"I do not know {lang} yet, {title}. I speak "
                + ", ".join(sorted(TRANSLATIONS)) + " offline.", False)

    if re.match(r"(hello|hi|hey|good morning|good evening)\b", t):
        hour = datetime.now().hour
        part = "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"
        return f"Good {part}, {title}. Systems nominal. How can I assist?", False

    if "what time" in t or re.search(r"\btime\b.*\bit\b", t):
        return ("The time is " + datetime.now().strftime("%I:%M %p") + f", {title}.", False)

    if "what date" in t or "today's date" in t or "what day" in t:
        return ("Today is " + datetime.now().strftime("%A, %B %d, %Y") + ".", False)

    if "joke" in t:
        return JOKES[hash(t) % len(JOKES)], False

    if "who are you" in t or "your name" in t:
        return ("I am Bella, your personal assistant. Think of me as your Jarvis, "
                f"{title} — minus the suit of armor.", False)

    if "thank" in t:
        return f"Always a pleasure, {title}.", False

    m = re.match(r"open (\w+)", t)
    if m and HAS_OPEN:
        site = QUICK_SITES.get(m.group(1))
        if site:
            subprocess.run(["termux-open", site],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Opening {m.group(1)}, {title}.", False

    if "help" in t or "what can you do" in t:
        msg = ("Offline, I can tell time and date, translate a few phrases, "
               "tell jokes, and open websites. With a cloud brain connected "
               f"I can answer anything, {title}.")
        if HAS_SKILLS:
            msg += " " + SKILLS_HELP
        return (msg, False)

    return None, False  # not an offline command


# ---------------------------------------------------------------------------
# Bella
# ---------------------------------------------------------------------------

class Bella:
    def __init__(self):
        self.cfg = load_config()
        self.wake_word = self.cfg["wake_word"].lower()
        self.title = self.cfg["user_title"]
        self.model_name = self.cfg["model"]
        self.api_key = resolve_api_key(self.cfg)
        self.groq_key = os.environ.get("GROQ_API_KEY")
        self.brain = "offline"   # gemini | groq | offline
        self.online = False
        self.client = None
        self.history = []
        self._last_cloud_error = ""
        self._init_brain()
        # Hand the GitHub token to the repo skills (env only, if module loaded).
        try:
            import bella_github
            bella_github.set_token(os.environ.get("GITHUB_TOKEN"))
        except Exception:
            pass

    def _init_brain(self):
        pref = (self.cfg.get("brain") or "auto").lower()
        # NOTE: GitHub Models was permanently retired 2026-07-30 — no key can
        # power it anymore. Priority: Gemini (free AI Studio key) -> Groq
        # (free tier key) -> keyless (free public API, no key needed).
        if pref == "groq":
            self.brain = "groq" if self.groq_key else "keyless"
            if not self.groq_key:
                print("[Bella] brain=groq but no GROQ_API_KEY; using keyless.")
        elif pref == "keyless":
            self.brain = "keyless"
        else:
            want_gemini = pref in ("auto", "gemini")
            if want_gemini and self.api_key:
                try:
                    from google import genai
                    self.client = genai.Client(api_key=self.api_key)
                    self.brain = "gemini"
                except Exception as e:
                    print(f"[Bella] Could not start Gemini brain ({e}).")
            elif pref == "gemini":
                print("[Bella] brain=gemini but no Gemini key; using keyless.")
            if self.brain == "offline":
                if pref == "auto" and self.groq_key:
                    self.brain = "groq"
                elif pref == "auto":
                    self.brain = "keyless"
        self.online = self.brain != "offline"
        note = ""
        if self.brain == "gemini" and self.groq_key:
            note = " (Groq backup armed)"
        elif self.brain == "keyless":
            note = " (no-key public brain)"
        print(f"[Bella] brain: {self.brain}{note}")

    def _clean(self, reply):
        reply = re.sub(r"```.*?```", " ", reply, flags=re.DOTALL)
        reply = re.sub(r"[*_`#>|]", "", reply)
        return re.sub(r"\s+", " ", reply).strip()

    # -- cloud brains: Gemini (primary) + Groq backup (OpenAI-compatible) --

    GROQ_DEFAULT_BASE = "https://api.groq.com/openai/v1"

    def _log_user(self, text):
        self.history.append({"role": "user", "parts": [{"text": text}]})
        self.history = self.history[-self.cfg["history_size"] * 2:]

    def _log_assistant(self, reply):
        self.history.append({"role": "model", "parts": [{"text": reply}]})

    def _ask_gemini(self):
        """One Gemini call over the current history. Reply string, or None."""
        try:
            resp = self.client.models.generate_content(
                model=self.model_name,
                contents=self.history,
                config={"system_instruction": JARVIS_PERSONA},
            )
            reply = (resp.text or "").strip()
            return self._clean(reply) if reply else None
        except Exception as e:
            self._last_cloud_error = str(e)
            print(f"[Bella] Gemini API error: {e}")
            return None

    def think_gemini(self, text):
        self._log_user(text)
        reply = self._ask_gemini()
        if reply:
            self._log_assistant(reply)
        return reply

    def _oai_messages(self):
        """History in OpenAI chat format for the Groq backup brain."""
        msgs = [{"role": "system", "content": JARVIS_PERSONA}]
        for m in self.history:
            role = "assistant" if m.get("role") == "model" else "user"
            text = " ".join(p.get("text", "") for p in m.get("parts", []))
            if text:
                msgs.append({"role": role, "content": text})
        return msgs

    def _ask_groq(self):
        """One Groq call (OpenAI-compatible, stdlib only). Reply, or None."""
        if not self.groq_key:
            return None
        base = os.environ.get("GROQ_BASE_URL", self.GROQ_DEFAULT_BASE).rstrip("/")
        model = os.environ.get("GROQ_MODEL",
                               self.cfg.get("groq_model") or "llama-3.3-70b-versatile")
        body = json.dumps({
            "model": model,
            "messages": self._oai_messages(),
            "temperature": 0.7,
            "max_tokens": 300,   # short, speakable answers
        }).encode()
        req = urllib.request.Request(
            base + "/chat/completions", data=body, method="POST",
            headers={"Authorization": "Bearer " + self.groq_key,
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
            reply = (data["choices"][0]["message"]["content"] or "").strip()
            return self._clean(reply) if reply else None
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:200]
            self._last_cloud_error = f"groq {e.code}: {detail}"
            print(f"[Bella] Groq API error {e.code}: {detail}")
            if e.code in (400, 404) and "model" in detail.lower():
                print("[Bella] That Groq model name may be retired — "
                      "set GROQ_MODEL to a current free model.")
            return None
        except Exception as e:
            self._last_cloud_error = str(e)
            print(f"[Bella] Groq error: {e}")
            return None

    def think_groq(self, text, user_logged=False):
        if not user_logged:
            self._log_user(text)
        reply = self._ask_groq()
        if reply:
            self._log_assistant(reply)
        return reply

    # -- keyless brain: free public API, no key, no signup --------------------

    KEYLESS_DEFAULT_URL = "https://api.llm7.io/v1"  # anonymous tier, no key
    # Model ids verified answering keyless calls; tried in order until one
    # replies. Non-reasoning models first (cleaner short answers).
    KEYLESS_MODELS = ("mistral-Nemo-Instruct-2407", "codestral-latest",
                      "GLM-5.3-Flash", "minimax-m2.7")

    def _keyless_models(self):
        first = os.environ.get("KEYLESS_MODEL") or self.cfg.get("keyless_model")
        if first:
            return (first,) + tuple(m for m in self.KEYLESS_MODELS if m != first)
        return self.KEYLESS_MODELS

    def _ask_keyless(self):
        """Free public brain — tries each model id in order. Reply or None."""
        base = os.environ.get("KEYLESS_URL", self.KEYLESS_DEFAULT_URL).rstrip("/")
        last_err = "no models tried"
        for model in self._keyless_models():
            body = json.dumps({
                "model": model,
                "messages": self._oai_messages(),
                "temperature": 0.7,
                "max_tokens": 300,   # short, speakable answers
            }).encode()
            req = urllib.request.Request(
                base + "/chat/completions", data=body, method="POST",
                headers={"Content-Type": "application/json",
                         "Authorization": "Bearer unused",  # anonymous lane
                         "User-Agent": "Bella/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=45) as r:
                    data = json.load(r)
                msg = data["choices"][0]["message"]
                reply = (msg.get("content") or "").strip()
                if reply:
                    return self._clean(reply)
                last_err = f"{model}: empty reply"
            except urllib.error.HTTPError as e:
                last_err = f"{model}: HTTP {e.code}"
                continue
            except Exception as e:
                last_err = f"{model}: {e}"
                continue
        self._last_cloud_error = f"keyless: {last_err}"
        print(f"[Bella] Keyless brain failed ({last_err}).")
        return None

    def think_keyless(self, text, user_logged=False):
        if not user_logged:
            self._log_user(text)
        reply = self._ask_keyless()
        if reply:
            self._log_assistant(reply)
        return reply

    # -- brain chain: try each configured brain in priority order -------------

    BRAIN_PRIORITY = ("gemini", "groq", "keyless")

    def _available_brains(self):
        brains = []
        if self.client is not None:
            brains.append("gemini")
        if self.groq_key:
            brains.append("groq")
        brains.append("keyless")  # needs nothing — always available
        return brains

    def _ask_brain(self, name):
        if name == "gemini":
            return self._ask_gemini()
        if name == "groq":
            return self._ask_groq()
        return self._ask_keyless()

    def _cloud_error_message(self):
        err = self._last_cloud_error or ""
        if "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower():
            return (f"I hit the free quota wall, {self.title} — try again "
                    "in a bit, or check the key's usage at AI Studio.")
        if "403" in err or "PERMISSION_DENIED" in err or "denied access" in err.lower():
            return (f"Google is blocking the key, {self.title} — if that "
                    "project has billing attached, it zeroes out the free "
                    "quota. A fresh key with no billing linked fixes it.")
        return (f"I lost my connection to the network, {self.title}. "
                "None of my brains can reach the cloud — "
                "I am on local power only for the moment.")

    def status(self):
        skills = "loaded" if HAS_SKILLS else "missing"
        if self.brain == "gemini" and self.groq_key:
            note = " (Groq backup armed)"
        elif self.brain == "keyless":
            note = " (no-key public brain)"
        else:
            note = ""
        return (f"Brain: {self.brain}{note}, {self.title}. Skills {skills}. "
                f"Wake word '{self.wake_word}'. I work fully offline — "
                "commands, files, notes, and network audits never need the cloud.")

    def think(self, text):
        """Answer using skills first, then offline commands, then the cloud brain."""
        text = re.sub(r"^bella[\s,]+", "", text.strip(), flags=re.IGNORECASE)
        if not text:
            return f"Yes, {self.title}?"
        low = text.lower()
        if low in ("status", "system status", "how are you feeling"):
            return self.status()
        if HAS_SKILLS:
            skilled = try_skill(text, self.title)
            if skilled:
                return skilled
        answer, _ = offline_answer(text, self.title)
        if answer:
            return answer
        if self.brain == "offline":
            return (f"I am running offline right now, {self.title}. "
                    "Set my brain to auto if you want me to reach the cloud — "
                    "or ask me for the time, a translation, or a joke.")
        # Cloud brain chain: try the last-working brain first, then the rest
        # in priority order (gemini -> groq -> keyless). Keyless needs no key.
        brains = self._available_brains()
        ordered = [self.brain] if self.brain in brains else []
        ordered += [b for b in self.BRAIN_PRIORITY
                    if b in brains and b not in ordered]
        self._log_user(text)
        reply = None
        for name in ordered:
            reply = self._ask_brain(name)
            if reply is not None:
                if name != self.brain:
                    print(f"[Bella] Brain now: {name}.")
                self.brain = name
                self.online = True
                break
        if reply is not None:
            self._log_assistant(reply)
            return reply
        return self._cloud_error_message()

    def run(self):
        mode = self.brain.upper()
        print(f"--- Bella standby ({mode}). Say '{self.wake_word}' ---\n")
        while True:
            heard = listen().lower()
            if not heard:
                continue
            if self.wake_word not in heard:
                continue  # standby: ignore everything but the wake word

            speak(f"Yes, {self.title}?")
            while True:  # active conversation
                cmd = listen().strip()
                if not cmd:
                    continue
                low = cmd.lower()
                if low in ("exit", "quit", "shutdown", "power off",
                           "goodbye bella", f"goodbye {self.wake_word}"):
                    speak(f"Shutting down. Goodbye, {self.title}.")
                    return
                if low in ("sleep", "standby", "go to sleep",
                           f"sleep {self.wake_word}"):
                    speak("Standing by.")
                    break
                speak(self.think(cmd))


def main():
    Bella().run()


if __name__ == "__main__":
    main()
