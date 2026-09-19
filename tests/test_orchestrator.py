"""
Integration tests for the async pipeline orchestrator
(app/pipeline/orchestrator.py).

These exercise the whole cold path and fast path end-to-end with the two LLM
calls mocked out — so they run fully offline, need no API keys, and cost no
free-tier quota. That matters: the real pipeline is the one thing that has
only ever been verified by burning rate-limited manual calls.

Run with:  pytest tests/test_orchestrator.py -v
"""
import asyncio
import time

import numpy as np
import pytest
from unittest.mock import patch

from app.cache.semantic_cache import SemanticCache
from app.core.llm_client import LLMRateLimitError
from app.models.schema import ContextDeeplinkResponse
from app.pipeline import orchestrator


def fake_embed(text: str) -> np.ndarray:
    """Deterministic keyword-presence pseudo-embedding, same trick as
    tests/test_cache.py — keeps these tests instant and model-free."""
    vocab = ["screen", "flicker", "battery", "dies", "fast", "drain",
             "display", "glitch", "quickly", "camera", "crash"]
    words = text.lower().split()
    vec = np.array([
        1.0 if any(v in w or w in v for w in words) else 0.0
        for v in vocab
    ])
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


class FakeDeeplinkIndex:
    """Stands in for DeeplinkIndex without loading the catalog, BM25 index or
    sentence-transformers model. Returns no match, which exercises the
    confidence-floor branch (an action simply keeps no actionableDeeplink)."""

    def __init__(self):
        self.catalog_by_uri = {}

    def search(self, query_text, top_k=1):
        return []


VALID_EXTRACTION = {
    "contexts": [
        {
            "goal": "Follow these steps to perform this Display Troubleshooting",
            "title": "Screen flicker fix",
            "score": 0.82,
            "actions": [
                {
                    "actionName": "Display Settings",
                    "description": "It will reduce visible screen flickering",
                    "category": "auto",
                    "stepGroups": [{"steps": ["Open Settings", "Tap Display"]}],
                },
                {
                    "actionName": "Factory Reset",
                    "description": "It will erase everything and restore defaults",
                    "category": "critical",
                    "stepGroups": [{"steps": ["Open Settings", "Tap Reset"]}],
                },
            ],
        }
    ]
}

VALID_ENRICHMENT = {
    "canonical_query": "screen flicker display glitch",
    "query_variations": ["screen keeps flickering", "display glitching"],
}


@pytest.fixture
def fresh_cache():
    """Swap the module-level singleton for a clean instance per test, so
    tests can't leak cached clusters into each other."""
    with patch("app.cache.semantic_cache.embed", side_effect=fake_embed):
        c = SemanticCache(hit_threshold=0.85, near_miss_threshold=0.5)
        with patch.object(orchestrator, "cache", c):
            yield c


@pytest.mark.asyncio
async def test_cold_path_returns_validated_ordered_plan_and_caches_it(fresh_cache):
    """Happy path: both LLM calls succeed -> plan is validated, actions are
    ordered auto-before-critical, and the result lands in the cache."""
    with patch("app.cache.semantic_cache.embed", side_effect=fake_embed), \
         patch.object(orchestrator, "enrich_query_async", return_value=VALID_ENRICHMENT), \
         patch.object(orchestrator, "extract_structure_async", return_value=VALID_EXTRACTION):

        result = await orchestrator.run_pipeline(
            "my screen keeps flickering", "reference text here", FakeDeeplinkIndex()
        )

    assert result.meta.cache_hit is False
    assert result.response.fallback is None
    assert len(result.response.contexts) == 1
    # Ordering contract: destructive actions must come last.
    categories = [a.category.value for a in result.response.contexts[0].actions]
    assert categories == ["auto", "critical"]
    assert result.query_variations == VALID_ENRICHMENT["query_variations"]
    assert fresh_cache.stats()["num_clusters"] == 1


@pytest.mark.asyncio
async def test_paraphrase_hits_cache_without_calling_the_llm(fresh_cache):
    """The core differentiator, end-to-end: a paraphrase of an already-cached
    query must be served from the cache with cache_hit=True and must NOT
    touch either LLM call."""
    with patch("app.cache.semantic_cache.embed", side_effect=fake_embed):
        fresh_cache.insert_new_cluster(
            "screen flicker display glitch",
            ContextDeeplinkResponse(**VALID_EXTRACTION),
        )

    with patch("app.cache.semantic_cache.embed", side_effect=fake_embed), \
         patch.object(orchestrator, "enrich_query_async") as mock_enrich, \
         patch.object(orchestrator, "extract_structure_async") as mock_extract:

        result = await orchestrator.run_pipeline(
            "display glitch screen flickering", None, FakeDeeplinkIndex()
        )

        mock_enrich.assert_not_called()
        mock_extract.assert_not_called()

    assert result.meta.cache_hit is True
    assert result.meta.model == "cache"
    assert result.meta.cache_similarity >= 0.85


