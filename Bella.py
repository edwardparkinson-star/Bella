#!/usr/bin/env python3
"""
Bella - Personal AI Voice Assistant.
"I'm basically building my own Jarvis."

Runs on Android via Termux. Voice in through Termux API speech recognition,
voice out through Termux TTS, brain powered by Google Gemini (free tier).

Setup:
    pip install -r requirements.txt
    pkg install termux-api            # Termux only (needs the Termux:API app)
    # then put your free Gemini key from https://aistudio.google.com
    # in the GEMINI_API_KEY env var or in config.json, and run:
    python bella.py

Without an API key Bella still works, but only with her offline commands.
"""

import json
import os
import re
import shutil
import subprocess
import sys
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
    "model": "gemini-2.5-flash",
    "history_size": 12,           # conversation turns remembered
    "brain": "auto",              # auto | gemini | offline
    "github_token": "",           # GitHub OAuth/PAT token for repo skills
    "telegram_token": "",         # Telegram bot token from @BotFather
    "telegram_admins": [],        # your Telegram user ID(s) — only these can talk to her
}

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
    """Env var wins, then config.json, then None (offline mode)."""
    return (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or cfg.get("api_key")
    )




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
               "tell jokes, and open websites. With a free Gemini API key from "
               f"AI Studio I can answer anything, {title}.")
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
        self.brain = "offline"   # gemini | offline
        self.online = False
        self.client = None
        self.history = []
        self._init_brain()
        # Hand the GitHub token to the repo skills (if the module loaded).
        try:
            import bella_github
            bella_github.set_token(
                os.environ.get("GITHUB_TOKEN") or self.cfg.get("github_token"))
        except Exception:
            pass

    def _init_brain(self):
        pref = (self.cfg.get("brain") or "auto").lower()
        # NOTE: GitHub Models was permanently retired 2026-07-30 — no key can
        # power it anymore. Gemini (free AI Studio key) is the cloud brain.
        want_gemini = pref in ("auto", "gemini")
        if want_gemini and self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
                self.brain = "gemini"
                self.online = True
            except Exception as e:
                print(f"[Bella] Could not start Gemini brain ({e}); offline mode.")
        elif pref == "gemini":
            print("[Bella] brain=gemini but no Gemini key found; offline mode.")
        print(f"[Bella] brain: {self.brain}")

    def _clean(self, reply):
        reply = re.sub(r"```.*?```", " ", reply, flags=re.DOTALL)
        reply = re.sub(r"[*_`#>|]", "", reply)
        return re.sub(r"\s+", " ", reply).strip()

    def think_gemini(self, text):
        try:
            self.history.append({"role": "user", "parts": [{"text": text}]})
            self.history = self.history[-self.cfg["history_size"] * 2:]
            resp = self.client.models.generate_content(
                model=self.model_name,
                contents=self.history,
                config={"system_instruction": JARVIS_PERSONA},
            )
            reply = (resp.text or "").strip()
            if not reply:
                return f"My apologies, {self.title} — I drew a blank on that one."
            reply = self._clean(reply)
            self.history.append({"role": "model", "parts": [{"text": reply}]})
            return reply
        except Exception as e:
            print(f"[Bella] API error: {e}")
            return (f"I lost my connection to the network, {self.title}. "
                    "I am on local power only for the moment.")

    def status(self):
        skills = "loaded" if HAS_SKILLS else "missing"
        return (f"Brain: {self.brain}, {self.title}. Skills {skills}. "
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
        if self.brain == "gemini":
            return self.think_gemini(text)
        return (f"I am running offline right now, {self.title}. "
                "Add a free Gemini API key from AI Studio for full answers — "
                "or ask me for the time, a translation, or a joke.")

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
