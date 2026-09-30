"""
One-call smoke test of the configured LLM provider (uses 1-2 requests).
Tells you whether the key, base URL, model and JSON mode work.

  python scripts\\check_provider.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.config import settings
from app.core import llm_client

PROMPT = 'Return ONLY this JSON object: {"status": "ok", "model_check": true}'


def attempt(json_mode: bool):
    settings.LLM_JSON_MODE = json_mode
    llm_client._openrouter_client = None
    return llm_client.generate_json(PROMPT, max_output_tokens=200, max_retries=0)


def main():
    model = settings.OPENROUTER_MODEL if settings.LLM_PROVIDER == "openrouter" else settings.LLM_MODEL
    base = settings.OPENROUTER_BASE_URL if settings.LLM_PROVIDER == "openrouter" else "Gemini SDK"
    from app.core.config import key_fingerprint, key_was_overridden, DOTENV_DUPLICATES, DOTENV_PATH
    print(f"dotenv file: {DOTENV_PATH or '(none)'}")
    key = settings.OPENROUTER_API_KEY if settings.LLM_PROVIDER == "openrouter" else settings.GEMINI_API_KEY
    print(f"provider={settings.LLM_PROVIDER} base={base} model={model} LLM_JSON_MODE={settings.LLM_JSON_MODE}")
    print(f"key={key_fingerprint(key)}  (compare with: curl.exe http://localhost:8000/v1/provider-check)")
    if key_was_overridden():
        print("note: this terminal had a DIFFERENT key in its environment; .env now overrides it")
    if DOTENV_DUPLICATES:
        print(f"WARNING: .env defines {DOTENV_DUPLICATES} more than once")
    try:
        data, usage = attempt(settings.LLM_JSON_MODE)
        print(f"OK  -> {data}  tokens={usage.prompt_tokens}+{usage.completion_tokens}")
        return
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        print(f"FAILED with JSON mode={settings.LLM_JSON_MODE}: {msg[:400]}")
        low = msg.lower()
        if "401" in low or "unauthorized" in low or "api key" in low:
            sys.exit("-> Authentication problem: check OPENROUTER_API_KEY (NVIDIA keys start with nvapi-).")
        if "404" in low or "not found" in low:
            sys.exit("-> Model not found at this base URL: check OPENROUTER_MODEL (NVIDIA ids have no ':free' suffix).")
        if "429" in low or "rate" in low:
            sys.exit("-> Rate limited: wait and retry.")
        if "503" in low or "overloaded" in low or "500" in low or "502" in low:
            sys.exit("-> Provider temporarily overloaded (5xx). Not a configuration problem:\n"
                     "   wait a minute and run this again. Keep LLM_JSON_MODE as it is.")
        if not ("400" in low or "response_format" in low or "json" in low):
            sys.exit("-> Unrecognised error; see the message above.")
    if settings.LLM_PROVIDER == "openrouter" and settings.LLM_JSON_MODE:
        print("Retrying once WITHOUT response_format (JSON mode off)...")
        try:
            data, usage = attempt(False)
            print(f"OK without JSON mode -> {data}\n-> Set LLM_JSON_MODE=false in .env for this provider/model.")
        except Exception as e:
            print(f"Still failing without JSON mode: {type(e).__name__}: {str(e)[:400]}")


if __name__ == "__main__":
    main()
