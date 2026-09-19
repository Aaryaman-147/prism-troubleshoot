"""
Shared LLM client. Supports two providers behind one interface:
  - Gemini (native SDK) — your original setup
  - OpenRouter (OpenAI-compatible endpoint) — higher free-tier RPM (20/min
    vs Gemini's 5/min), useful for testing volume without hitting quota
    walls constantly.

Switch providers via .env: set LLM_PROVIDER=openrouter or LLM_PROVIDER=gemini.
Both enrichment.py and extraction.py call generate_json() here — this is
the one place to touch if you swap providers again.
"""
import asyncio
import json
import re
import time

from app.core.config import settings

_configured = False
_gemini_model = None
_openrouter_client = None
_openrouter_async_client = None
_async_client_loop = None


class LLMRateLimitError(Exception):
    """Raised when the provider's quota is exhausted, after retries."""
    pass


def _extract_retry_seconds(exc: Exception, default: int = 15) -> int:
    match = re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)", str(exc))
    if match:
        return int(match.group(1))
    return default


def _clean_json_text(text: str) -> str:
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())


def _generate_gemini(prompt: str, max_output_tokens: int, max_retries: int) -> dict:
    import google.generativeai as genai
    from google.api_core.exceptions import ResourceExhausted

    global _configured, _gemini_model
    if not _configured:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _configured = True
    if _gemini_model is None:
        _gemini_model = genai.GenerativeModel(settings.LLM_MODEL)

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            resp = _gemini_model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=max_output_tokens,
                    temperature=0.2,
                    response_mime_type="application/json",
                ),
            )
            # resp.text can be None (not raise!) when Gemini blocks the
            # response (safety filters) or stops early with no content
            # part — e.g. finish_reason=SAFETY or MAX_TOKENS with nothing
            # generated yet. This was previously crashing with a confusing
            # 'NoneType is not subscriptable' TypeError deep inside
            # str.strip(). Check explicitly and surface the real reason.
            if not resp.candidates or resp.text is None:
                finish_reason = None
                safety_ratings = None
                if resp.candidates:
                    finish_reason = resp.candidates[0].finish_reason
                    safety_ratings = resp.candidates[0].safety_ratings
                raise ValueError(
                    f"Gemini returned no text. finish_reason={finish_reason}, "
                    f"safety_ratings={safety_ratings}. This usually means the "
                    f"prompt/response hit a safety filter, or max_output_tokens "
                    f"({max_output_tokens}) was hit before any content was "
                    f"generated — try raising it."
                )
            return json.loads(_clean_json_text(resp.text))
        except ResourceExhausted as e:
            last_error = e
            retry_delay = min(_extract_retry_seconds(e), 60)
            if attempt < max_retries:
                print(f"[gemini rate limited] attempt {attempt + 1}/{max_retries + 1}, "
                      f"waiting {retry_delay}s")
                time.sleep(retry_delay)
            continue
    raise LLMRateLimitError(f"Gemini quota exhausted after {max_retries + 1} attempts: {last_error}")


def _generate_openrouter(prompt: str, max_output_tokens: int, max_retries: int) -> dict:
    from openai import OpenAI, RateLimitError

    global _openrouter_client

    if _openrouter_client is None:
        _openrouter_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY,
        )

    last_error = None

    for attempt in range(max_retries + 1):
        try:
            resp = _openrouter_client.chat.completions.create(
                model=settings.OPENROUTER_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_output_tokens,
                temperature=0.2,
                response_format={"type": "json_object"},
            )

            content = resp.choices[0].message.content

            if content is None:
                finish_reason = resp.choices[0].finish_reason
                raise ValueError(
                    f"OpenRouter returned no content. finish_reason={finish_reason}. "
                    f"Often means max_tokens was hit before generating anything, "
                    f"or the model/provider had an internal error — try raising "
                    f"max_output_tokens or switching models."
                )

            try:
                return json.loads(_clean_json_text(content))
            except json.JSONDecodeError as e:
                print(f"[JSON PARSE FAILED] model={settings.OPENROUTER_MODEL}")
                print(f"Raw content (first 500 chars): {content[:500]}")
                raise

        except RateLimitError as e:
            last_error = e
            wait = 10 * (attempt + 1)

            if attempt < max_retries:
                print(
                    f"[openrouter rate limited] attempt "
                    f"{attempt + 1}/{max_retries + 1}, "
                    f"waiting {wait}s"
                )
                time.sleep(wait)

            continue

    raise LLMRateLimitError(
        f"OpenRouter quota exhausted after "
        f"{max_retries + 1} attempts: {last_error}"
    )

