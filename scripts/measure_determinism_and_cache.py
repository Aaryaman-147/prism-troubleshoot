"""
Measures two of the spec's own graded metrics that weren't yet verified:

1. DETERMINISM ("Deterministic Execution: Consistent action plans for
   identical or semantically identical inputs.") — runs the SAME cold-path
   query N times and reports how much the output actually varies. LLM
   temperature > 0 means some variance is expected; this quantifies it
   rather than leaving it as an assumption.

2. SEMANTIC PARAPHRASE HIT RATE (target: >= 80%) — seeds the cache with
   one query, then fires a set of paraphrases at it and reports the real
   hit rate, rather than the handful of ad-hoc manual tests done so far.

This makes real LLM calls and WILL consume free-tier quota — it's meant
to be run deliberately, not as part of the normal pytest suite (which
stays fully offline/mocked).

Usage:
    python scripts/measure_determinism_and_cache.py
"""
import asyncio
import json
import sys
import time

sys.path.insert(0, ".")

from app.pipeline.orchestrator import run_pipeline
from app.pipeline.deeplink_retrieval import DeeplinkIndex
from app.core.config import settings

DETERMINISM_QUERY = "screen flickers and the battery dies fast"
DETERMINISM_REFERENCE = (
    "Display flickering combined with rapid battery drain is commonly "
    "caused by adaptive brightness conflicting with a third-party app, "
    "or a stuck refresh-rate setting. Open Settings, then Display, then "
    "Motion smoothness, and set it to Standard instead of Adaptive."
)
DETERMINISM_RUNS = 5

PARAPHRASE_SEED_QUERY = "my screen keeps flickering and the battery dies fast"
PARAPHRASE_SEED_REFERENCE = DETERMINISM_REFERENCE
PARAPHRASES_TO_TEST = [
    "screen flickers and battery drains quickly",
    "display keeps flashing and battery life is terrible",
    "why does my screen flicker and battery die so fast",
    "scren flickers n battery dies fast",  # typo-inclusive
    "the screen won't stop flickering, battery also dying fast",
    "flickering display, poor battery life",
    "my phone's screen flickers and it drains battery quick",
    "battery dies quick and screen has a flicker",
]


def plan_signature(response) -> dict:
    """Extracts the parts of a plan that matter for a determinism check —
    ignores the LLM's free-text score, which is expected to vary slightly."""
    if not response.contexts:
        return {"fallback": response.fallback}
    goal = response.contexts[0]
    return {
        "title": goal.title,
        "num_actions": len(goal.actions),
        "action_names": [a.actionName for a in goal.actions],
        "categories": [a.category.value for a in goal.actions],
    }


async def measure_determinism(index: DeeplinkIndex):
    print(f"\n{'='*70}")
    print(f"DETERMINISM CHECK — running the same query {DETERMINISM_RUNS} times")
    print(f"{'='*70}")

    from app.cache.semantic_cache import cache as _cache

    signatures = []
    failures = []
    for i in range(DETERMINISM_RUNS):
        # Clear the cache before every run. Without this, only run 1 is a
        # real cold-path call — runs 2-5 either hit cache (masking real
        # variance) or each independently risk a transient API hiccup,
        # which previously got miscounted as "nondeterminism" rather than
        # "the provider failed once".
        _cache._clusters.clear()
        result = await run_pipeline(DETERMINISM_QUERY, DETERMINISM_REFERENCE, index)
        sig = plan_signature(result.response)
        is_transient_failure = sig.get("fallback") in ("extraction_error", "rate_limited")
        if is_transient_failure:
            failures.append(sig)
        else:
            signatures.append(sig)
        print(f"[{i+1}/{DETERMINISM_RUNS}] {json.dumps(sig)}"
              f"{'  (transient API failure, excluded from determinism count)' if is_transient_failure else ''}")

    if failures:
        print(f"\n{len(failures)}/{DETERMINISM_RUNS} runs hit a transient API "
              f"failure (rate limit or provider error), not a real plan — "
              f"excluded from the determinism comparison below. If this "
              f"keeps happening, it's a quota/reliability issue, not a "
              f"determinism finding.")

    if not signatures:
        print("\nRESULT: every run failed transiently — no successful plan "
              "to compare. Re-run once quota resets.")
        return

    unique_signatures = {json.dumps(s, sort_keys=True) for s in signatures}
    print(f"\nUnique plan shapes across {len(signatures)} successful runs "
          f"(of {DETERMINISM_RUNS} attempted): {len(unique_signatures)}")
    if len(unique_signatures) == 1:
        print("RESULT: fully deterministic on this query (plan shape identical every successful run)")
    else:
        print(f"RESULT: {len(unique_signatures)} distinct plan shapes seen — "
              f"NOT fully deterministic. This may be acceptable (the spec "
              f"says 'consistent', not necessarily byte-identical) but "
              f"worth knowing before claiming full determinism in the PPT.")


async def measure_paraphrase_hit_rate(index: DeeplinkIndex):
    print(f"\n{'='*70}")
    print(f"SEMANTIC PARAPHRASE HIT RATE — target >= 80% per spec")
    print(f"{'='*70}")

    # Seed the cache
    seed_result = await run_pipeline(PARAPHRASE_SEED_QUERY, PARAPHRASE_SEED_REFERENCE, index)
    print(f"Seed query cached: {not seed_result.meta.cache_hit} "
          f"(should be True — first time seeing this query)")

    hits = 0
    for i, paraphrase in enumerate(PARAPHRASES_TO_TEST, 1):
        # No reference text — this call can ONLY succeed via cache
        result = await run_pipeline(paraphrase, None, index)
        hit = result.meta.cache_hit
        hits += hit
        sim = result.meta.cache_similarity
        sim_str = f"{sim:.3f}" if sim is not None else "n/a"
        print(f"[{i}/{len(PARAPHRASES_TO_TEST)}] hit={hit} "
              f"similarity={sim_str} '{paraphrase[:50]}'")

    hit_rate = hits / len(PARAPHRASES_TO_TEST) * 100
    print(f"\nHit rate: {hits}/{len(PARAPHRASES_TO_TEST)} = {hit_rate:.1f}%")
    from pathlib import Path
    Path("results").mkdir(exist_ok=True)
    Path("results/independent_paraphrase.json").write_text(json.dumps(
        {"hits": hits, "total": len(PARAPHRASES_TO_TEST), "rate_pct": round(hit_rate, 1)}), encoding="utf-8")
    print("Saved results/independent_paraphrase.json (used by scripts/finalize_metrics.py)")
    if hit_rate >= 80:
        print(f"RESULT: MEETS the spec's >=80% target")
    else:
        print(f"RESULT: BELOW the spec's >=80% target — consider lowering "
              f"CACHE_HIT_THRESHOLD in .env (currently {settings.CACHE_HIT_THRESHOLD})")


async def main():
    index = DeeplinkIndex(settings.DEEPLINKS_PATH)
    await measure_determinism(index)
    await measure_paraphrase_hit_rate(index)


if __name__ == "__main__":
    asyncio.run(main())
