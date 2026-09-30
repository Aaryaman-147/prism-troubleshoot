"""
Singleton embedding model. Loaded once at app startup (see main.py lifespan),
shared across the semantic cache and the deeplink dense-retrieval index.
Never instantiate SentenceTransformer per-request — that's a common
performance mistake that kills your fast-path latency target.
"""
from functools import lru_cache
import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import settings


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(settings.EMBEDDING_MODEL)


@lru_cache(maxsize=8192)
def _embed_cached(text: str) -> np.ndarray:
    model = get_embedding_model()
    return model.encode(text, convert_to_numpy=True, normalize_embeddings=True)


def embed(text: str) -> np.ndarray:
    """Memoized: each distinct text is encoded once. The stress test showed
    concurrent cache hits queueing behind repeated model calls."""
    return _embed_cached(text).copy()


def embed_batch(texts: list[str]) -> np.ndarray:
    model = get_embedding_model()
    return model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    # vectors are already normalized, so dot product == cosine similarity
    return float(np.dot(a, b))
