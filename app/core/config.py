import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")  # "gemini" or "openrouter"

    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-2.0-flash")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-20b:free")

    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

    # Semantic cache tuning — the differentiator lives here
    CACHE_HIT_THRESHOLD: float = float(os.getenv("CACHE_HIT_THRESHOLD", "0.85"))
    CACHE_NEAR_MISS_THRESHOLD: float = float(os.getenv("CACHE_NEAR_MISS_THRESHOLD", "0.70"))

    # Deeplink retrieval / matching — all varied by scripts/ablation.py
    DEEPLINK_ALPHA: float = float(os.getenv("DEEPLINK_ALPHA", "0.5"))
    DEEPLINK_MIN_CONFIDENCE: float = float(os.getenv("DEEPLINK_MIN_CONFIDENCE", "0.5"))
    # SIIS relevance verification (see app/pipeline/relevance.py) — a cheap
    # pre-extraction check that the reference text plausibly addresses the
    # complaint at all, per Samsung's explicit "abstain on mismatch, don't
    # force an answer" guidance. Deliberately a LOWER bar than deeplink
    # confidence: this only needs to catch a clearly WRONG reference
    # (different domain entirely), not judge fix quality.
    SIIS_RELEVANCE_MIN_SIMILARITY: float = float(os.getenv("SIIS_RELEVANCE_MIN_SIMILARITY", "0.25"))
    DEEPLINK_MARGIN: float = float(os.getenv("DEEPLINK_MARGIN", "0.05"))
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
    QUERIES_PATH: str = os.getenv("QUERIES_PATH", "app/data/queries.json")
    SIIS_RESPONSES_PATH: str = os.getenv("SIIS_RESPONSES_PATH", "app/data/siis_responses.json")

    FAST_PATH_LATENCY_TARGET_MS: int = 300


settings = Settings()
