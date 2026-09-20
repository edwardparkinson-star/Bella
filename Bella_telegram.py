#!/usr/bin/env python3
"""
Bella on Telegram — remote-control bridge.

Message her from anywhere and she answers with her full brain and skills:
commands, files, notes, network audits, GitHub repos. No wake word needed;
you're talking to her directly.

Setup:
  1. Message @BotFather on Telegram, /newbot, copy the token.
  2. Message @userinfobot, copy your numeric user ID.
  3. Set env vars: TELEGRAM_TOKEN, TELEGRAM_ADMINS (your numeric user ID).
     (or put your id in config.json's telegram_admins).
  4. Run:  python bella_telegram.py   (keep Termux awake: termux-wake-lock)

Security: ONLY the IDs in telegram_admins can talk to her. Everyone else is
ignored. Tokens live in the environment only — never in config or code.
"""

import json
import os
import time
import urllib.parse
import urllib.request

from bella import Bella, load_config

CHUNK = 4000  # Telegram message limit is 4096


def tg_call(token, method, params=None, timeout=40):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params or {}).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def chunk_text(text):
    """Split a long reply into Telegram-sized chunks on line boundaries."""
    if len(text) <= CHUNK:
        return [text]
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > CHUNK:
            chunks.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        chunks.append(cur)
    return chunks or [text[:CHUNK]]


def send_reply(token, chat_id, text):
    for part in chunk_text(text):
        try:
            tg_call(token, "sendMessage",
                    {"chat_id": chat_id, "text": part})
        except Exception as e:
            print(f"[tg] send failed: {e}")
            break


def main():
    cfg = load_config()
    token = os.environ.get("TELEGRAM_TOKEN")
    admins = cfg.get("telegram_admins") or []
    env_admins = os.environ.get("TELEGRAM_ADMINS", "")
    if env_admins.strip():
        admins = [int(x) for x in env_admins.replace(",", " ").split()
                  if x.strip().isdigit()]
    if not token:
        print("[tg] No Telegram token. Set TELEGRAM_TOKEN in the environment.")
        return
    if not admins:
        print("[tg] WARNING: 'telegram_admins' is empty — I will ignore "
              "everyone until you add your Telegram user ID.")

    bella = Bella()
    print(f"[tg] Bella online on Telegram (brain: {bella.brain}). "
          f"Admins: {admins or 'none yet'}")

    offset = 0
    while True:
        try:
            updates = tg_call(token, "getUpdates",
                              {"offset": offset, "timeout": 30}, timeout=40)
        except Exception as e:
            print(f"[tg] poll error: {e}; retrying...")
            time.sleep(5)
            continue
        for u in updates.get("result", []):
            offset = u["update_id"] + 1
            msg = u.get("message") or {}
            frm = msg.get("from") or {}
            uid = frm.get("id")
            text = (msg.get("text") or "").strip()
            if not text or "chat" not in msg:
                continue
            if uid not in admins:
                print(f"[tg] ignored message from unauthorized user {uid} "
                      f"(@{frm.get('username')})")
                continue
            if text.startswith("/"):
                text = text[1:]  # /status -> status
            name = frm.get("username") or frm.get("first_name") or uid
            print(f"[tg] {name}: {text[:80]}")
            try:
                reply = bella.think(text)
            except Exception as e:
                reply = f"Something glitched on my end, {bella.title}: {e}"
            send_reply(token, msg["chat"]["id"], reply)


if __name__ == "__main__":
    main()
