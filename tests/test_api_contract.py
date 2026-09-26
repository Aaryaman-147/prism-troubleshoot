"""
Tests for the FastAPI HTTP contract itself (app/main.py) — a gap the rest
of the suite doesn't cover, since every other test calls pipeline code
directly in Python rather than through the actual HTTP layer. These use
FastAPI's TestClient, which runs requests through the real ASGI app
(routing, validation, status codes) without needing a live server.

Run with: pytest tests/test_api_contract.py -v
"""
import numpy as np
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.core.llm_client import TokenUsage


def fake_embed(text):
    return np.array([1.0, 0.0])


def fake_embed_batch(texts):
    return np.array([[1.0, 0.0] for _ in texts])


@pytest.fixture
def client(tmp_path):
    """
    Builds a TestClient against a real (tiny, valid) catalog file rather
    than the project's actual placeholder data, so this test file doesn't
    silently break if app/data/deeplinks.json changes shape later (e.g.
    once the real Samsung catalog replaces it).
    """
    catalog_path = tmp_path / "tiny_catalog.json"
    catalog_path.write_text(
        '[{"deeplink": "bixby://masked/act/test", "description": "test entry"}]'
    )

    with patch("app.core.config.settings.DEEPLINKS_PATH", str(catalog_path)), \
         patch("app.pipeline.deeplink_retrieval.embed", side_effect=fake_embed), \
         patch("app.pipeline.deeplink_retrieval.embed_batch", side_effect=fake_embed_batch), \
         patch("app.cache.semantic_cache.embed", side_effect=fake_embed), \
         patch("app.core.embeddings.get_embedding_model", return_value=None):
        from app.main import app
        with TestClient(app) as test_client:
            yield test_client


class TestHealthEndpoint:
    def test_health_returns_ok_once_warmed_up(self, client):
        """TestClient's context manager runs the lifespan startup hook
        before any request, so by the time we get here the index should
        already be loaded."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestTroubleshootEndpointValidation:
    def test_missing_query_field_returns_422_not_500(self, client):
        """A malformed request body must fail cleanly at the validation
        layer, not reach the pipeline and crash."""
        resp = client.post("/v1/troubleshoot", json={})
        assert resp.status_code == 422

    def test_wrong_type_for_query_returns_422(self, client):
        resp = client.post("/v1/troubleshoot", json={"query": 12345})
        assert resp.status_code == 422

    def test_extra_unexpected_field_does_not_break_request(self, client):
        """Pydantic's default behavior ignores unknown fields — this pins
        that behavior so a client accidentally sending extra data doesn't
        cause a surprise failure."""
        with patch("app.pipeline.orchestrator.enrich_query_async") as mock_enrich, \
             patch("app.pipeline.orchestrator.extract_structure_async") as mock_extract:
            async def fake_enrich(q):
                return {"canonical_query": q, "query_variations": []}, TokenUsage()
            async def fake_extract(q, r):
                return {"contexts": [], "fallback": "no_match"}, TokenUsage()
            mock_enrich.side_effect = fake_enrich
            mock_extract.side_effect = fake_extract

            resp = client.post("/v1/troubleshoot", json={
                "query": "test complaint",
                "unexpected_field": "should be ignored, not crash",
            })
            assert resp.status_code == 200

    def test_malformed_json_body_returns_422(self, client):
        resp = client.post(
            "/v1/troubleshoot",
            content="{not valid json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422


class TestTroubleshootEndpointHappyPath:
    def test_valid_request_returns_200_with_expected_shape(self, client):
        with patch("app.pipeline.orchestrator.enrich_query_async") as mock_enrich, \
             patch("app.pipeline.orchestrator.extract_structure_async") as mock_extract:
            async def fake_enrich(q):
                return {"canonical_query": q, "query_variations": [q]}, TokenUsage()
            async def fake_extract(q, r):
                return {"contexts": [], "fallback": "no_match"}, TokenUsage()
            mock_enrich.side_effect = fake_enrich
            mock_extract.side_effect = fake_extract

            resp = client.post("/v1/troubleshoot", json={
                "query": "screen flickers and battery dies fast",
            })
            assert resp.status_code == 200
            body = resp.json()
            # Pin the response contract so a schema refactor can't
            # silently drop a field the frontend depends on.
            assert "query" in body
            assert "response" in body
            assert "meta" in body
            assert "latency_ms" in body["meta"]
            assert "cache_hit" in body["meta"]

    def test_response_never_leaks_a_raw_500_on_pipeline_exception(self, client):
        """
        Regression test for the exact class of bug hit during development
        (a raw TypeError from an LLM client bubbling up as an unhandled
        500). The orchestrator is supposed to catch this internally and
        degrade to a fallback response — this confirms that contract holds
        all the way through the real HTTP layer, not just in isolation.
        """
        with patch("app.pipeline.orchestrator.enrich_query_async") as mock_enrich, \
             patch("app.pipeline.orchestrator.extract_structure_async") as mock_extract:
            async def raises(*a, **kw):
                raise TypeError("simulated 'NoneType is not subscriptable' class of bug")
            mock_enrich.side_effect = raises
            mock_extract.side_effect = raises

            resp = client.post("/v1/troubleshoot", json={"query": "anything"})
            assert resp.status_code == 200, (
                "An internal pipeline exception must degrade to a clean "
                "fallback response, not surface as a raw 500"
            )
            assert resp.json()["response"]["fallback"] is not None


class TestCacheStatsEndpoint:
    def test_cache_stats_returns_valid_shape_when_empty(self, client):
        resp = client.get("/v1/cache/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert "num_clusters" in body
        assert "total_paraphrases_absorbed" in body
