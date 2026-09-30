"""
Concurrency stress test (spec Phase 4: "end-to-end stress tests evaluating
cold-start, cache hits, and schema compliance"). Needs a running server with
a warm cache. Makes NO LLM calls unless you pass --cold.

  python scripts/stress_test.py                      # 200 cached requests, 20 concurrent
  python scripts/stress_test.py --n 500 --concurrency 50
  python scripts/stress_test.py --cold 5             # + 5 concurrent cold queries (uses the LLM)
"""
import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def pct(xs, q):
    s = sorted(xs)
    return round(s[min(len(s) - 1, int(round(q * (len(s) - 1))))], 1) if s else None


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--cold", type=int, default=0)
    a = ap.parse_args()
    from app.models.schema import TroubleshootResponse

    warm = Path("app/data/cache_warm.jsonl")
    queries = [json.loads(l)["query"] for l in warm.read_text(encoding="utf-8").splitlines() if l.strip()] if warm.exists() else []
    if not queries:
        sys.exit("No app/data/cache_warm.jsonl: run a batch and copy results/results.jsonl there first.")
    sem = asyncio.Semaphore(a.concurrency)
    lat, hits, errors, invalid = [], 0, 0, 0

    async with httpx.AsyncClient(base_url=a.base, timeout=120) as client:
        # The server loads the embedding model and warms the cache before it
        # can answer: firing immediately after (re)starting gave
        # "Server disconnected without sending a response".
        health = None
        for attempt in range(60):
            try:
                health = (await client.get("/health")).json()
                if health.get("status") == "ok":
                    break
            except (httpx.HTTPError, ValueError):
                pass
            if attempt == 0:
                print("waiting for the server to finish starting (model load + cache warm-up)...")
            await asyncio.sleep(2)
        else:
            sys.exit(f"Server not ready after 120 s at {a.base}. Is it running? Check its logs.")
        print(f"health: {health}")

        async def one(q):
            nonlocal hits, errors, invalid
            async with sem:
                t = time.perf_counter()
                try:
                    r = await client.post("/v1/troubleshoot", json={"query": q})
                    lat.append((time.perf_counter() - t) * 1000)
                    body = r.json()
                    TroubleshootResponse.model_validate(body)
                    hits += bool(body["meta"]["cache_hit"])
                except (httpx.HTTPError, httpx.RemoteProtocolError):
                    errors += 1
                except Exception:
                    invalid += 1

        t0 = time.perf_counter()
        await asyncio.gather(*[one(queries[i % len(queries)]) for i in range(a.n)])
        wall = time.perf_counter() - t0
        print(f"\n{a.n} requests, {a.concurrency} concurrent, {wall:.1f}s wall ({a.n / wall:.0f} req/s)")
        print(f"cache hits: {hits}/{a.n} | HTTP errors: {errors} | schema-invalid: {invalid}")
        print(f"end-to-end latency (client side, incl. HTTP): P50 {pct(lat, .5)} ms, P95 {pct(lat, .95)} ms, max {pct(lat, 1.0)} ms")

        if a.cold:
            siis = json.loads(Path("app/data/siis_responses.json").read_text(encoding="utf-8"))["responses"][:a.cold]
            cold_lat = []

            async def cold(r):
                t = time.perf_counter()
                resp = await client.post("/v1/troubleshoot", json={"query": r["original_query"] + " (stress)",
                                                                  "siis_response": r["siis_response"]})
                cold_lat.append((time.perf_counter() - t) * 1000)
                return resp.json()["meta"]["cache_hit"]

            await asyncio.gather(*[cold(r) for r in siis])
            print(f"{a.cold} concurrent cold queries: P50 {pct(cold_lat, .5)} ms, max {pct(cold_lat, 1.0)} ms")


if __name__ == "__main__":
    asyncio.run(main())
