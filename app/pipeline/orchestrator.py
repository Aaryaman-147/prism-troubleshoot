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
from app.core.llm_client import LLMRateLimitError, TokenUsage
from app.pipeline.enrichment import enrich_query_async
from app.pipeline.extraction import extract_structure_async
from app.pipeline.ordering import resolve_deeplinks, order_actions, attach_validation_deeplinks
from app.pipeline.deeplink_retrieval import DeeplinkIndex
from app.pipeline.relevance import verify_relevance
from app.models.schema import (
    ContextDeeplinkResponse, ResponseMeta, TroubleshootResponse,
    RetrievalOverrides, AmbiguousMatch,
)
from app.utils.validators import contains_leaked_url, scrub_urls, repair_title
from app.core.config import settings

async def run_pipeline(
    query: str,
    siis_response: str | None,
    deeplink_index: DeeplinkIndex,
    retrieval_overrides: RetrievalOverrides | None = None,
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
            # Ambiguity/confidence are retrieval-time explainability data —
            # a cache hit skips retrieval entirely, so there's nothing to
            # report here. Left as the schema defaults ([], {}).
        )

    # --- Cold path: full pipeline ---

    # SIIS relevance verification, per Samsung's explicit meeting guidance:
    # "design around relevance verification and abstention rather than
    # forcing retrieved content into an answer." This is a cheap, LOCAL
    # embedding-similarity check (no LLM call), so it runs BEFORE the
    # concurrent enrichment/extraction calls below and can skip them
    # entirely on a clear mismatch -- saving a wasted extraction call on
    # reference text that obviously doesn't address the complaint, and
    # producing an honest no_match instead of forcing extraction to
    # rationalize a connection that isn't there. See
    # app/pipeline/relevance.py for the full rationale; this is a
    # necessary-but-not-sufficient filter (catches clear domain
    # mismatches, doesn't judge whether a relevant reference actually
    # contains a usable fix -- that's still extraction's job).
    relevance = verify_relevance(query, siis_response or "")
    if not relevance.is_relevant:
        print(f"[SIIS relevance check FAILED] query='{query}' "
              f"similarity={relevance.similarity:.3f} reason={relevance.reason}")
        latency_ms = (time.perf_counter() - t_start) * 1000
        response = ContextDeeplinkResponse(
            contexts=[],
            fallback="siis_mismatch",
            fallback_reason=(
                f"The reference material provided doesn't appear to address this "
                f"complaint (topical similarity {relevance.similarity:.2f}, below "
                f"the {settings.SIIS_RELEVANCE_MIN_SIMILARITY:.2f} threshold). "
                f"Rather than force an unrelated fix, no plan was generated."
            ),
        )
        # A relevance rejection is a genuine, correct abstention outcome —
        # NOT a failure — so it's safe (and correct) to cache, same as any
        # other successful no_match-style result for this exact query.
        # (Left uncached here deliberately: the reference text is a
        # per-request input, not a property of the query alone, so a
        # cached "mismatch" verdict for this query could be wrong for a
        # different, better reference passed in next time.)
        return TroubleshootResponse(
            query=query,
            query_variations=[],
            response=response,
            meta=ResponseMeta(
                latency_ms=round(latency_ms, 2),
                cache_hit=False,
                model="relevance-check-only",
                cost_usd=0.0,
                cache_similarity=round(relevance.similarity, 4),
            ),
        )

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
        enrichment, enrichment_usage = enrichment_result
    except LLMRateLimitError as e:
        print(f"[enrichment RATE LIMITED] query='{query}' error={e}")
        enrichment = {"canonical_query": query, "query_variations": [query]}
        enrichment_usage = TokenUsage()
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
        enrichment_usage = TokenUsage()

    try:
        if isinstance(extraction_result, BaseException):
            raise extraction_result
        raw, extraction_usage = extraction_result
    except LLMRateLimitError as e:
        print(f"[extraction RATE LIMITED] query='{query}' error={e}")
        raw = {"contexts": [], "fallback": "rate_limited"}
        extraction_usage = TokenUsage()
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
        extraction_usage = TokenUsage()

    total_usage = TokenUsage(
        prompt_tokens=enrichment_usage.prompt_tokens + extraction_usage.prompt_tokens,
        completion_tokens=enrichment_usage.completion_tokens + extraction_usage.completion_tokens,
    )

    canonical_query = enrichment["canonical_query"]
    variations = enrichment.get("query_variations", [])

    # --- Multi-issue follow-up ---
    # Enrichment and the first extraction call fire CONCURRENTLY (see
    # asyncio.gather above), so that first extraction attempt cannot see
    # enrichment's is_multi_issue/sub_issues signal -- it runs "blind" on
    # whether this is genuinely one issue or two. extraction.py's own
    # prompt already tries to split into up to 2 contexts on its own
    # judgment, and usually gets it right. This follow-up exists for the
    # remaining case: enrichment confidently reports 2+ distinct sub_issues
    # but the blind first attempt only returned 1 context -- i.e. the two
    # mechanisms disagree. Rather than trust either signal alone, re-run
    # extraction ONCE with the sub_issues as an explicit hint, and prefer
    # ITS result if it now returns >= as many contexts as sub_issues named.
    # This costs one extra sequential LLM call, but ONLY when: (a)
    # enrichment is confident about multiple issues, AND (b) the first
    # attempt didn't already agree -- not on every request.
    sub_issues = enrichment.get("sub_issues") or []
    is_multi_issue = bool(enrichment.get("is_multi_issue")) and len(sub_issues) >= 2
    existing_context_count = len(raw.get("contexts") or [])

    if is_multi_issue and existing_context_count < len(sub_issues):
        print(f"[multi-issue follow-up] query='{query}' sub_issues={sub_issues} "
              f"(first attempt returned {existing_context_count} context(s))")
        try:
            followup_raw, followup_usage = await extract_structure_async(
                query, siis_response or "", sub_issues=sub_issues
            )
            total_usage = TokenUsage(
                prompt_tokens=total_usage.prompt_tokens + followup_usage.prompt_tokens,
                completion_tokens=total_usage.completion_tokens + followup_usage.completion_tokens,
            )
            followup_context_count = len(followup_raw.get("contexts") or [])
            if followup_context_count >= existing_context_count:
                # Only replace if the follow-up did at least as well --
                # never let a worse follow-up result discard a working
                # first attempt.
                raw = followup_raw
        except LLMRateLimitError as e:
            print(f"[multi-issue follow-up RATE LIMITED] query='{query}' error={e}")
            # Fall through with whatever the first (blind) extraction
            # attempt already produced -- a partial/single-issue answer
            # beats losing the plan entirely.
        except Exception as e:
            import traceback
            print(f"\n{'='*70}")
            print(f"[multi-issue follow-up FAILED] query='{query}'")
            print(f"Exception type: {type(e).__name__}")
            print(f"Exception message: {e}")
            traceback.print_exc()
            print(f"{'='*70}\n")
            # Same fallback: keep the first attempt's result.

    ambiguous_matches: list[dict] = []
    deeplink_confidence: dict[str, float] = {}

    _FALLBACK_EXPLANATIONS = {
        "no_match": "No reference material was provided (or the reference text "
                    "contained no viable fix), so no troubleshooting plan could "
                    "be grounded — the system does not invent steps without a "
                    "documented source.",
        "rate_limited": "The language model provider's rate limit was exhausted "
                         "after several retries. This is a transient infrastructure "
                         "condition, not a judgment about the complaint itself.",
        "extraction_error": "An unexpected error occurred while extracting a "
                             "structured plan from the reference text. Check server "
                             "logs for the specific cause.",
    }

    if raw.get("fallback") or not raw.get("contexts"):
        fallback_code = raw.get("fallback", "no_match")
        print(f"[no contexts] query='{query}' fallback='{fallback_code}' raw={raw}")
        response = ContextDeeplinkResponse(
            contexts=[],
            fallback=fallback_code,
            fallback_reason=_FALLBACK_EXPLANATIONS.get(
                fallback_code, f"No plan was generated (reason code: {fallback_code})."
            ),
        )
    else:
        for goal in raw["contexts"]:
            # Repair an over-long title programmatically rather than
            # discarding an otherwise-valid plan over one cosmetic field.
            # Live testing showed this fails ~40-60% of the time on some
            # models — not a rare edge case. See repair_title's docstring.
            if isinstance(goal.get("title"), str):
                goal["title"] = repair_title(goal["title"], max_words=3)

            # .get(key, []) only supplies the default when the KEY IS
            # MISSING — if the LLM emits the key with an explicit null
            # (valid JSON: {"actions": null}), .get() happily returns
            # None, and the loop below crashes with the exact
            # 'NoneType is not subscriptable'-class error seen in testing.
            # `or []` catches both cases.
            actions = goal.get("actions") or []

            # Scrub any leaked URLs before they ever reach validation
            for action in actions:
                if contains_leaked_url(action.get("description", "")):
                    action["description"] = scrub_urls(action["description"])
                for sg in action.get("stepGroups") or []:
                    sg["steps"] = [
                        scrub_urls(s) if contains_leaked_url(s) else s
                        for s in (sg.get("steps") or [])
                    ]

            actions, goal_ambiguous, goal_confidence = resolve_deeplinks(
                actions,
                deeplink_index,
                min_confidence=retrieval_overrides.min_confidence if retrieval_overrides else None,
                margin=retrieval_overrides.margin if retrieval_overrides else None,
                alpha=retrieval_overrides.alpha if retrieval_overrides else None,
            )
            actions = attach_validation_deeplinks(actions)
            goal["actions"] = order_actions(actions)
            ambiguous_matches.extend(goal_ambiguous)
            deeplink_confidence.update(goal_confidence)

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
            response = ContextDeeplinkResponse(
                contexts=[],
                fallback="validation_failed",
                fallback_reason=(
                    "The generated plan didn't conform to the required output "
                    "schema (e.g. a title or description of the wrong length). "
                    "Rather than return a malformed plan, no plan was returned."
                ),
            )

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
        ambiguous_matches=[AmbiguousMatch(**m) for m in ambiguous_matches],
        deeplink_confidence=deeplink_confidence,
        meta=ResponseMeta(
            latency_ms=round(latency_ms, 2),
            cache_hit=False,
            model=settings.OPENROUTER_MODEL if settings.LLM_PROVIDER == "openrouter" else settings.LLM_MODEL,
            # Real token counts from both LLM calls this request made — see
            # TokenUsage in llm_client.py. cost_usd stays 0.0 for the free
            # tier (accurate, not faked), but token utilization is now
            # genuinely tracked rather than hardcoded, per the spec's own
            # "Cost Predictability" criterion.
            cost_usd=total_usage.estimated_cost_usd(rate_per_1k_tokens=0.0),
            prompt_tokens=total_usage.prompt_tokens,
            completion_tokens=total_usage.completion_tokens,
            cache_similarity=round(lookup.similarity, 4) if lookup.similarity >= 0 else None,
        ),
    )
