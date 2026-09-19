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

THREAD-SAFETY: the module-level `cache` singleton is shared across all
requests in the process, and the orchestrator now runs pipeline stages
concurrently (asyncio + a thread pool for the Gemini path). Without a lock,
two concurrent requests could (a) mutate `_clusters` while another thread
is iterating it in lookup() -> RuntimeError: dictionary changed size during
iteration, or (b) interleave a merge_into_cluster() running-mean update and
corrupt the centroid (lost update). All reads/writes of `_clusters` and of
cluster fields are therefore guarded by a single re-entrant lock.

The expensive part (embed()) is deliberately done OUTSIDE the lock — it is
pure and touches no shared state, so holding the lock across it would
serialize every request on the embedding model for no benefit.
"""
import threading
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
    merged_count: int = 1          # distinct user queries this cluster has served
    centroid_n: int = 1            # vectors averaged into the centroid (>= merged_count)
    members: list[np.ndarray] = field(default_factory=list)
    paraphrases_seen: list[str] = field(default_factory=list)


@dataclass
class CacheLookupResult:
    status: str  # "hit" | "near_miss" | "miss"
    cluster: Optional[CacheCluster]
    similarity: float
    lookup_ms: float


# Cap on member vectors kept per cluster. 384 floats each at MiniLM size, so
# 16 members is ~25KB per cluster — negligible, and the linear scan stays fast
# at demo scale. Swap the scan for FAISS if this ever holds thousands.
MAX_MEMBERS_PER_CLUSTER = 16


class SemanticCache:
    def __init__(
        self,
        hit_threshold: float = settings.CACHE_HIT_THRESHOLD,
        near_miss_threshold: float = settings.CACHE_NEAR_MISS_THRESHOLD,
    ):
        self.hit_threshold = hit_threshold
        self.near_miss_threshold = near_miss_threshold
        self._clusters: dict[str, CacheCluster] = {}
        # Re-entrant so a future method can call another locked method
        # without deadlocking itself.
        self._lock = threading.RLock()

    def lookup(self, query: str) -> CacheLookupResult:
        t0 = time.perf_counter()
        vec = embed(query)  # outside the lock on purpose — see module docstring

        best_sim = -1.0
        best_cluster: Optional[CacheCluster] = None
        with self._lock:
            for cluster in self._clusters.values():
                sim = self._similarity(vec, cluster)
                if sim > best_sim:
                    best_sim = sim
                    best_cluster = cluster

        elapsed_ms = (time.perf_counter() - t0) * 1000

        if best_cluster is not None and best_sim >= self.hit_threshold:
            return CacheLookupResult("hit", best_cluster, best_sim, elapsed_ms)
        if best_cluster is not None and best_sim >= self.near_miss_threshold:
            return CacheLookupResult("near_miss", best_cluster, best_sim, elapsed_ms)
        return CacheLookupResult("miss", None, best_sim, elapsed_ms)

    @staticmethod
    def _similarity(vec: np.ndarray, cluster: CacheCluster) -> float:
        """
        Score a query against a cluster as the MAX similarity over the
        cluster's member phrasings, not the similarity to its centroid.

        Centroid-only scoring was the bug behind the demo miss. A cluster
        holds several phrasings of one issue — the raw complaint, the
        canonical technical form, the generated paraphrases — and averaging
        them lands the centroid in the middle of a spread-out region, some
        distance from EVERY actual phrasing including the original complaint.
        Resubmitting the identical query scored ~0.81 against its own cluster.

        Max-over-members makes an identical query score 1.0 by construction,
        and a paraphrase score against whichever stored phrasing it happens to
        resemble most. That is what the hit threshold was calibrated for: a
        query-to-query similarity, not a query-to-average similarity.
        """
        if not cluster.members:
            return cosine_sim(vec, cluster.centroid)
        return max(cosine_sim(vec, m) for m in cluster.members)

    def insert_new_cluster(
        self,
        query: str,
        payload: ContextDeeplinkResponse,
        seed_texts: Optional[list[str]] = None,
    ) -> CacheCluster:
        """
        Create a cluster for `query`.

        `seed_texts` is what makes the cache actually hit. Previously the
        centroid was the embedding of the ENRICHED canonical query alone,
        while lookup() embeds the RAW user query — so even resubmitting the
        identical complaint compared across that gap and scored ~0.81,
        under the 0.85 hit threshold. Every paraphrase started handicapped.

        Seeding the centroid with the raw query, the canonical query and the
        enrichment stage's own query_variations places it in the middle of
        the region real paraphrases arrive from, instead of off to one side.
        Those variations are already generated and paid for on every cold
        call — this just stops throwing them away.

        Deliberately NOT fixed by lowering the hit threshold: that buys hit
        rate by making false hits likelier, and serving a confidently wrong
        cached plan is worse than an honest cold call.

        The raw query is forced to the front of the member list so that it
        survives the MAX_MEMBERS_PER_CLUSTER cap — a generated paraphrase is
        expendable, the phrasing a real user actually typed is not.
        """
        texts = [t for t in (seed_texts or [query]) if t and t.strip()]
        # De-duplicate while preserving order, so a repeated string doesn't
        # silently get extra weight in the mean.
        seen: set[str] = set()
        unique_texts = [t for t in texts if not (t in seen or seen.add(t))]

        # Raw query first — it must never be evicted by the member cap.
        if query in unique_texts:
            unique_texts.remove(query)
        unique_texts.insert(0, query)

        vecs = [embed(t) for t in unique_texts]
        centroid = np.mean(vecs, axis=0)
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm

        cluster = CacheCluster(
            cluster_id=str(uuid.uuid4()),
            centroid=centroid,
            payload=payload,
            canonical_query=query,
            centroid_n=len(vecs),
            members=vecs[:MAX_MEMBERS_PER_CLUSTER],
            paraphrases_seen=[query],
        )
        with self._lock:
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
        # The read-modify-write of centroid/merged_count must be atomic:
        # two threads merging concurrently would otherwise both read the
        # same `n`, and one update would be silently lost.
        with self._lock:
            # Weight by centroid_n (vectors actually averaged in), not
            # merged_count (queries served) — those differ once a cluster is
            # seeded from multiple texts, and using the wrong one would let a
            # single new paraphrase yank a well-established centroid.
            n = cluster.centroid_n
            new_centroid = (cluster.centroid * n + vec) / (n + 1)
            norm = np.linalg.norm(new_centroid)
            cluster.centroid = new_centroid / norm if norm > 0 else new_centroid
            cluster.centroid_n += 1
            cluster.merged_count += 1
            cluster.paraphrases_seen.append(query)
            # Keep the newly-seen real phrasing as a member. Evict from index
            # 1 onward so the originating query (index 0) is never dropped.
            if len(cluster.members) >= MAX_MEMBERS_PER_CLUSTER:
                cluster.members.pop(1)
            cluster.members.append(vec)

    def stats(self) -> dict:
        # Snapshot under the lock, and copy the mutable lists out, so the
        # returned dict can be serialized by FastAPI without another thread
        # appending a paraphrase mid-serialization.
        with self._lock:
            clusters = [
                {
                    "cluster_id": c.cluster_id,
                    "canonical_query": c.canonical_query,
                    "merged_count": c.merged_count,
                    "paraphrases_seen": list(c.paraphrases_seen),
                }
                for c in self._clusters.values()
            ]
            # merged_count starts at 1 for the originating query, so the
            # number ABSORBED is one less per cluster — otherwise a brand new
            # cluster reports "1 paraphrase absorbed" having absorbed none.
            total = sum(c.merged_count - 1 for c in self._clusters.values())
            num = len(self._clusters)
        return {
            "num_clusters": num,
            "total_paraphrases_absorbed": total,
            "clusters": clusters,
        }


# Module-level singleton — shared across requests within the process.
cache = SemanticCache()
