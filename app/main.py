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
    _state["deeplink_index"] = DeeplinkIndex(settings.DEEPLINKS_PATH)
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
    ready = "deeplink_index" in _state
    return {"status": "ok" if ready else "warming_up"}


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
