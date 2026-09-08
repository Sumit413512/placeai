# PlaceAI Gemini API Setup

PlaceAI uses the official `google-genai` Python SDK. The default model is `gemini-3.8-flash`.

## 1. Create an API key

1. Open Google AI Studio: https://aistudio.google.com/apikey
2. Sign in with the Google account you want to use.
3. Create an API key and copy it.
4. Never place the key in frontend JavaScript, HTML, GitHub, screenshots, or emails.

## 2. Create the local `.env` file

From the PlaceAI project root, copy `.env.example` to `.env`.

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set:

```env
GEMINI_API_KEY=PASTE_YOUR_REAL_KEY_HERE
GEMINI_MODEL=gemini-3.8-flash
```

Do not add quotes around the key unless the key itself contains them.

## 3. Install dependencies

Activate the project virtual environment, then run:

```powershell
python -m pip install -r requirements.txt
```

The project already pins `google-genai`.

## 4. Restart PlaceAI

Stop the running server with `Ctrl+C`, then:

```powershell
python -m uvicorn app.app:app --reload
```

## 5. Verify Gemini configuration

Open this URL directly in the browser:

```text
http://127.0.0.1:8000/ai/status
```

The endpoint is non-secret and does not require login. A correct setup looks like:

```json
{
  "configured": true,
  "sdk_available": true,
  "model": "gemini-3.8-flash"
}
```

If `configured` is false, the `.env` key is missing/not loaded. Restart the server after saving `.env`.
If `sdk_available` is false, reinstall requirements in the same virtual environment used to run Uvicorn.

## 6. Test PlaceAI AI features

Student: upload a text-based PDF -> **Resume & AI** -> **Parse with AI** -> **Generate / refresh**.

Recruiter: open a job with applicants -> **View applicants** -> **AI-rank applicants**.

Both features use the same `GEMINI_API_KEY` and `GEMINI_MODEL`.

## Common failures

- `Gemini is not configured`: `.env` missing, wrong key variable, or server not restarted.
- `Google GenAI SDK is not installed`: install `requirements.txt` in the active venv.
- `Gemini request failed`: check key validity, model access, quota/rate limits, billing requirements, and internet connectivity.
- Resume parsing returns PDF error: use a text-based PDF rather than a scanned-image PDF.


## One-command connectivity check

After adding your key to `.env`, run:

```powershell
python scripts/check_gemini.py
```

A successful response starts with `[OK] Gemini API reachable`.

Never commit or share your `.env` file. If a key is pasted into chat, email, source code, screenshots, or a public repository, revoke it and create a new key before production use.
