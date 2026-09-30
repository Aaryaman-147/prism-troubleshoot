from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.core.config import settings
from app.core.embeddings import get_embedding_model
from app.pipeline.deeplink_retrieval import DeeplinkIndex
from app.pipeline.orchestrator import run_pipeline
from app.models.schema import TroubleshootRequest, TroubleshootResponse
from app.cache.semantic_cache import cache

from fastapi.middleware.cors import CORSMiddleware

_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm the embedding model and build the deeplink index ONCE at startup —
    # never per-request, or the fast-path latency target is unreachable.
    get_embedding_model()
    index = DeeplinkIndex(settings.DEEPLINKS_PATH)
    _state["deeplink_index"] = index
    from app.cache.warm import warm_cache
    validation_uris = {(v.get("validation") or {}).get("deeplink") for v in index.catalog_by_uri.values()} - {None}
    _state["cache_warm"] = warm_cache(settings.CACHE_WARM_PATH, cache, set(index.catalog_by_uri), validation_uris)
    print(f"[cache warm-up] {settings.CACHE_WARM_PATH}: {_state['cache_warm']}")
    yield
    _state.clear()


app = FastAPI(title="Smart Guided Troubleshooting Engine", lifespan=lifespan)

# Frontend is a standalone HTML file (opened via file:// or a separate dev
# server), so it's a different origin from the API — without this, the
# browser blocks every fetch() call with a CORS error before it even
# reaches your endpoint. Wide open here since this is a local demo tool,
# not a public API — tighten origins if you ever deploy this for real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    # Spec: HTTP 200 {"status": "ok"} once the cache, embedding model and
    # vector index are initialized. While still starting: 503, so a load
    # balancer or the stress test knows not to send traffic yet.
    from fastapi.responses import JSONResponse
    ready = "deeplink_index" in _state
    if not ready:
        return JSONResponse(status_code=503, content={"status": "warming_up"})
    return {"status": "ok"}      # exactly the spec's body; details: GET /v1/status


@app.get("/v1/status")
async def status():
    ready = "deeplink_index" in _state
    return {"status": "ok" if ready else "warming_up",
            "catalog_entries": len(_state["deeplink_index"].catalog_by_uri) if ready else 0,
            "cache_warm": _state.get("cache_warm")}


@app.get("/v1/provider-check")
async def provider_check():
    if not settings.ENABLE_DIAGNOSTICS:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"detail": "Diagnostics disabled. Set ENABLE_DIAGNOSTICS=true in .env."})
    """One tiny LLM call FROM INSIDE the server process, plus the masked key
    it is using. Compare with scripts/check_provider.py: different
    fingerprints mean the server and your terminal see different keys."""
    from app.core.config import key_fingerprint, key_was_overridden, DOTENV_DUPLICATES, DOTENV_PATH
    from app.core.llm_client import generate_json_async
    info = {"provider": settings.LLM_PROVIDER, "base_url": settings.OPENROUTER_BASE_URL,
            "model": settings.OPENROUTER_MODEL if settings.LLM_PROVIDER == "openrouter" else settings.LLM_MODEL,
            "key": key_fingerprint(settings.OPENROUTER_API_KEY if settings.LLM_PROVIDER == "openrouter" else settings.GEMINI_API_KEY),
            "stale_environment_key_replaced_by_dotenv": key_was_overridden(),
            "dotenv_duplicate_keys": DOTENV_DUPLICATES,
            "dotenv_file": DOTENV_PATH or "(none: values come from the process environment, e.g. Docker env_file)"}
    try:
        data, usage = await generate_json_async('Return ONLY {"ok": true}', max_output_tokens=50, max_retries=0)
        info.update(ok=True, tokens=usage.prompt_tokens + usage.completion_tokens)
    except Exception as e:
        info.update(ok=False, error=f"{type(e).__name__}: {str(e)[:200]}")
    return info


@app.get("/v1/examples")
async def examples():
    """Samsung's real queries with their SIIS text, for the frontend's
    example picker (so demos use the real data, not hand-typed samples)."""
    import json as _json
    from pathlib import Path as _Path
    from app.pipeline.normalize import normalize_siis
    from app.eval.batch import _clean_query
    p = _Path(settings.SIIS_RESPONSES_PATH)
    if not p.exists():
        return []
    rows = _json.loads(p.read_text(encoding="utf-8")).get("responses") or []
    return [{"id": r.get("id"), "query": _clean_query(r.get("original_query", "")),
             "title": (r.get("siis_response") or {}).get("title", ""),
             "siis_text": normalize_siis(r.get("siis_response"))} for r in rows]


@app.get("/v1/config")
async def public_config():
    """Retrieval defaults, so the frontend's sliders start at the backend's
    calibrated values instead of hardcoded ones (a mismatch made every
    frontend request count as an override and bypass the cache)."""
    return {"alpha": settings.DEEPLINK_ALPHA, "min_confidence": settings.DEEPLINK_MIN_CONFIDENCE,
            "margin": settings.DEEPLINK_MARGIN, "retrieval_text_version": settings.RETRIEVAL_TEXT_VERSION}


@app.post("/v1/troubleshoot", response_model=TroubleshootResponse)
async def troubleshoot(req: TroubleshootRequest):
    if "deeplink_index" not in _state:
        raise HTTPException(status_code=503, detail="index still warming up")
    return await run_pipeline(req.query, req.siis_response, _state["deeplink_index"], req.retrieval_overrides)


@app.get("/v1/cache/stats")
async def cache_stats():
    """Not in the original spec — added for the demo: shows live cache-hit-rate
    growth as paraphrases get absorbed. Good for the differentiator demo."""
    return cache.stats()
