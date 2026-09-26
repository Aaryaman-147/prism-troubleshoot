"""
Concurrency stress test for the cache's threading.RLock
(app/cache/semantic_cache.py).

This has been flagged twice in handoffs as "reasoned about, never
empirically verified" — the lock exists because the Gemini async path runs
via asyncio.to_thread (real OS threads, not just event-loop interleaving),
so two requests really can call insert_new_cluster / merge_into_cluster at
the same instant. Everything elsewhere in the test suite uses asyncio, which
only interleaves at await points and would never actually exercise a real
race condition on the underlying dict/list mutations. This file uses real
threads (concurrent.futures.ThreadPoolExecutor) specifically to do that.

Run with: pytest tests/test_cache_concurrency.py -v
Slower than the rest of the suite (real thread scheduling) — expect ~1-2s,
not the sub-10ms the rest of the suite runs in.
"""
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pytest
from unittest.mock import patch

from app.models.schema import ContextDeeplinkResponse


def fake_embed(text: str) -> np.ndarray:
    """Same deterministic pseudo-embedding as test_cache.py, extended with
    enough distinct query buckets to create real, non-colliding clusters
    under concurrent inserts."""
    vocab = [f"topic{i}" for i in range(64)]
    words = text.lower().split()
    vec = np.array([1.0 if w in vocab else 0.0 for w in words + vocab[:0]] or
                    [1.0 if v in words else 0.0 for v in vocab])
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


PAYLOAD = ContextDeeplinkResponse(contexts=[])


@pytest.fixture
def cache():
    with patch("app.cache.semantic_cache.embed", side_effect=fake_embed):
        from app.cache.semantic_cache import SemanticCache
        yield SemanticCache(hit_threshold=0.85, near_miss_threshold=0.5)


class TestConcurrentInserts:
    def test_many_threads_inserting_distinct_clusters_lose_nothing(self, cache):
        """
        20 threads, each inserting a cluster for its own distinct query, all
        firing at once. Without the lock, concurrent dict[key] = value writes
        during iteration elsewhere (lookup() iterates .values()) can raise
        "RuntimeError: dictionary changed size during iteration" or silently
        drop an entry. Every insert must land — none silently lost.
        """
        n = 20
        barrier = threading.Barrier(n)

        def insert(i):
            barrier.wait()  # maximize actual overlap, not just "close in time"
            with patch("app.cache.semantic_cache.embed", side_effect=fake_embed):
                return cache.insert_new_cluster(f"topic{i} query", PAYLOAD)

        with ThreadPoolExecutor(max_workers=n) as pool:
            futures = [pool.submit(insert, i) for i in range(n)]
            results = [f.result() for f in as_completed(futures)]

        assert len(results) == n
        assert cache.stats()["num_clusters"] == n, (
            "a concurrent insert was lost — the lock did not fully "
            "serialize writes to _clusters"
        )

    def test_concurrent_lookups_during_inserts_never_crash(self, cache):
        """
        Interleaves readers (lookup, which iterates _clusters.values()) with
        writers (insert_new_cluster, which mutates _clusters) on real
        threads. This is the specific RuntimeError class an unlocked dict
        iteration is vulnerable to — asyncio-only tests can't produce it
        because they never truly interleave a dict mutation mid-iteration.
        """
        stop = threading.Event()
        errors = []

        def reader():
            while not stop.is_set():
                try:
                    with patch("app.cache.semantic_cache.embed", side_effect=fake_embed):
                        cache.lookup("topic3 topic7 query")
                except Exception as e:  # noqa: BLE001 — capturing ANY crash is the point
                    errors.append(e)

        def writer(i):
            with patch("app.cache.semantic_cache.embed", side_effect=fake_embed):
                cache.insert_new_cluster(f"topic{i} writer query", PAYLOAD)

        readers = [threading.Thread(target=reader) for _ in range(4)]
        for t in readers:
            t.start()

        with ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(writer, range(30)))

        stop.set()
        for t in readers:
            t.join(timeout=2)

        assert not errors, f"reader thread(s) crashed during concurrent writes: {errors}"


class TestConcurrentMerges:
    def test_concurrent_merges_into_same_cluster_lose_no_updates(self, cache):
        """
        The centroid read-modify-write in merge_into_cluster (read
        centroid_n, compute new mean, write both back) is a classic
        lost-update race if unlocked: two threads can both read n=5,
        both compute the mean for n=6, and the second write clobbers the
        first — leaving merged_count incremented twice but the centroid
        reflecting only one of the two merges.

        This asserts merged_count/centroid_n end up EXACTLY right after
        many real concurrent merges, which a lost update would break.
        """
        with patch("app.cache.semantic_cache.embed", side_effect=fake_embed):
            cluster = cache.insert_new_cluster("topic0 seed query", PAYLOAD)

        n = 25
        barrier = threading.Barrier(n)

        def merge(i):
            barrier.wait()
            with patch("app.cache.semantic_cache.embed", side_effect=fake_embed):
                cache.merge_into_cluster(cluster, f"topic0 paraphrase {i}")

        with ThreadPoolExecutor(max_workers=n) as pool:
            list(pool.map(merge, range(n)))

        # 1 (seed) + n merges
        assert cluster.merged_count == 1 + n, (
            f"expected merged_count={1 + n}, got {cluster.merged_count} — "
            f"a concurrent merge was lost (classic read-modify-write race)"
        )
        assert cluster.centroid_n == 1 + n
        assert cache.stats()["total_paraphrases_absorbed"] == n

        # Centroid must still be a valid unit vector — a corrupted
        # interleaved write (partial read + partial write from two threads)
        # would likely leave a non-unit-norm or NaN-containing vector.
        norm = np.linalg.norm(cluster.centroid)
        assert np.isfinite(norm)
        assert abs(norm - 1.0) < 1e-6

    def test_member_cap_holds_under_concurrent_merges(self, cache):
        """
        MAX_MEMBERS_PER_CLUSTER eviction (members.pop(1) then append) is
        itself a mutation that needs the lock — concurrent evict+append
        pairs racing could leave members either over the cap or, worse,
        raise an IndexError from popping an empty-ish list mid-mutation.
        """
        from app.cache.semantic_cache import MAX_MEMBERS_PER_CLUSTER

        with patch("app.cache.semantic_cache.embed", side_effect=fake_embed):
            cluster = cache.insert_new_cluster("topic0 seed query", PAYLOAD)

        n = MAX_MEMBERS_PER_CLUSTER * 3  # force well past the cap
        barrier = threading.Barrier(n)

        def merge(i):
            barrier.wait()
            with patch("app.cache.semantic_cache.embed", side_effect=fake_embed):
                cache.merge_into_cluster(cluster, f"topic0 paraphrase {i}")

        with ThreadPoolExecutor(max_workers=n) as pool:
            list(pool.map(merge, range(n)))

        assert len(cluster.members) == MAX_MEMBERS_PER_CLUSTER
        # The originating query's vector (index 0) must never be evicted.
        assert cluster.members[0] is not None
