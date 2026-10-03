#!/usr/bin/env python3
"""
JARVIS Batcomputer — cloud brain server.

FastAPI service: POST a text command to /command, get JARVIS's reply
from Ollama. Runs on the cloud box (e.g. RunPod); the local client
talks to it over HTTPS.

Setup:
    pip install -r requirements-server.txt
    cp .env.example .env   # fill in your values (keys NEVER go in code)
    uvicorn server:app --host 0.0.0.0 --port 8000

Env (.env supported):
    OLLAMA_HOST     Ollama base URL             (default http://localhost:11434)
    DEFAULT_MODEL   Ollama model                (default llama3.2)
    SHODAN_API_KEY  optional — enables /shodan/{ip} lookups
"""

import os

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

try:
    from shodan import Shodan
    _HAS_SHODAN = True
except ImportError:
    _HAS_SHODAN = False

app = FastAPI(title="JARVIS Batcomputer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "llama3.2")
SHODAN_API_KEY = os.getenv("SHODAN_API_KEY", "").strip()


def _shodan():
    """Shodan client, or None when the key/package is missing."""
    if not _HAS_SHODAN or not SHODAN_API_KEY:
        return None
    return Shodan(SHODAN_API_KEY)


class Command(BaseModel):
    text: str


class Reply(BaseModel):
    response: str
    status: str = "success"


@app.get("/status")
async def status():
    return {"status": "JARVIS online", "system": "Batcomputer Tactical Core"}


@app.post("/command", response_model=Reply)
async def process_command(cmd: Command):
    text = cmd.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty command.")
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            payload = {
                "model": DEFAULT_MODEL,
                "prompt": (
                    "You are JARVIS, a tactical AI assistant inspired by "
                    "Iron Man and the Batcomputer. Be precise, strategic, "
                    "and slightly sarcastic. Keep every answer short and "
                    f"speakable. User: {text}"
                ),
                "stream": False,
            }
            r = await client.post(f"{OLLAMA_HOST}/api/generate", json=payload)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502,
                            detail=f"Ollama unreachable: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return Reply(response=(data.get("response") or
                           "No response generated.").strip())


@app.get("/shodan/{ip}")
async def shodan_lookup(ip: str):
    """Host intel via Shodan. Needs SHODAN_API_KEY in the environment."""
    api = _shodan()
    if api is None:
        raise HTTPException(status_code=501, detail=(
            "Shodan is not configured — install the shodan package "
            "and set SHODAN_API_KEY."))
    try:
        host = api.host(ip)
    except Exception as e:
        raise HTTPException(status_code=502,
                            detail=f"Shodan query failed: {e}")
    return {
        "ip": host.get("ip_str"),
        "org": host.get("org"),
        "os": host.get("os"),
        "ports": host.get("ports"),
        "hostnames": host.get("hostnames"),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