def generate_json(prompt: str, max_output_tokens: int = 1500, max_retries: int = 2) -> dict:
    """
    Calls the configured provider (see LLM_PROVIDER in .env), strips any
    markdown code-fence wrapping, and parses JSON. Retries on rate limits
    with backoff. Raises LLMRateLimitError if still limited after retries,
    json.JSONDecodeError if output genuinely isn't valid JSON.
    """
    if settings.LLM_PROVIDER == "openrouter":
        return _generate_openrouter(prompt, max_output_tokens, max_retries)
    return _generate_gemini(prompt, max_output_tokens, max_retries)


# ---------------------------------------------------------------------------
# Async variants
# ---------------------------------------------------------------------------
# Why: the orchestrator fires enrichment + extraction concurrently. Under the
# old ThreadPoolExecutor that worked, but the FastAPI endpoint still blocked
# its event loop worker for the whole 5-40s cold call, so the server couldn't
# serve a sub-300ms cache hit to a second client while one cold call was in
# flight. Going async fixes that.
#
# OpenRouter gets REAL async (AsyncOpenAI -> non-blocking httpx). The Gemini
# SDK's generate_content is synchronous and blocking, so it gets a thread-pool
# fallback via asyncio.to_thread — which still frees the event loop, it just
# costs one worker thread per in-flight call.


async def _generate_openrouter_async(prompt: str, max_output_tokens: int, max_retries: int) -> dict:
    from openai import AsyncOpenAI, RateLimitError

    global _openrouter_async_client, _async_client_loop

    # The async client holds an httpx connection pool bound to the event loop
    # it was created on. Re-using it across loops (pytest creates a fresh loop
    # per test) raises "Event loop is closed", so rebuild it if the loop changed.
    current_loop = asyncio.get_running_loop()
    if _openrouter_async_client is None or _async_client_loop is not current_loop:
        _openrouter_async_client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY,
        )
        _async_client_loop = current_loop

    last_error = None

    for attempt in range(max_retries + 1):
        try:
            resp = await _openrouter_async_client.chat.completions.create(
                model=settings.OPENROUTER_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_output_tokens,
                temperature=0.2,
                response_format={"type": "json_object"},
            )

            content = resp.choices[0].message.content

            if content is None:
                finish_reason = resp.choices[0].finish_reason
                raise ValueError(
                    f"OpenRouter returned no content. finish_reason={finish_reason}. "
                    f"Often means max_tokens was hit before generating anything, "
                    f"or the model/provider had an internal error — try raising "
                    f"max_output_tokens or switching models."
                )

            try:
                return json.loads(_clean_json_text(content))
            except json.JSONDecodeError:
                print(f"[JSON PARSE FAILED] model={settings.OPENROUTER_MODEL}")
                print(f"Raw content (first 500 chars): {content[:500]}")
                raise

        except RateLimitError as e:
            last_error = e
            wait = 10 * (attempt + 1)

            if attempt < max_retries:
                print(
                    f"[openrouter rate limited] attempt "
                    f"{attempt + 1}/{max_retries + 1}, waiting {wait}s"
                )
                # asyncio.sleep, NOT time.sleep — blocking here would stall
                # every other request on the event loop during the backoff.
                await asyncio.sleep(wait)

            continue

    raise LLMRateLimitError(
        f"OpenRouter quota exhausted after "
        f"{max_retries + 1} attempts: {last_error}"
    )


async def generate_json_async(prompt: str, max_output_tokens: int = 1500, max_retries: int = 2) -> dict:
    """
    Async counterpart of generate_json(). Same contract, same exceptions
    (LLMRateLimitError, ValueError, json.JSONDecodeError) — the orchestrator's
    error handling is unchanged.

    - openrouter -> genuinely non-blocking HTTP
    - gemini     -> blocking SDK call offloaded to a worker thread
    """
    if settings.LLM_PROVIDER == "openrouter":
        return await _generate_openrouter_async(prompt, max_output_tokens, max_retries)
    return await asyncio.to_thread(
        _generate_gemini, prompt, max_output_tokens, max_retries
    )
