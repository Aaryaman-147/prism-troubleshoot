"""
Semantic cache with paraphrase clustering.

Why this exists: the spec explicitly calls out "exact-string cache keying"
as a common pitfall — raw string/hash keys miss on unseen paraphrases,
tanking both latency (P95 <= 300ms target) and the semantic-paraphrase
hit-rate metric (target >= 80%).

Design:
  - Each cache entry is a CLUSTER, not a flat key: a centroid embedding +
    a validated Goal payload + a running count of merged paraphrases.
  - New query -> embed -> compare against all centroids (cosine sim).
      similarity >= HIT_THRESHOLD      -> cache hit, serve immediately
      NEAR_MISS <= similarity < HIT    -> run full pipeline once, then
                                           MERGE result into nearest
                                           cluster (update centroid via
                                           running mean) instead of
                                           creating a near-duplicate entry
      similarity < NEAR_MISS           -> genuinely new cluster
  - This directly prevents cache fragmentation (many near-identical
    clusters for trivial rephrasings) while still being correct: it
    never serves a cached answer without a similarity check.

This is intentionally in-memory for the hackathon timeline. Swapping the
store for Redis/FAISS later is a drop-in change to `_load`/`_persist` and
the linear scan below, not a redesign.
"""
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from app.core.config import settings
from app.core.embeddings import embed, cosine_sim
from app.models.schema import ContextDeeplinkResponse


@dataclass
class CacheCluster:
    cluster_id: str
    centroid: np.ndarray
    payload: ContextDeeplinkResponse
    canonical_query: str
    merged_count: int = 1
    paraphrases_seen: list[str] = field(default_factory=list)


@dataclass
class CacheLookupResult:
    status: str  # "hit" | "near_miss" | "miss"
    cluster: Optional[CacheCluster]
    similarity: float
    lookup_ms: float


class SemanticCache:
    def __init__(
        self,
        hit_threshold: float = settings.CACHE_HIT_THRESHOLD,
        near_miss_threshold: float = settings.CACHE_NEAR_MISS_THRESHOLD,
    ):
        self.hit_threshold = hit_threshold
        self.near_miss_threshold = near_miss_threshold
        self._clusters: dict[str, CacheCluster] = {}

    def lookup(self, query: str) -> CacheLookupResult:
        t0 = time.perf_counter()
        vec = embed(query)

        best_sim = -1.0
        best_cluster: Optional[CacheCluster] = None
        for cluster in self._clusters.values():
            sim = cosine_sim(vec, cluster.centroid)
            if sim > best_sim:
                best_sim = sim
                best_cluster = cluster

        elapsed_ms = (time.perf_counter() - t0) * 1000

        if best_cluster is not None and best_sim >= self.hit_threshold:
            return CacheLookupResult("hit", best_cluster, best_sim, elapsed_ms)
        if best_cluster is not None and best_sim >= self.near_miss_threshold:
            return CacheLookupResult("near_miss", best_cluster, best_sim, elapsed_ms)
        return CacheLookupResult("miss", None, best_sim, elapsed_ms)

    def insert_new_cluster(self, query: str, payload: ContextDeeplinkResponse) -> CacheCluster:
        vec = embed(query)
        cluster = CacheCluster(
            cluster_id=str(uuid.uuid4()),
            centroid=vec,
            payload=payload,
            canonical_query=query,
            paraphrases_seen=[query],
        )
        self._clusters[cluster.cluster_id] = cluster
        return cluster

    def merge_into_cluster(self, cluster: CacheCluster, query: str) -> None:
        """
        Absorb a near-miss paraphrase into an existing cluster by updating
        its centroid as a running mean, re-normalized. This is what keeps
        the cache from fragmenting into many near-duplicate entries for
        trivial rephrasings — the exact failure mode named in the spec.
        """
        vec = embed(query)
        n = cluster.merged_count
        new_centroid = (cluster.centroid * n + vec) / (n + 1)
        norm = np.linalg.norm(new_centroid)
        cluster.centroid = new_centroid / norm if norm > 0 else new_centroid
        cluster.merged_count += 1
        cluster.paraphrases_seen.append(query)

    def stats(self) -> dict:
        return {
            "num_clusters": len(self._clusters),
            "total_paraphrases_absorbed": sum(
                c.merged_count for c in self._clusters.values()
            ),
            "clusters": [
                {
                    "cluster_id": c.cluster_id,
                    "canonical_query": c.canonical_query,
                    "merged_count": c.merged_count,
                    "paraphrases_seen": c.paraphrases_seen,
                }
                for c in self._clusters.values()
            ],
        }


# Module-level singleton — shared across requests within the process.
cache = SemanticCache()
