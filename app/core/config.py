import os
from dotenv import load_dotenv

import re as _re
from pathlib import Path as _Path

from dotenv import dotenv_values, find_dotenv

# .env overrides stale terminal variables (a leftover OPENROUTER_API_KEY from
# `set`/`setx` silently beat .env before) -- EXCEPT placeholder values. The
# old Dockerfile baked .env.example in as /app/.env; blindly overriding let
# its "your_key_here" / LLM_PROVIDER=gemini replace the real values Docker
# passes in via env_file, so the server called Gemini with a fake key.
_ENV_BEFORE = {k: os.environ.get(k) for k in ("OPENROUTER_API_KEY", "GEMINI_API_KEY", "LLM_PROVIDER")}
# PRISM_NO_DOTENV=1 ignores .env entirely (tests/CI): every tunable then
# comes from the calibrated defaults below, proving nothing depends on .env.
DOTENV_PATH = "" if os.getenv("PRISM_NO_DOTENV") == "1" else find_dotenv()
_PLACEHOLDER = _re.compile(r"your[_-]?\w*[_-]?(key|here)|^changeme$|^xxx+$|^<.*>$", _re.I)


def _is_placeholder(v: str) -> bool:
    return bool(v) and bool(_PLACEHOLDER.search(v.strip()))


def apply_dotenv(path: str) -> None:
    """Load `path` into os.environ: real values override stale ones; a file
    containing placeholders (a copy of .env.example) never overrides values
    the environment already provides."""
    values = dotenv_values(path)
    example_copy = any(_is_placeholder(v or "") for v in values.values())
    for k, v in values.items():
        if v is None:
            continue
        if os.environ.get(k) and (_is_placeholder(v) or example_copy):
            continue
        os.environ[k] = v


if DOTENV_PATH:
    apply_dotenv(DOTENV_PATH)


def _dotenv_duplicates(path: str = ".env") -> list[str]:
    try:
        keys = [m.group(1) for m in (_re.match(r"^\s*([A-Z0-9_]+)\s*=", l)
                for l in _Path(path).read_text(encoding="utf-8").splitlines()) if m]
    except OSError:
        return []
    return sorted({k for k in keys if keys.count(k) > 1})


DOTENV_DUPLICATES = _dotenv_duplicates(DOTENV_PATH) if DOTENV_PATH else []
if DOTENV_DUPLICATES:
    print(f"[config] WARNING: .env defines these keys more than once (last one wins): {DOTENV_DUPLICATES}")


def key_fingerprint(key: str) -> str:
    """Masked key for diagnostics: first 6 + last 4 characters."""
    return "(empty)" if not key else f"...{key[-4:]}" if len(key) > 12 else "(short)"


def key_was_overridden(name: str = "OPENROUTER_API_KEY") -> bool:
    before = _ENV_BEFORE.get(name)
    return before is not None and before != os.environ.get(name)


