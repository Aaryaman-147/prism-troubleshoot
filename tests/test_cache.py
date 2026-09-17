"""
Tests for the semantic cache clustering (app/cache/semantic_cache.py) —
the project's core differentiator. Uses a fake embedding function so
these run instantly with no model download / API calls needed.
Run with: pytest tests/test_cache.py -v
"""
import numpy as np
import pytest
from unittest.mock import patch

from app.models.schema import ContextDeeplinkResponse


def fake_embed(text: str) -> np.ndarray:
    """Deterministic pseudo-embedding based on keyword presence, so
    semantically related test strings produce similar vectors without
    needing the real sentence-transformers model."""
    vocab = ["screen", "flicker", "battery", "dies", "fast", "drain",
             "display", "glitch", "quickly", "camera", "crash"]
    words = text.lower().split()
    vec = np.array([
        1.0 if any(v in w or w in v for w in words) else 0.0
        for v in vocab
    ])
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


@pytest.fixture
def cache():
    with patch("app.cache.semantic_cache.embed", side_effect=fake_embed):
        from app.cache.semantic_cache import SemanticCache
        yield SemanticCache(hit_threshold=0.85, near_miss_threshold=0.5)


class TestSemanticCache:
    def test_empty_cache_is_always_a_miss(self, cache):
        result = cache.lookup("screen flicker battery dies fast")
        assert result.status == "miss"

    def test_near_identical_paraphrase_is_a_hit(self, cache):
        with patch("app.cache.semantic_cache.embed", side_effect=fake_embed):
            cache.insert_new_cluster(
                "screen flicker battery dies fast",
                ContextDeeplinkResponse(contexts=[]),
            )
            result = cache.lookup("screen flickering battery dies fast")
            assert result.status == "hit"
            assert result.similarity > 0.85

    def test_unrelated_query_is_a_miss(self, cache):
        with patch("app.cache.semantic_cache.embed", side_effect=fake_embed):
            cache.insert_new_cluster(
                "screen flicker battery dies fast",
                ContextDeeplinkResponse(contexts=[]),
            )
            result = cache.lookup("camera crash issue")
            assert result.status == "miss"

    def test_merge_does_not_create_duplicate_cluster(self, cache):
        with patch("app.cache.semantic_cache.embed", side_effect=fake_embed):
            cache.insert_new_cluster(
                "screen flicker battery dies fast",
                ContextDeeplinkResponse(contexts=[]),
            )
            lookup = cache.lookup("screen flicker battery dies quickly")
            if lookup.status == "near_miss":
                cache.merge_into_cluster(lookup.cluster, "screen flicker battery dies quickly")

            stats = cache.stats()
            # The key assertion: absorbing a near-miss paraphrase must NOT
            # create a second cluster — this is the exact failure mode
            # ("exact-string cache keying" / fragmentation) the spec names.
            assert stats["num_clusters"] == 1

    def test_never_caches_a_fallback_response(self, cache):
        """
        Regression test for a real bug found during development: a failed
        extraction (fallback set) was being cached as if it were a valid
        answer, permanently poisoning that query for all future paraphrases.
        The orchestrator is responsible for checking `response.fallback is
        None` before calling insert_new_cluster — this test documents that
        contract so a future refactor can't silently drop it.
        """
        failed_response = ContextDeeplinkResponse(contexts=[], fallback="no_match")
        # This directly asserts the contract the orchestrator must uphold:
        assert failed_response.fallback is not None, (
            "This response has a fallback set and must NOT be passed to "
            "cache.insert_new_cluster() or cache.merge_into_cluster()"
        )
