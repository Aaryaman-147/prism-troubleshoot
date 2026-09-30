"""
Shared LLM client. Supports two providers behind one interface:
  - Gemini (native SDK) - your original setup
  - OpenRouter (OpenAI-compatible endpoint) - higher free-tier RPM (20/min
    vs Gemini's 5/min), useful for testing volume without hitting quota
    walls constantly.

Switch providers via .env: set LLM_PROVIDER=openrouter or LLM_PROVIDER=gemini.
Both enrichment.py and extraction.py call generate_json()/generate_json_async()
here - this is the one place to touch if you swap providers again.
"""
import asyncio
import json
import re
import time
from dataclasses import dataclass

from app.core.config import settings

_configured = False
_gemini_model = None
_openrouter_client = None
_openrouter_async_client = None
_async_client_loop = None


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def estimated_cost_usd(self, rate_per_1k_tokens: float = 0.0) -> float:
        return (self.total_tokens / 1000) * rate_per_1k_tokens


class LLMRateLimitError(Exception):
    pass


def _extract_retry_seconds(exc: Exception, default: int = 15) -> int:
    match = re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)", str(exc))
    if match:
        return int(match.group(1))
    return default


def _clean_json_text(text: str) -> str:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())

    start = text.find("{")
    if start == -1:
        return text

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    return text[start:]


def _is_transient_server_error(e: Exception) -> bool:
    """503 'Service temporarily overloaded' etc. from NVIDIA/OpenRouter --
    previously not retried, so one overloaded moment failed the request."""
    if type(e).__name__ in {"InternalServerError", "APIConnectionError", "APITimeoutError", "ServiceUnavailableError"}:
        return True
    return getattr(e, "status_code", 0) in (500, 502, 503, 504)


def _top_level_objects(text: str):
    """Yield every top-level balanced {...} span. Quotes are only tracked
    inside an object, so apostrophes/quotes in surrounding prose don't
    confuse the scan."""
    depth, start, in_str, esc = 0, None, False, False
    for i, ch in enumerate(text):
        if depth and in_str:
            if esc: esc = False
            elif ch == "\\": esc = True
            elif ch == '"': in_str = False
            continue
        if depth and ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0: start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0:
                yield text[start:i + 1]


def _parse_json(text: str, required_keys=None) -> dict:
    """
    Without required_keys: first balanced object (previous behaviour).
    With required_keys: the first object that parses AND contains one of
    them. Reasoning models sometimes quote a small JSON example before the
    real answer; in a real run the parser returned {"key": "wifi_connected",
    ...} from the reasoning instead of the {"contexts": [...]} answer.
    """
    if not required_keys:
        return json.loads(_clean_json_text(text))
    stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    for span in _top_level_objects(stripped):
        try:
            obj = json.loads(span)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and any(k in obj for k in required_keys):
            return obj
    raise json.JSONDecodeError(f"no JSON object containing any of {list(required_keys)}", stripped[:200], 0)


def _thinking_kwargs() -> dict:
    """NVIDIA's Nemotron 3 models reason by default; that text consumed the
    output budget (truncated JSON, 76-102 s cases) and leaked into content.
    chat_template_kwargs.enable_thinking=false turns it off. Only sent to
    NVIDIA's endpoint, where it is documented."""
    if settings.LLM_DISABLE_THINKING and "nvidia.com" in str(settings.OPENROUTER_BASE_URL):
        return {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
    return {}


def _generate_gemini(prompt: str, max_output_tokens: int, max_retries: int, required_keys=None) -> tuple[dict, TokenUsage]:
    import google.generativeai as genai
    from google.api_core.exceptions import ResourceExhausted

    global _configured, _gemini_model
    if not _configured:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _configured = True
    if _gemini_model is None:
        _gemini_model = genai.GenerativeModel(settings.LLM_MODEL)

    last_error = None
    last_error_was_transient_parse_failure = False
    for attempt in range(max_retries + 1):
        try:
            resp = _gemini_model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=max_output_tokens,
                    temperature=settings.LLM_TEMPERATURE,
                    response_mime_type="application/json",
                ),
            )
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
                    f"generated - try raising it."
                )
            try:
                parsed = _parse_json(resp.text, required_keys)
            except json.JSONDecodeError:
                print(f"[JSON PARSE FAILED] model={settings.LLM_MODEL}")
                print(f"Raw content (first 500 chars): {resp.text[:500]}")
                raise
            usage = TokenUsage()
            if hasattr(resp, "usage_metadata") and resp.usage_metadata:
                usage = TokenUsage(
                    prompt_tokens=getattr(resp.usage_metadata, "prompt_token_count", 0) or 0,
                    completion_tokens=getattr(resp.usage_metadata, "candidates_token_count", 0) or 0,
                )
            return parsed, usage
        except ResourceExhausted as e:
            last_error = e
            retry_delay = min(_extract_retry_seconds(e), 60)
            if attempt < max_retries:
                print(f"[gemini rate limited] attempt {attempt + 1}/{max_retries + 1}, "
                      f"waiting {retry_delay}s")
                time.sleep(retry_delay)
            continue
        except json.JSONDecodeError as e:
            last_error = e
            last_error_was_transient_parse_failure = True
            if attempt < max_retries:
                wait = 3 * (attempt + 1)
                print(f"[gemini malformed JSON] attempt {attempt + 1}/{max_retries + 1}, "
                      f"retrying in {wait}s")
                time.sleep(wait)
            continue

    if last_error_was_transient_parse_failure:
        raise json.JSONDecodeError(
            f"Gemini returned malformed JSON {max_retries + 1} times in a row: "
            f"{last_error}",
            "", 0,
        )
    raise LLMRateLimitError(f"Gemini quota exhausted after {max_retries + 1} attempts: {last_error}")