class Settings:
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")  # "gemini" or "openrouter"

    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-2.0-flash")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    # Any OpenAI-compatible endpoint works through the "openrouter" provider:
    #   OpenRouter: https://openrouter.ai/api/v1 (default)
    #   NVIDIA:     https://integrate.api.nvidia.com/v1  (key starts nvapi-,
    #               model e.g. nvidia/nemotron-3-super-120b-a12b)
    OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    # Some OpenAI-compatible hosts reject response_format=json_object with a
    # 400. Set LLM_JSON_MODE=false for those; _clean_json_text still
    # extracts the JSON object from free-form output.
    # Nemotron 3 on NVIDIA's API reasons by default; off = faster, cleaner JSON.
    # Appendix C: cost = (prompt tokens + completion tokens) x rate. Rates are
    # USD per 1M tokens; 0 for NVIDIA's free tier. Set a list price to report
    # what the same traffic would cost on a paid endpoint.
    LLM_PRICE_PER_MTOK_INPUT: float = float(os.getenv("LLM_PRICE_PER_MTOK_INPUT", "0"))
    LLM_PRICE_PER_MTOK_OUTPUT: float = float(os.getenv("LLM_PRICE_PER_MTOK_OUTPUT", "0"))
    # Per-call timeout (s). A degenerate response (hundreds of blank lines up to
    # the output limit) took 104 s before failing JSON parsing; timing out and
    # retrying (APITimeoutError is treated as transient) caps that tail.
    LLM_TIMEOUT_S: float = float(os.getenv("LLM_TIMEOUT_S", "30"))
    LLM_DISABLE_THINKING: bool = os.getenv("LLM_DISABLE_THINKING", "true").lower() == "true"
    LLM_JSON_MODE: bool = os.getenv("LLM_JSON_MODE", "true").lower() == "true"
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-20b:free")

    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

    # Semantic cache tuning — the differentiator lives here
    CACHE_HIT_THRESHOLD: float = float(os.getenv("CACHE_HIT_THRESHOLD", "0.75"))  # all measured results use 0.75 (100% paraphrase hits)
    CACHE_NEAR_MISS_THRESHOLD: float = float(os.getenv("CACHE_NEAR_MISS_THRESHOLD", "0.70"))

    # Deeplink retrieval / matching — all varied by scripts/ablation.py
    DEEPLINK_ALPHA: float = float(os.getenv("DEEPLINK_ALPHA", "0.75"))
    DEEPLINK_MIN_CONFIDENCE: float = float(os.getenv("DEEPLINK_MIN_CONFIDENCE", "0.6"))
    # SIIS relevance verification (see app/pipeline/relevance.py) — a cheap
    # pre-extraction check that the reference text plausibly addresses the
    # complaint at all, per Samsung's explicit "abstain on mismatch, don't
    # force an answer" guidance. Deliberately a LOWER bar than deeplink
    # confidence: this only needs to catch a clearly WRONG reference
    # (different domain entirely), not judge fix quality.
    SIIS_RELEVANCE_MIN_SIMILARITY: float = float(os.getenv("SIIS_RELEVANCE_MIN_SIMILARITY", "0.32"))  # calibrated: keeps 20/20 genuine SIIS pairs
    DEEPLINK_MARGIN: float = float(os.getenv("DEEPLINK_MARGIN", "0.08"))  # 101-probe calibration: every top config uses 0.08
    # What to do with an "auto" action when no catalog deeplink is confident
    # enough. Samsung (Theme-2 meeting): "If no relevant deeplink exists in
    # the supplied deeplink file, set it to None/null and mark the action as
    # manual." -> default "manual_null". The spec PDF separately describes a
    # reserved dummy_positive placeholder; "dummy_positive" restores that
    # behaviour if Samsung confirms it's still wanted. The two sources
    # conflict -- the meeting guidance is newer and more explicit.
    # Samsung's real catalog resolves the earlier conflict: its dummy_positive
    # entry says "Use only when a step opens a Settings screen and no other
    # catalog entry matches it. Write description and message yourself", and
    # sample_output.json shows a non-Settings action (service center) as
    # manual + null. "hybrid" applies exactly that split.
    # Options: hybrid | manual_null | dummy_positive
    # Defaults above come from scripts/calibrate_retrieval.py on Samsung's
    # real 578-entry catalog: alpha 0.75 / floor 0.6 -> 22/26 correct, 0 wrong
    # (margin 0.02 scores identically to 0.0 but keeps the ambiguity net).
    # Retrieval text v2: search text includes the catalog's validation key
    # (the precise setting name -- messages are often generic, e.g. "Enable
    # Adaptive Display" is shared by 7 different settings) and drops
    # boilerplate ("... via device Settings on the device", bare "Open
    # Settings" steps). v1 = original text. Compare both with
    # scripts/calibrate_retrieval.py before relying on either.
    RETRIEVAL_TEXT_VERSION: str = os.getenv("RETRIEVAL_TEXT_VERSION", "v1")  # v1 measured 23 vs 22 correct
    # Step grounding: 0 = measure only. >0 = drop actions whose fraction of
    # SIIS-supported steps is below this. Set only after reviewing the
    # measured rate in metrics.md.
    GROUNDING_MIN_ACTION_SUPPORT: float = float(os.getenv("GROUNDING_MIN_ACTION_SUPPORT", "0.5"))  # team decision after manual review
    # Skip the LLM description-repair calls once a request has used this much
    # time; deterministic fallbacks (shorten / "help" / salvage) still apply.
    # Paraphrases per plan kept OUT of the cache. 0 in production (store every
    # phrasing = best recall). batch_run sets it to 2 while measuring, so its
    # paraphrase pass tests genuinely unseen phrasings.
    # When the caller supplies a SIIS reference, a cached plan is reused only
    # if it was grounded in that same document AND the complaint is a close
    # paraphrase (stricter than CACHE_HIT_THRESHOLD, which serves reference-less
    # lookups). An external audit showed a warmed plan served for a different
    # document; 4 of Samsung's 20 queries hit sibling plans at 0.79-0.86.
    CACHE_HIT_THRESHOLD_WITH_SIIS: float = float(os.getenv("CACHE_HIT_THRESHOLD_WITH_SIIS", "0.90"))  # real-model check: max distinct-query pair 0.858
    CACHE_SEED_HOLDOUT: int = int(os.getenv("CACHE_SEED_HOLDOUT", "0"))
    # /v1/provider-check makes a live LLM call and /v1/cache/stats can list
    # queries: off unless explicitly enabled for local debugging.
    ENABLE_DIAGNOSTICS: bool = os.getenv("ENABLE_DIAGNOSTICS", "false").lower() == "true"
    REPAIR_TIME_BUDGET_MS: int = int(os.getenv("REPAIR_TIME_BUDGET_MS", "6000"))
    # Plan score. "llm": the model's self-rating (in practice nearly always
    # 0.85). "evidence": that rating scaled by how much of the plan the SIIS
    # text supports: score x (0.5 + 0.5 x grounded-step fraction). A fully
    # grounded plan keeps its score; a half-grounded one loses 25%.
    SCORE_MODE: str = os.getenv("SCORE_MODE", "evidence")
    UNMATCHED_AUTO_POLICY: str = os.getenv("UNMATCHED_AUTO_POLICY", "hybrid")
    BM25_SATURATION_K: float = float(os.getenv("BM25_SATURATION_K", "3.0"))

    # Number of paraphrases the enrichment stage generates per query.
    # Lowered from 9->5 during active dev to cut cold-path latency and
    # rate-limit pressure; bump it back up (e.g. 8-9) just for demo/PPT
    # recordings via .env, where richer paraphrase diversity makes the
    # cache-hit-rate story land better and you're not iterating rapidly.
    # Number of paraphrases the enrichment stage generates per query.
    # The theme spec (section 4.1, query_variations) explicitly requires
    # "8 to 10 distinct paraphrases across varied registers" -- this is a
    # SCHEMA/RULE COMPLIANCE requirement, not a tunable demo knob. Default
    # raised from 5 (an earlier dev-speed optimization, made before the
    # spec PDF was available) to 8, the low end of the required range.
    # Lower only temporarily for local iteration if quota is the bottleneck
    # -- 8 should be the value at submission time.
    ENRICHMENT_PARAPHRASE_COUNT: int = int(os.getenv("ENRICHMENT_PARAPHRASE_COUNT", "8"))

    # LLM sampling temperature. Lower = more deterministic wording across
    # repeated identical queries (see scripts/measure_determinism_and_cache.py),
    # at some cost to paraphrase/creative diversity. 0.2 was the original
    # value; try 0.0-0.1 if the determinism check keeps showing multiple
    # distinct plan shapes and byte-closer consistency matters more than
    # wording variety for the demo/PPT.
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))

    DEEPLINKS_PATH: str = os.getenv("DEEPLINKS_PATH", "app/data/deeplinks.json")
    QUERIES_PATH: str = os.getenv("QUERIES_PATH", "app/data/input.txt")
    SIIS_RESPONSES_PATH: str = os.getenv("SIIS_RESPONSES_PATH", "app/data/siis_responses.json")

    FAST_PATH_LATENCY_TARGET_MS: int = 300

    # Pre-warmed cache (spec: "semantic lookup against pre-warmed cache
    # entries"). At startup, successful records from this results.jsonl are
    # loaded into the cache. Records whose deeplinks aren't in the current
    # catalog are skipped as stale. Missing file = no warm-up.
    CACHE_WARM_PATH: str = os.getenv("CACHE_WARM_PATH", "app/data/cache_warm.jsonl")


settings = Settings()


# Settings that change what a plan CONTAINS. A cached/pre-warmed plan made
# under different values is stale (e.g. warmed before grounding enforcement
# was switched on would still serve ungrounded actions).
_CONTENT_SETTINGS = ("GROUNDING_MIN_ACTION_SUPPORT", "UNMATCHED_AUTO_POLICY", "RETRIEVAL_TEXT_VERSION",
                     "DEEPLINK_ALPHA", "DEEPLINK_MIN_CONFIDENCE", "DEEPLINK_MARGIN", "SCORE_MODE",
                     "SIIS_RELEVANCE_MIN_SIMILARITY")


def config_fingerprint() -> str:
    import hashlib
    blob = "|".join(f"{k}={getattr(settings, k)}" for k in _CONTENT_SETTINGS)
    return hashlib.sha1(blob.encode()).hexdigest()[:10]
