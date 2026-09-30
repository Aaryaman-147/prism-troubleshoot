"""
Suite-wide isolation. Two failures appeared only on machines with the REAL
sentence-transformers model installed: any embed() call a test didn't mock
ran the real 384-dim model and was compared against 2-dim vectors that
another test had left in the shared module-level cache. Every test now gets:
  - a fresh, empty pipeline cache (no cross-test leakage),
  - no startup cache warm-up from app/data/cache_warm.jsonl,
  - deterministic hash embeddings for the cache and relevance check,
so results are identical with or without the real model installed.
Tests that need specific embeddings still patch them locally, which
overrides these defaults.
"""
import hashlib

import numpy as np
import pytest
from unittest.mock import patch


def hash_embed(text: str) -> np.ndarray:
    """Same text -> same unit vector; different texts -> ~orthogonal."""
    seed = int(hashlib.md5(str(text).encode("utf-8")).hexdigest()[:8], 16)
    v = np.random.default_rng(seed).standard_normal(32)
    return v / np.linalg.norm(v)


TEST_SETTINGS = {
    "DEEPLINK_ALPHA": 0.75, "DEEPLINK_MIN_CONFIDENCE": 0.6, "DEEPLINK_MARGIN": 0.08,
    "RETRIEVAL_TEXT_VERSION": "v1", "UNMATCHED_AUTO_POLICY": "hybrid",
    "SIIS_RELEVANCE_MIN_SIMILARITY": 0.32, "GROUNDING_MIN_ACTION_SUPPORT": 0.0,
    "SCORE_MODE": "evidence", "CACHE_SEED_HOLDOUT": 0, "REPAIR_TIME_BUDGET_MS": 6000, "LLM_JSON_MODE": True, "LLM_DISABLE_THINKING": True,
    "LLM_PROVIDER": "openrouter", "OPENROUTER_BASE_URL": "https://integrate.api.nvidia.com/v1",
    "CACHE_HIT_THRESHOLD": 0.75, "CACHE_HIT_THRESHOLD_WITH_SIIS": 0.90, "ENABLE_DIAGNOSTICS": True,
}


@pytest.fixture(autouse=True)
def _isolate_pipeline(monkeypatch):
    from app.cache.semantic_cache import SemanticCache
    from app.core.config import settings
    from app.pipeline import orchestrator
    # Tests must not depend on the developer's .env: pin every tunable to
    # the calibrated code defaults. (A local GROUNDING_MIN_ACTION_SUPPORT=0.5
    # and margin change made 2 tests fail on one machine only.)
    for name, value in TEST_SETTINGS.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(settings, "CACHE_WARM_PATH", "")
    monkeypatch.setattr(orchestrator, "cache", SemanticCache())
    async def _no_network(*a, **k):
        raise RuntimeError("network disabled in tests -- patch generate_json_async locally")
    # The description correction loop calls the real LLM; tests must never
    # spend real provider credits by accident.
    with patch("app.cache.semantic_cache.embed", side_effect=hash_embed), \
         patch("app.pipeline.relevance.embed", side_effect=hash_embed), \
         patch("app.pipeline.orchestrator.generate_json_async", side_effect=_no_network), \
         patch("app.pipeline.language.generate_json_async", side_effect=_no_network):
        yield
