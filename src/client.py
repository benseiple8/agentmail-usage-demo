"""Thin wrapper around the AgentMail REST API, used by every other script.
Reads AGENTMAIL_API_KEY from .env. No SDK: calls are verified directly
against https://docs.agentmail.to/openapi.json so behavior matches the real
API."""
import os

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("AGENTMAIL_API_KEY")
BASE_URL = "https://api.agentmail.to"

if not API_KEY:
    raise RuntimeError(
        "AGENTMAIL_API_KEY not set. Copy .env.example to .env and add your real key."
    )


def _headers():
    return {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


def get(path, params=None):
    r = requests.get(f"{BASE_URL}{path}", headers=_headers(), params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def post(path, json_body=None):
    r = requests.post(f"{BASE_URL}{path}", headers=_headers(), json=json_body or {}, timeout=30)
    r.raise_for_status()
    return r.json()