def _generate_openrouter(prompt: str, max_output_tokens: int, max_retries: int, required_keys=None) -> tuple[dict, TokenUsage]:
    from openai import OpenAI, RateLimitError

    global _openrouter_client

    if _openrouter_client is None:
        _openrouter_client = OpenAI(
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
            timeout=settings.LLM_TIMEOUT_S,
        )

    last_error = None
    last_error_was_empty_response = False

    for attempt in range(max_retries + 1):
        try:
            resp = _openrouter_client.chat.completions.create(
                model=settings.OPENROUTER_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_output_tokens,
                temperature=settings.LLM_TEMPERATURE,
                **({"response_format": {"type": "json_object"}} if settings.LLM_JSON_MODE else {}),
                **_thinking_kwargs(),
            )

            if not resp.choices:
                raise ValueError(
                    f"OpenRouter returned no choices at all (resp.choices="
                    f"{resp.choices!r}). Usually an upstream provider error "
                    f"or moderation flag that didn't surface as an HTTP "
                    f"error - try again or switch models."
                )

            content = resp.choices[0].message.content

            if content is None:
                finish_reason = resp.choices[0].finish_reason
                raise ValueError(
                    f"OpenRouter returned no content. finish_reason={finish_reason}. "
                    f"Often means max_tokens was hit before generating anything, "
                    f"or the model/provider had an internal error - try raising "
                    f"max_output_tokens or switching models."
                )

            usage = TokenUsage()
            if resp.usage:
                usage = TokenUsage(
                    prompt_tokens=resp.usage.prompt_tokens or 0,
                    completion_tokens=resp.usage.completion_tokens or 0,
                )

            try:
                return _parse_json(content, required_keys), usage
            except json.JSONDecodeError as e:
                print(f"[JSON PARSE FAILED] model={settings.OPENROUTER_MODEL}")
                print(f"Raw content (first 500 chars): {content[:500]}")
                raise

        except RateLimitError as e:
            last_error = e
            wait = 10 * (attempt + 1)
            if attempt < max_retries:
                print(f"[openrouter rate limited] attempt {attempt + 1}/{max_retries + 1}, waiting {wait}s")
                time.sleep(wait)
            continue

        except json.JSONDecodeError as e:
            last_error = e
            last_error_was_empty_response = True
            wait = 3 * (attempt + 1)
            if attempt < max_retries:
                print(f"[openrouter malformed JSON] attempt {attempt + 1}/{max_retries + 1}, retrying in {wait}s")
                time.sleep(wait)
            continue

        except ValueError as e:
            if "OpenRouter returned no" not in str(e):
                raise
            last_error = e
            last_error_was_empty_response = True
            wait = 5 * (attempt + 1)
            if attempt < max_retries:
                print(f"[openrouter empty response] attempt {attempt + 1}/{max_retries + 1}, waiting {wait}s")
                time.sleep(wait)
            continue

        except Exception as e:
            if not _is_transient_server_error(e):
                raise
            last_error = e
            last_error_was_empty_response = True   # not quota: surface as a generation failure
            wait = 5 * (attempt + 1)
            if attempt < max_retries:
                print(f"[provider server error] {type(e).__name__} attempt {attempt + 1}/{max_retries + 1}, waiting {wait}s")
                time.sleep(wait)
            continue

    if last_error_was_empty_response:
        raise ValueError(
            f"OpenRouter returned an empty/malformed response "
            f"{max_retries + 1} times in a row: {last_error}"
        )
    raise LLMRateLimitError(
        f"OpenRouter quota exhausted after "
        f"{max_retries + 1} attempts: {last_error}"
    )

