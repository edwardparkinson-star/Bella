#!/usr/bin/env python3
"""
JARVIS Batcomputer — local client (laptop / 8GB device).

Listens for the wake word, records your command, sends it to the cloud
server's /command endpoint, and speaks the reply.

Setup:
    pip install -r requirements-client.txt
    # first run downloads the wake-word model automatically
    export JARVIS_URL="https://your-server:8000/command"
    python client.py

Env:
    JARVIS_URL    full /command URL of your server
    JARVIS_VOICE  edge-tts voice (default en-US-GuyNeural)

Speech-to-text uses faster-whisper when installed; otherwise you type
the command after the wake word fires.
"""

import asyncio
import os
import shutil
import subprocess
import tempfile
import wave

import numpy as np
import requests
import sounddevice as sd

import edge_tts
from openwakeword.model import Model

CLOUD_URL = os.getenv("JARVIS_URL", "http://YOUR_RUNPOD_URL:8000/command")
VOICE = os.getenv("JARVIS_VOICE", "en-US-GuyNeural")
WAKE_WORDS = ["hey_jarvis"]
WAKE_THRESHOLD = 0.5
SAMPLE_RATE = 16000
FRAME_SAMPLES = int(0.08 * SAMPLE_RATE)  # 80 ms frames, what openwakeword wants
COMMAND_SECONDS = 5

try:
    from faster_whisper import WhisperModel
    _stt = WhisperModel("tiny", device="cpu", compute_type="int8")
    _HAS_WHISPER = True
except Exception:
    _HAS_WHISPER = False


def transcribe(audio: np.ndarray) -> str:
    """Speech -> text. faster-whisper when installed, typed fallback."""
    if _HAS_WHISPER:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SAMPLE_RATE)
                w.writeframes(audio.tobytes())
            segments, _ = _stt.transcribe(path)
            return " ".join(s.text for s in segments).strip()
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
    return input("STT unavailable — type your command: ").strip()


def _play_file(path: str) -> bool:
    """Play an mp3 with the first available player. Returns False if none."""
    try:
        import pygame  # noqa
        import pygame.mixer
        pygame.mixer.init()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(100)
        return True
    except Exception:
        pass
    for player, args in (("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
                         ("mpv", ["--no-video", "--really-quiet"])):
        if shutil.which(player):
            try:
                subprocess.run([player, *args, path], check=True,
                               timeout=120)
                return True
            except Exception:
                pass
    return False


async def speak(text: str):
    """Speak a reply through edge-tts."""
    communicate = edge_tts.Communicate(text, VOICE)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        path = f.name
    try:
        await communicate.save(path)
        if not _play_file(path):
            print("(no audio player found — install pygame or ffplay "
                  "to hear replies)")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def ensure_wakeword_models():
    try:
        from openwakeword.utils import download_models
        download_models()
    except Exception as e:
        print(f"Wake-word model download issue: {e} — "
              "continuing with whatever is cached.")


async def main():
    if "YOUR_RUNPOD_URL" in CLOUD_URL:
        print("Set JARVIS_URL to your server's /command URL first, "
              "e.g. export JARVIS_URL=\"https://xxx:8000/command\"")
        return
    ensure_wakeword_models()
    oww = Model(wakeword_models=WAKE_WORDS)
    print("JARVIS is listening... (Ctrl+C to stop)")
    while True:
        audio = sd.rec(FRAME_SAMPLES, samplerate=SAMPLE_RATE,
                       channels=1, dtype=np.int16)
        sd.wait()
        scores = oww.predict(audio.flatten())
        if max(scores.values(), default=0) > WAKE_THRESHOLD:
            print("Wake word detected — listening for command...")
            cmd_audio = sd.rec(COMMAND_SECONDS * SAMPLE_RATE,
                               samplerate=SAMPLE_RATE,
                               channels=1, dtype=np.int16)
            sd.wait()
            text = transcribe(cmd_audio.flatten())
            if not text:
                print("Didn't catch that.")
                continue
            print("You:", text)
            try:
                r = requests.post(CLOUD_URL, json={"text": text},
                                  timeout=120)
                r.raise_for_status()
                reply = r.json().get("response", "")
            except Exception as e:
                print("Error:", e)
                continue
            print("JARVIS:", reply)
            if reply:
                await speak(reply)


if __name__ == "__main__":
    asyncio.run(main())
