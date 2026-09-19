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
    DEEPLINK_MARGIN: float = float(os.getenv("DEEPLINK_MARGIN", "0.05"))
    BM25_SATURATION_K: float = float(os.getenv("BM25_SATURATION_K", "3.0"))

    DEEPLINKS_PATH: str = os.getenv("DEEPLINKS_PATH", "app/data/deeplinks.json")
    QUERIES_PATH: str = os.getenv("QUERIES_PATH", "app/data/queries.json")
    SIIS_RESPONSES_PATH: str = os.getenv("SIIS_RESPONSES_PATH", "app/data/siis_responses.json")

    FAST_PATH_LATENCY_TARGET_MS: int = 300


settings = Settings()