def generate_json(prompt: str, max_output_tokens: int = 1500, max_retries: int = 2, required_keys=None) -> tuple[dict, TokenUsage]:
    if settings.LLM_PROVIDER == "openrouter":
        return _generate_openrouter(prompt, max_output_tokens, max_retries, required_keys)
    return _generate_gemini(prompt, max_output_tokens, max_retries, required_keys)


async def _generate_openrouter_async(prompt: str, max_output_tokens: int, max_retries: int, required_keys=None) -> tuple[dict, TokenUsage]:
    from openai import AsyncOpenAI, RateLimitError

    global _openrouter_async_client, _async_client_loop

    current_loop = asyncio.get_running_loop()
    if _openrouter_async_client is None or _async_client_loop is not current_loop:
        _openrouter_async_client = AsyncOpenAI(
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
            timeout=settings.LLM_TIMEOUT_S,
        )
        _async_client_loop = current_loop

    last_error = None
    last_error_was_empty_response = False

    for attempt in range(max_retries + 1):
        try:
            resp = await _openrouter_async_client.chat.completions.create(
                model=settings.OPENROUTER_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_output_tokens,
                temperature=settings.LLM_TEMPERATURE,
                **({"response_format": {"type": "json_object"}} if settings.LLM_JSON_MODE else {}),
                **_thinking_kwargs(),
            )

            if not resp.choices:
                raise ValueError(
                    f"OpenRouter returned no choices at all (resp.choices="
                    f"{resp.choices!r}). Usually an upstream provider error "
                    f"or moderation flag that didn't surface as an HTTP "
                    f"error - try again or switch models."
                )

            content = resp.choices[0].message.content

            if content is None:
                finish_reason = resp.choices[0].finish_reason
                raise ValueError(
                    f"OpenRouter returned no content. finish_reason={finish_reason}. "
                    f"Often means max_tokens was hit before generating anything, "
                    f"or the model/provider had an internal error - try raising "
                    f"max_output_tokens or switching models."
                )

            usage = TokenUsage()
            if resp.usage:
                usage = TokenUsage(
                    prompt_tokens=resp.usage.prompt_tokens or 0,
                    completion_tokens=resp.usage.completion_tokens or 0,
                )

            try:
                return _parse_json(content, required_keys), usage
            except json.JSONDecodeError:
                print(f"[JSON PARSE FAILED] model={settings.OPENROUTER_MODEL}")
                print(f"Raw content (first 500 chars): {content[:500]}")
                raise

        except RateLimitError as e:
            last_error = e
            wait = 10 * (attempt + 1)
            if attempt < max_retries:
                print(f"[openrouter rate limited] attempt {attempt + 1}/{max_retries + 1}, waiting {wait}s")
                await asyncio.sleep(wait)
            continue

        except json.JSONDecodeError as e:
            last_error = e
            last_error_was_empty_response = True
            wait = 3 * (attempt + 1)
            if attempt < max_retries:
                print(f"[openrouter malformed JSON] attempt {attempt + 1}/{max_retries + 1}, retrying in {wait}s")
                await asyncio.sleep(wait)
            continue

        except ValueError as e:
            if "OpenRouter returned no" not in str(e):
                raise
            last_error = e
            last_error_was_empty_response = True
            wait = 5 * (attempt + 1)
            if attempt < max_retries:
                print(f"[openrouter empty response] attempt {attempt + 1}/{max_retries + 1}, waiting {wait}s")
                await asyncio.sleep(wait)
            continue

        except Exception as e:
            if not _is_transient_server_error(e):
                raise
            last_error = e
            last_error_was_empty_response = True   # not quota: surface as a generation failure
            wait = 5 * (attempt + 1)
            if attempt < max_retries:
                print(f"[provider server error] {type(e).__name__} attempt {attempt + 1}/{max_retries + 1}, waiting {wait}s")
                await asyncio.sleep(wait)
            continue

    if last_error_was_empty_response:
        raise ValueError(
            f"OpenRouter returned an empty/malformed response "
            f"{max_retries + 1} times in a row: {last_error}"
        )
    raise LLMRateLimitError(
        f"OpenRouter quota exhausted after "
        f"{max_retries + 1} attempts: {last_error}"
    )


async def generate_json_async(prompt: str, max_output_tokens: int = 1500, max_retries: int = 2, required_keys=None) -> tuple[dict, TokenUsage]:
    if settings.LLM_PROVIDER == "openrouter":
        return await _generate_openrouter_async(prompt, max_output_tokens, max_retries, required_keys)
    return await asyncio.to_thread(
        _generate_gemini, prompt, max_output_tokens, max_retries, required_keys
    )
