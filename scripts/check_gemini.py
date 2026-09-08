from __future__ import annotations

import os
import sys
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("GEMINI_API_KEY", "").strip()
model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash"

if not key:
    print("[FAIL] GEMINI_API_KEY is missing. Add it to .env and restart the app.")
    raise SystemExit(2)

try:
    from google import genai
except Exception as exc:
    print(f"[FAIL] google-genai is not installed: {exc}")
    print("Run: python -m pip install -r requirements.txt")
    raise SystemExit(3)

try:
    client = genai.Client(api_key=key)
    response = client.models.generate_content(model=model, contents="Reply with exactly: PLACEAI GEMINI OK")
    text = (getattr(response, "text", "") or "").strip()
    print(f"[OK] Gemini API reachable with model: {model}")
    print(f"Response: {text[:200]}")
except Exception as exc:
    print(f"[FAIL] Gemini request failed using {model}: {exc}")
    print("Check the API key, API access, quota/rate limits, billing requirements and internet connection.")
    raise SystemExit(4)
