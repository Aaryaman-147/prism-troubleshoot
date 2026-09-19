"""
Orchestrates the full pipeline: enrichment -> cache check -> extraction ->
deeplink resolution -> ordering -> validation -> cache write.
This is what main.py's /v1/troubleshoot endpoint calls.

PERFORMANCE NOTE: enrichment and extraction are independent LLM calls
(extraction doesn't need enrichment's output) — they run CONCURRENTLY via
asyncio.gather below. This alone roughly halves cold-path latency versus
calling them sequentially, since each LLM call is the dominant cost.

WHY ASYNC (not the old ThreadPoolExecutor): the two calls were already
concurrent with threads, but run_pipeline itself was synchronous, so
FastAPI's event loop was blocked for the entire 5-40s cold call. A second
client asking for a cached answer couldn't be served in the meantime —
which directly undermines the sub-300ms fast-path claim under any
concurrency at all. Now the loop stays free during LLM waits.

Note the remaining sync work here (embedding for the cache lookup, BM25 +
dense deeplink retrieval) is CPU-bound and runs inline on the event loop.
That's fine at demo scale — it's single-digit milliseconds — but it is the
next thing to offload with asyncio.to_thread if you ever load-test this.
"""
import asyncio
import time

from pydantic import ValidationError

from app.cache.semantic_cache import cache
from app.core.llm_client import LLMRateLimitError
from app.pipeline.enrichment import enrich_query_async
from app.pipeline.extraction import extract_structure_async
from app.pipeline.ordering import resolve_deeplinks, order_actions
from app.pipeline.deeplink_retrieval import DeeplinkIndex
from app.models.schema import ContextDeeplinkResponse, ResponseMeta, TroubleshootResponse
from app.utils.validators import contains_leaked_url, scrub_urls
from app.core.config import settings

async def run_pipeline(
    query: str,
    siis_response: str | None,
    deeplink_index: DeeplinkIndex,
) -> TroubleshootResponse:
    t_start = time.perf_counter()

    # --- Cache check first (fast path) ---
    lookup = cache.lookup(query)

    if lookup.status == "hit":
        latency_ms = (time.perf_counter() - t_start) * 1000
        return TroubleshootResponse(
            query=query,
            query_variations=lookup.cluster.paraphrases_seen,
            response=lookup.cluster.payload,
            meta=ResponseMeta(
                latency_ms=round(latency_ms, 2),
                cache_hit=True,
                model="cache",
                cost_usd=0.0,
                cache_similarity=round(lookup.similarity, 4),
            ),
        )

    # --- Cold path: full pipeline ---
    # Fire enrichment + extraction CONCURRENTLY — they're independent calls.
    # return_exceptions=True so one failing call doesn't cancel the other:
    # a failed enrichment must NOT throw away a perfectly good extraction.
    enrichment_result, extraction_result = await asyncio.gather(
        enrich_query_async(query),
        extract_structure_async(query, siis_response or ""),
        return_exceptions=True,
    )

    try:
        if isinstance(enrichment_result, BaseException):
            raise enrichment_result
        enrichment = enrichment_result
    except LLMRateLimitError as e:
        print(f"[enrichment RATE LIMITED] query='{query}' error={e}")
        enrichment = {"canonical_query": query, "query_variations": [query]}
    except Exception as e:
        # Same class of bug as extraction below (e.g. Gemini returning
        # None for .text on a safety-blocked/empty response) — must not
        # crash the whole request with an uncaught 500. Enrichment failing
        # isn't fatal: fall back to using the raw query as its own
        # canonical form with no extra paraphrases, and keep going.
        import traceback
        print(f"\n{'='*70}")
        print(f"[enrichment FAILED] query='{query}'")
        print(f"Exception type: {type(e).__name__}")
        print(f"Exception message: {e}")
        traceback.print_exc()
        print(f"{'='*70}\n")
        enrichment = {"canonical_query": query, "query_variations": [query]}

    try:
        if isinstance(extraction_result, BaseException):
            raise extraction_result
        raw = extraction_result
    except LLMRateLimitError as e:
        print(f"[extraction RATE LIMITED] query='{query}' error={e}")
        raw = {"contexts": [], "fallback": "rate_limited"}
    except Exception as e:
        # This is the case that was previously silently swallowed as a
        # generic no_match — now it's visible in server logs (with full
        # traceback) so you can tell "LLM call/JSON-parse failed" apart
        # from "LLM legitimately found nothing".
        import traceback
        print(f"\n{'='*70}")
        print(f"[extraction FAILED] query='{query}'")
        print(f"Exception type: {type(e).__name__}")
        print(f"Exception message: {e}")
        print("Full traceback:")
        traceback.print_exc()
        print(f"{'='*70}\n")
        raw = {"contexts": [], "fallback": "extraction_error"}

    canonical_query = enrichment["canonical_query"]
    variations = enrichment.get("query_variations", [])

    if raw.get("fallback") or not raw.get("contexts"):
        fallback_reason = raw.get("fallback", "no_match")
        print(f"[no contexts] query='{query}' fallback='{fallback_reason}' raw={raw}")
        response = ContextDeeplinkResponse(contexts=[], fallback=fallback_reason)
    else:
        for goal in raw["contexts"]:
            actions = goal.get("actions", [])

            # Scrub any leaked URLs before they ever reach validation
            for action in actions:
                if contains_leaked_url(action.get("description", "")):
                    action["description"] = scrub_urls(action["description"])
                for sg in action.get("stepGroups", []):
                    sg["steps"] = [
                        scrub_urls(s) if contains_leaked_url(s) else s
                        for s in sg.get("steps", [])
                    ]

            actions = resolve_deeplinks(actions, deeplink_index)
            goal["actions"] = order_actions(actions)

        try:
            response = ContextDeeplinkResponse(**raw)
        except ValidationError as e:
            # Previously silent — this is very likely what you were hitting.
            # The LLM's output shape (word counts, "It will" prefix, Title
            # Case, etc.) is strict, and Gemini often needs 1-2 prompt
            # iterations to reliably comply. Check server logs for the
            # exact field that failed.
            print(f"[validation FAILED] query='{query}' errors={e.errors()}")
            print(f"[validation FAILED] raw_llm_output={raw}")
            response = ContextDeeplinkResponse(contexts=[], fallback="validation_failed")

    # --- Cache write ---
    # NEVER cache a fallback/failure — otherwise a transient extraction
    # failure (e.g. missing reference text) gets "frozen" as the permanent
    # answer for that query and all its future paraphrases, even after the
    # underlying issue is fixed. Only cache genuine successful plans.
    if response.fallback is None:
        if lookup.status == "near_miss":
            cache.merge_into_cluster(lookup.cluster, query)
        else:
            # Seed the centroid from the raw query + canonical form + the
            # enrichment stage's paraphrases. Without the raw query in here,
            # even an identical resubmission misses (see insert_new_cluster).
            cache.insert_new_cluster(
                canonical_query,
                response,
                seed_texts=[query, canonical_query, *variations],
            )

    latency_ms = (time.perf_counter() - t_start) * 1000
    return TroubleshootResponse(
        query=query,
        query_variations=variations,
        response=response,
        meta=ResponseMeta(
            latency_ms=round(latency_ms, 2),
            cache_hit=False,
            model=settings.OPENROUTER_MODEL if settings.LLM_PROVIDER == "openrouter" else settings.LLM_MODEL,
            cache_similarity=round(lookup.similarity, 4) if lookup.similarity >= 0 else None,
        ),
    )
