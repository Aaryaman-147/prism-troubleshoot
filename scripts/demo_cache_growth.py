"""
Demo script for the video: fires an original complaint, then a series of
unseen paraphrases, and prints cache hit/near-miss/miss + latency for each.
This is the data behind the "cache hit rate climbing live" demo moment.

IMPORTANT: Gemini's free tier is rate-limited to a handful of requests per
MINUTE. Firing all 7 queries back-to-back WILL trip that limit and cause
non-JSON error responses. This script now sleeps between COLD queries
(cache misses) to stay under the limit, and prints raw error text instead
of crashing if a response still isn't valid JSON.

Requires GEMINI_API_KEY set in .env (free tier at https://aistudio.google.com/apikey).

Run with the API already up: uvicorn app.main:app --reload
    python scripts/demo_cache_growth.py
"""
import time
import httpx

BASE_URL = "http://localhost:8000"

QUERIES = [
    "screen flickers and the battery dies fast",
    "my display keeps flickering and battery drains quickly",
    "battery dying fast, screen flickering too",
    "why is my screen flickering and the battery not lasting",
    "screen flikering nd batery dies fast",  # typo-inclusive
    "display glitch + poor battery life",
    "the phone's screen has a flicker issue and battery is bad",
]

# Seconds to wait after a COLD call (LLM call made) before the next request,
# to stay under free-tier requests-per-minute limits. Cache hits don't need
# this since they never touch the LLM.
COLD_CALL_COOLDOWN_S = 15

if __name__ == "__main__":
    for i, q in enumerate(QUERIES, 1):
        resp = httpx.post(f"{BASE_URL}/v1/troubleshoot", json={"query": q}, timeout=60)

        try:
            data = resp.json()
        except ValueError:
            print(f"[{i}] '{q[:50]}...' -> NON-JSON RESPONSE (likely rate limited or server error)")
            print(f"    raw response: {resp.status_code} {resp.text[:200]}")
            print(f"    waiting {COLD_CALL_COOLDOWN_S}s before continuing...")
            time.sleep(COLD_CALL_COOLDOWN_S)
            continue

        meta = data["meta"]
        print(
            f"[{i}] '{q[:50]}...' -> "
            f"cache_hit={meta['cache_hit']} "
            f"latency={meta['latency_ms']}ms "
            f"similarity={meta.get('cache_similarity')}"
        )

        if not meta["cache_hit"]:
            print(f"    (cold call made — waiting {COLD_CALL_COOLDOWN_S}s to respect rate limits)")
            time.sleep(COLD_CALL_COOLDOWN_S)

    print("\n--- Final cache stats ---")
    stats = httpx.get(f"{BASE_URL}/v1/cache/stats").json()
    print(f"Clusters: {stats['num_clusters']}, "
          f"Total paraphrases absorbed: {stats['total_paraphrases_absorbed']}")