@pytest.mark.asyncio
async def test_enrichment_failure_does_not_discard_a_good_extraction(fresh_cache):
    """asyncio.gather(return_exceptions=True) contract: one call blowing up
    (e.g. Gemini safety-filtering a response into a ValueError) must not
    cancel or throw away the other. The plan still comes back; enrichment
    degrades to using the raw query as its own canonical form."""
    async def boom(*args, **kwargs):
        raise ValueError("Gemini returned no text. finish_reason=SAFETY")

    with patch("app.cache.semantic_cache.embed", side_effect=fake_embed), \
         patch.object(orchestrator, "enrich_query_async", side_effect=boom), \
         patch.object(orchestrator, "extract_structure_async", return_value=VALID_EXTRACTION):

        result = await orchestrator.run_pipeline(
            "my screen keeps flickering", "reference text here", FakeDeeplinkIndex()
        )

    assert result.response.fallback is None
    assert len(result.response.contexts) == 1
    assert result.query_variations == ["my screen keeps flickering"]


@pytest.mark.asyncio
async def test_rate_limited_extraction_returns_fallback_and_is_never_cached(fresh_cache):
    """Regression guard for the fallback-poisoning bug, now at pipeline level:
    a rate-limited extraction must surface as a fallback AND must leave the
    cache empty, so the failure doesn't become the permanent answer."""
    async def rate_limited(*args, **kwargs):
        raise LLMRateLimitError("quota exhausted after 3 attempts")

    with patch("app.cache.semantic_cache.embed", side_effect=fake_embed), \
         patch.object(orchestrator, "enrich_query_async", return_value=VALID_ENRICHMENT), \
         patch.object(orchestrator, "extract_structure_async", side_effect=rate_limited):

        result = await orchestrator.run_pipeline(
            "my screen keeps flickering", "reference text here", FakeDeeplinkIndex()
        )

    assert result.response.fallback == "rate_limited"
    assert result.response.contexts == []
    assert fresh_cache.stats()["num_clusters"] == 0


@pytest.mark.asyncio
async def test_enrichment_and_extraction_actually_run_concurrently(fresh_cache):
    """The whole point of the async conversion. Two 0.3s calls run in
    parallel should finish in ~0.3s, not ~0.6s. Asserting well under the
    sequential total keeps this from being flaky on a slow machine."""
    async def slow_enrich(*args, **kwargs):
        await asyncio.sleep(0.3)
        return VALID_ENRICHMENT

    async def slow_extract(*args, **kwargs):
        await asyncio.sleep(0.3)
        return VALID_EXTRACTION

    with patch("app.cache.semantic_cache.embed", side_effect=fake_embed), \
         patch.object(orchestrator, "enrich_query_async", side_effect=slow_enrich), \
         patch.object(orchestrator, "extract_structure_async", side_effect=slow_extract):

        t0 = time.perf_counter()
        result = await orchestrator.run_pipeline(
            "my screen keeps flickering", "reference text here", FakeDeeplinkIndex()
        )
        elapsed = time.perf_counter() - t0

    assert result.response.fallback is None
    assert elapsed < 0.5, (
        f"took {elapsed:.2f}s — the two LLM calls appear to be running "
        f"sequentially, not via asyncio.gather"
    )


@pytest.mark.asyncio
async def test_identical_query_resubmitted_is_a_cache_hit(fresh_cache):
    """
    Regression test for the bug that broke the live demo: the cache stored the
    centroid of the ENRICHED canonical query while lookup() embeds the RAW
    user query, so resubmitting a byte-identical complaint scored ~0.81 and
    missed the 0.85 threshold — a cold LLM call for a question already
    answered. If this test fails, the paraphrase hit rate (a scored metric)
    is near zero no matter what the cache stats panel claims.
    """
    with patch("app.cache.semantic_cache.embed", side_effect=fake_embed), \
         patch.object(orchestrator, "enrich_query_async", return_value=VALID_ENRICHMENT), \
         patch.object(orchestrator, "extract_structure_async", return_value=VALID_EXTRACTION):

        first = await orchestrator.run_pipeline(
            "screen flicker battery drain", "reference text here", FakeDeeplinkIndex()
        )
        assert first.meta.cache_hit is False

        second = await orchestrator.run_pipeline(
            "screen flicker battery drain", "reference text here", FakeDeeplinkIndex()
        )

    assert second.meta.cache_hit is True, (
        f"identical query missed the cache at similarity "
        f"{second.meta.cache_similarity} — centroid seeding is broken"
    )
    assert fresh_cache.stats()["num_clusters"] == 1


@pytest.mark.asyncio
async def test_unrelated_complaint_still_misses_a_seeded_cluster(fresh_cache):
    """
    Guard on the other side of the seeding fix. Seeding a cluster with several
    phrasings and scoring max-over-members makes hits easier by design — this
    asserts it did not make FALSE hits easier, which would be far worse than
    the original miss: an unrelated complaint served a cached plan for a
    different issue entirely.
    """
    with patch("app.cache.semantic_cache.embed", side_effect=fake_embed), \
         patch.object(orchestrator, "enrich_query_async", return_value=VALID_ENRICHMENT), \
         patch.object(orchestrator, "extract_structure_async", return_value=VALID_EXTRACTION):

        await orchestrator.run_pipeline(
            "screen flicker battery drain", "reference text here", FakeDeeplinkIndex()
        )
        result = await orchestrator.run_pipeline(
            "camera crash", "reference text here", FakeDeeplinkIndex()
        )

    assert result.meta.cache_hit is False
    assert fresh_cache.stats()["num_clusters"] == 2
