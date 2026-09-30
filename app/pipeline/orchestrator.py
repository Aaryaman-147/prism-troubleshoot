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
import re
import time

from pydantic import ValidationError

from app.cache.semantic_cache import cache
from app.core.llm_client import LLMRateLimitError, TokenUsage, generate_json_async
from app.pipeline.grounding import grounding_report, step_sources
from app.pipeline.enrichment import enrich_query_async
from app.pipeline.extraction import extract_structure_async
from app.pipeline.ordering import resolve_deeplinks, order_actions, attach_validation_deeplinks
from app.pipeline.deeplink_retrieval import DeeplinkIndex
from app.pipeline.relevance import verify_relevance
from app.models.schema import (
    ContextDeeplinkResponse, ResponseMeta, TroubleshootResponse,
    RetrievalOverrides, AmbiguousMatch,
)
from app.utils.validators import contains_leaked_url, scrub_urls, repair_title, repair_action_name, repair_description, repair_goal, repair_title_case
from app.pipeline.normalize import sanitize_plan, split_compound_steps, top_up_variations, is_critical_action, reference_fingerprint, normalize_siis, normalize_category, normalize_variations, merge_contexts, dedupe_contexts_by_title
from app.core.config import settings, config_fingerprint

def _description_ok(d) -> bool:
    return isinstance(d, str) and d.startswith("It will") and 5 <= len(d.split()) <= 7


async def _repair_descriptions(raw: dict, query: str, t_start: float | None = None) -> TokenUsage:
    bad = [a for c in (raw or {}).get("contexts") or [] for a in c.get("actions") or []
           if not _description_ok(a.get("description"))]
    if not bad:
        return TokenUsage()
    if t_start is not None and (time.perf_counter() - t_start) * 1000 > settings.REPAIR_TIME_BUDGET_MS:
        print(f"[description repair skipped] request already at {(time.perf_counter() - t_start) * 1000:.0f} ms "
              f"(budget {settings.REPAIR_TIME_BUDGET_MS} ms); using deterministic fallbacks")
        for a in bad:
            d = a.get("description")
            if isinstance(d, str) and d.startswith("It will ") and len(d.split()) == 4:
                a["description"] = "It will help " + d[len("It will "):]
        return TokenUsage()
    items = "\n".join(
        f'{i}: action="{a.get("actionName", "")}" current="{a.get("description", "")}" '
        f'steps="{" | ".join(s for g in a.get("stepGroups") or [] for s in (g.get("steps") or [])[:2])}"'
        for i, a in enumerate(bad))
    prompt = (
        "Rewrite each action description so it is EXACTLY 5, 6 or 7 words IN TOTAL, starts with \"It will\", "
        "i.e. 3 to 5 words AFTER \"It will\" (count them). "
        "and states the concrete benefit to the user. Keep the original meaning; do not add new claims.\n"
        "Example: \"It will identify damage\" -> \"It will identify any physical damage\".\n\n"
        f"User complaint: {query}\n\nActions:\n{items}\n\n"
        'Return ONLY JSON: {"descriptions": {"0": "It will ...", "1": "It will ..."}}')
    try:
        data, usage = await generate_json_async(prompt, max_output_tokens=400, max_retries=1,
                                                required_keys=("descriptions",))
    except Exception as e:
        print(f"[description repair FAILED] {type(e).__name__}: {e}")
        return TokenUsage()
    got = data.get("descriptions")
    # Accept {"0": ...}, {0: ...}, {"action_0": ...} or a plain list: the
    # strict {"0": ...} lookup silently discarded valid rewrites
    # ("fixed 0/3" in real runs).
    if isinstance(got, dict):
        by_index = {str(k): v for k, v in got.items()}
        ordered = list(got.values())
    elif isinstance(got, list):
        by_index, ordered = {}, got
    else:
        by_index, ordered = {}, []
    fixed, rejected = 0, []
    for i, a in enumerate(bad):
        cand = by_index.get(str(i))
        if cand is None:
            cand = next((v for k, v in by_index.items() if k.endswith(f"_{i}") or k.endswith(f" {i}")), None)
        if cand is None and i < len(ordered):
            cand = ordered[i]
        new = str(cand or "").strip().rstrip(".")
        if _description_ok(new):
            a["description"] = new; fixed += 1
        else:
            rejected.append(new)
    print(f"[description repair] fixed {fixed}/{len(bad)}" + (f" | rejected: {rejected}" if rejected else ""))
    # Second, count-aware pass: rewrites were typically 8-10 words. Telling
    # the model the exact current count and how many words to remove works
    # far better than restating the 5-7 rule.
    still = [(a, r) for a, r in zip([a for a in bad if not _description_ok(a.get("description"))], rejected)
             if r.startswith("It will") and len(r.split()) > 7]
    if still:
        items2 = "\n".join(f'{i}: "{r}" has {len(r.split())} words; remove at least {len(r.split()) - 7}'
                            for i, (_, r) in enumerate(still))
        prompt2 = ("Shorten each sentence to 5, 6 or 7 words IN TOTAL by removing words. Keep it starting "
                   "with \"It will\" and keep its meaning.\n" + items2 +
                   '\nReturn ONLY JSON: {"descriptions": {"0": "It will ..."}}')
        try:
            data2, usage2 = await generate_json_async(prompt2, max_output_tokens=300, max_retries=1,
                                                      required_keys=("descriptions",))
            got2 = data2.get("descriptions")
            vals = list(got2.values()) if isinstance(got2, dict) else (got2 if isinstance(got2, list) else [])
            fixed2 = 0
            for (a, _), cand in zip(still, vals):
                cand = str(cand or "").strip().rstrip(".")
                if _description_ok(cand):
                    a["description"] = cand; fixed2 += 1
            usage = TokenUsage(prompt_tokens=usage.prompt_tokens + usage2.prompt_tokens,
                               completion_tokens=usage.completion_tokens + usage2.completion_tokens)
            print(f"[description repair pass 2] fixed {fixed2}/{len(still)}")
        except Exception as e:
            print(f"[description repair pass 2 FAILED] {type(e).__name__}: {e}")
    # Last resort for the most common miss, a 4-word "It will <verb> <object>":
    # "It will help <verb> <object>" keeps the meaning and meets 5 words,
    # rather than dropping a correct action over one missing word.
    for a in bad:
        d = a.get("description")
        if isinstance(d, str) and d.startswith("It will ") and len(d.split()) == 4:
            a["description"] = "It will help " + d[len("It will "):]
    return usage


def _classify_failure(e: Exception) -> str:
    """Auth/permission/credit failures are configuration problems: report
    them as provider_error with the cause, instead of a generic
    extraction_error that said only "check server logs"."""
    status = getattr(e, "status_code", 0)
    name = type(e).__name__
    msg = str(e).lower()
    if status in (401, 402, 403) or name in ("AuthenticationError", "PermissionDeniedError") \
            or "credit" in msg or "unauthorized" in msg:
        return "provider_error"
    return "extraction_error"


_MENU_TARGETS = {
    "settings", "display", "battery", "connections", "sound", "sounds and vibration", "notifications",
    "apps", "general management", "accessibility", "advanced features", "security and privacy",
    "biometrics", "location", "accounts and backup", "device care", "software update",
    "navigation bar", "lock screen", "wallpaper", "about phone", "storage", "privacy", "home screen",
}
_NAV_STEP_RE = re.compile(r"^\s*(?:open|tap|select|go to|navigate to|choose)\s+(?:the\s+)?(.+?)\s*\.?\s*$", re.I)


def _fold_navigation_actions(actions: list[dict]) -> list[dict]:
    """
    A real plan came back as separate actions "Settings" (Open Settings.),
    "Navigation Bar" (Select Navigation bar.), "Swipe Gestures" (Confirm...),
    and "Display" (Select Display.) LAST. A single-step action that only
    opens a known menu is not an action: its step is folded into the next
    action's path; a trailing one is dropped. Anything else is untouched.
    """
    def nav_only(a):
        steps = [s for g in a.get("stepGroups") or [] for s in g.get("steps") or []]
        m = _NAV_STEP_RE.match(steps[0]) if len(steps) == 1 else None
        return bool(m) and m.group(1).lower().rstrip(".") in _MENU_TARGETS and a.get("category") != "critical"
    if not any(nav_only(a) for a in actions) or all(nav_only(a) for a in actions):
        return actions
    out, carry = [], []
    for a in actions:
        if nav_only(a):
            carry += [s for g in a["stepGroups"] for s in g["steps"]]
            continue
        if carry and a.get("stepGroups"):
            first = a["stepGroups"][0]
            existing = [s.lower() for s in first.get("steps") or []]
            first["steps"] = [s for s in carry if s.lower() not in existing] + list(first.get("steps") or [])
            carry = []
        out.append(a)
    dropped = len(actions) - len(out)
    print(f"[navigation fold] merged {dropped} menu-only action(s) into their neighbours")
    return out


def token_cost_usd(prompt_tokens: int, completion_tokens: int) -> float:
    """Appendix C: (prompt tokens + completion tokens) x rate, per-direction rates."""
    return round((prompt_tokens or 0) * settings.LLM_PRICE_PER_MTOK_INPUT / 1e6
                 + (completion_tokens or 0) * settings.LLM_PRICE_PER_MTOK_OUTPUT / 1e6, 6)


def _seed_texts(query: str, canonical: str, variations: list[str], n_contexts: int) -> list[str]:
    """Phrasings stored for a new cache cluster.
    Multi-issue plans store only the full complaint: their paraphrases often
    cover ONE sub-issue ("Camera app crashes when opened"), which made a
    single-issue query hit the two-plan answer at 0.988 in real-model testing.
    While batch_run measures, the last CACHE_SEED_HOLDOUT paraphrases are held
    out so they can be replayed as unseen (production holdout = 0)."""
    if n_contexts > 1:
        return [query, canonical]
    k = settings.CACHE_SEED_HOLDOUT
    kept = variations[:-k] if k and len(variations) > k + 2 else variations
    return [query, canonical, *kept]


def _salvage_plan(raw: dict):
    """Keep every action and goal that validates on its own; None if nothing survives."""
    from app.models.schema import Action, Goal
    goals = []
    for g in (raw or {}).get("contexts") or []:
        kept = []
        for a in g.get("actions") or []:
            try:
                Action.model_validate(a)
                kept.append(a)
            except ValidationError as e:
                print(f"[salvage] dropped action {a.get('actionName')!r}: {e.errors()[0]['msg']}")
        if not kept:
            continue
        try:
            goals.append(Goal.model_validate({**g, "actions": kept}))
        except ValidationError as e:
            print(f"[salvage] dropped goal {g.get('title')!r}: {e.errors()[0]['msg']}")
    return ContextDeeplinkResponse(contexts=goals) if goals else None


def _reference_direction(key: str, reference: str) -> str | None:
    """Which way the REFERENCE says to set `key`: 'onURL', 'offURL' or None,
    judged from the sentences that mention that setting."""
    from app.pipeline.ordering import _ON_RE, _OFF_RE
    k = (key or "").lower().strip()
    if not k or not reference:
        return None
    sents = [x for x in re.split(r"(?<=[.!?])\s+|\n+", reference) if k in x.lower()]
    on = sum(len(_ON_RE.findall(x)) for x in sents)
    off = sum(len(_OFF_RE.findall(x)) for x in sents)
    return "onURL" if on > off else ("offURL" if off > on else None)


def _drop_contradicting_twins(actions: list[dict], reference: str = "") -> list[dict]:
    """
    Resolve an action that CONTRADICTS or DUPLICATES an earlier one:
      - same setting (validation key) with opposite on/off originalType: keep
        the one whose direction the REFERENCE states for that setting. A
        manual review caught "keep the first" enabling Touch sensitivity when
        the reference said to disable it. No stated direction -> keep first.
      - the exact same deeplink again -> drop the later one.
    `dummy_positive` is a shared placeholder, never a duplicate. Different
    screens that merely share a generic key are kept.
    """
    opposite = {"onURL": "offURL", "offURL": "onURL"}
    seen_links, owner, kept = set(), {}, []      # owner: (key, type) -> index in kept
    for a in actions:
        links, toggles = set(), set()
        for g in a.get("stepGroups") or []:
            link = g.get("actionableDeeplink") or {}
            if not link.get("deeplink") or link["deeplink"].endswith("dummy_positive"):
                continue
            links.add(link["deeplink"])
            key = (g.get("validationDeeplink") or {}).get("key")
            if key and link.get("originalType") in opposite:
                toggles.add((key, link["originalType"]))
        clash = [t for t in toggles if (t[0], opposite[t[1]]) in owner]
        if clash:
            key, kind = clash[0]
            if _reference_direction(key, reference) == kind:
                idx = owner.pop((key, opposite[kind]))
                print(f"[twin conflict] replaced {kept[idx].get('actionName')!r} with {a.get('actionName')!r}: "
                      f"the reference says {'enable' if kind == 'onURL' else 'disable'} {key!r}")
                kept[idx] = a
                for t in toggles:
                    owner[t] = idx
                seen_links |= links
            else:
                print(f"[twin conflict] dropped {a.get('actionName')!r}: opposite toggle of {[key]}")
            continue
        if links and links <= seen_links:
            print(f"[twin conflict] dropped {a.get('actionName')!r}: duplicate deeplink")
            continue
        seen_links |= links
        for t in toggles:
            owner[t] = len(kept)
        kept.append(a)
    return kept


def _is_template_echo(raw: dict) -> bool:
    """True if the output still contains the prompt's '...' placeholders."""
    def placeholder(v):
        return isinstance(v, str) and (v.strip() in ("...", "…") or v.strip().endswith(" ..."))
    for c in (raw or {}).get("contexts") or []:
        if placeholder(c.get("title")) or placeholder(c.get("goal")):
            return True
        for a in c.get("actions") or []:
            if placeholder(a.get("actionName")) or placeholder(a.get("description")):
                return True
            if any(placeholder(s) for g in a.get("stepGroups") or [] for s in g.get("steps") or []):
                return True
    return False


async def _run_pipeline_core(
    query: str,
    siis_response,
    deeplink_index: DeeplinkIndex,
    retrieval_overrides: RetrievalOverrides | None = None,
) -> TroubleshootResponse:
    t_start = time.perf_counter()
    # Accepts plain text or Samsung's {"title","content"} object; strips the
    # device-category tag lists out of content (see normalize.py).
    siis_text = normalize_siis(siis_response)

    # Live-tuning overrides that differ from the configured defaults must
    # bypass cache READS -- otherwise the demo sliders silently do nothing
    # for any query already cached.
    overrides_active = retrieval_overrides is not None and any(
        v is not None and abs(v - d) > 1e-9 for v, d in [
            (retrieval_overrides.alpha, settings.DEEPLINK_ALPHA),
            (retrieval_overrides.min_confidence, settings.DEEPLINK_MIN_CONFIDENCE),
            (retrieval_overrides.margin, settings.DEEPLINK_MARGIN),
        ]
    )

    # --- Cache check first (fast path) ---
    lookup = await asyncio.to_thread(cache.lookup, query)
    ref_fp = reference_fingerprint(siis_text)
    if lookup.status in ("hit", "near_miss") and ref_fp and (
            lookup.cluster.reference_fp != ref_fp            # different or UNKNOWN document (e.g. warmed)
            or lookup.similarity < settings.CACHE_HIT_THRESHOLD_WITH_SIIS):
        # The caller supplied a reference: reuse a cached plan only if it was
        # grounded in that same document and the complaint is a close
        # paraphrase. Otherwise ground anew (spec: no steps outside the text).
        lookup = type(lookup)("miss", None, lookup.similarity, lookup.lookup_ms)

    if lookup.status == "hit" and not overrides_active:
        latency_ms = (time.perf_counter() - t_start) * 1000
        return TroubleshootResponse(
            query=query,
            query_variations=lookup.cluster.variations or lookup.cluster.paraphrases_seen,
            response=lookup.cluster.payload,
            meta=ResponseMeta(
                latency_ms=round(latency_ms, 2),
                cache_hit=True,
                model="cache",
                cost_usd=0.0,
                cache_similarity=round(lookup.similarity, 4),
                # The document this plan is grounded in (a hit with a supplied
                # reference is only ever the SAME document). Lets warm-up give
                # this query its own entry (BUG-010).
                # Only when the caller supplied a reference (then it equals the
                # cluster's). A reference-less hit says nothing about the
                # query's own document, so warm-up must not re-register it.
                reference_fp=ref_fp,
                config_fingerprint=config_fingerprint(),
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
    # No reference text and no cache hit: nothing to ground a plan in. The
    # spec's roadmap names this fallback "no_siis_context". Previously an
    # extraction LLM call was spent anyway just to be told "no_match".
    if not siis_text:
        latency_ms = (time.perf_counter() - t_start) * 1000
        return TroubleshootResponse(
            query=query,
            response=ContextDeeplinkResponse(
                contexts=[], fallback="no_siis_context",
                fallback_reason=("No reference material was provided and no "
                                 "previously-answered similar complaint is cached, so "
                                 "there is nothing to ground a plan in. No LLM call was made."),
            ),
            meta=ResponseMeta(latency_ms=round(latency_ms, 2), cache_hit=False,
                              model="none", cost_usd=0.0,
                              cache_similarity=round(lookup.similarity, 4) if lookup.similarity >= 0 else None),
        )

    relevance = verify_relevance(query, siis_text)
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
                cache_similarity=round(lookup.similarity, 4) if lookup.similarity >= 0 else None,
                relevance_similarity=round(relevance.similarity, 4),
            ),
        )

    # Fire enrichment + extraction CONCURRENTLY — they're independent calls.
    # return_exceptions=True so one failing call doesn't cancel the other:
    # a failed enrichment must NOT throw away a perfectly good extraction.
    enrichment_result, extraction_result = await asyncio.gather(
        enrich_query_async(query),
        extract_structure_async(query, siis_text),
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
        raw = sanitize_plan(raw)
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
        raw = {"contexts": [], "fallback": _classify_failure(e), "_error": f"{type(e).__name__}: {str(e)[:180]}"}
        extraction_usage = TokenUsage()

    total_usage = TokenUsage(
        prompt_tokens=enrichment_usage.prompt_tokens + extraction_usage.prompt_tokens,
        completion_tokens=enrichment_usage.completion_tokens + extraction_usage.completion_tokens,
    )

    # --- Template-echo guard ---
    # A real run returned the prompt's example shape verbatim ("title": "...",
    # "It will ..."), which then failed validation. Retry extraction once.
    if _is_template_echo(raw):
        print(f"[template echo] query='{query}' -- retrying extraction once")
        try:
            raw, retry_usage = await extract_structure_async(query, siis_text)
            raw = sanitize_plan(raw)
            total_usage = TokenUsage(prompt_tokens=total_usage.prompt_tokens + retry_usage.prompt_tokens,
                                     completion_tokens=total_usage.completion_tokens + retry_usage.completion_tokens)
        except Exception as e:
            print(f"[template echo retry FAILED] {type(e).__name__}: {e}")
        if _is_template_echo(raw):
            raw = {"contexts": [], "fallback": "extraction_error"}

    canonical_query = enrichment["canonical_query"]
    variations = normalize_variations(enrichment.get("query_variations", []), query)
    variations = top_up_variations(variations, query, str(enrichment.get("canonical_query") or query))

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
                query, siis_text, sub_issues=sub_issues
            )
            followup_raw = sanitize_plan(followup_raw)
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

    # --- Over-split guard ---
    # Real runs showed ONE complaint split into two contexts (one per possible
    # cause), including two contexts with an identical title. Deterministic
    # correction: same-title contexts always merge; and when enrichment
    # explicitly judged the complaint single-issue, all contexts merge.
    if raw.get("contexts") and len(raw["contexts"]) > 1:
        raw["contexts"] = dedupe_contexts_by_title(raw["contexts"])
        if "is_multi_issue" in enrichment and not is_multi_issue and len(raw["contexts"]) > 1:
            print(f"[over-split merged] query='{query}' contexts={len(raw['contexts'])} -> 1")
            raw["contexts"] = [merge_contexts(raw["contexts"])]

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
                             "structured plan from the reference text.",
        "insufficient_grounding": "Every generated action had too few steps supported by the "
                                  "reference text, so no plan was returned rather than one with "
                                  "unsupported steps.",
        "provider_error": "The language model provider rejected the request "
                          "(authentication, permissions or credits). This is a "
                          "configuration issue, not a judgment about the complaint.",
    }

    # A real response contained 5 valid actions AND "fallback": "no_match";
    # checking the fallback key first discarded the whole plan. Contexts win:
    # a model-supplied fallback is ignored whenever it also returned a plan.
    if raw.get("contexts") and raw.get("fallback"):
        print(f"[fallback ignored] model returned a plan together with fallback={raw['fallback']!r}")
        raw.pop("fallback", None)
    if not raw.get("contexts"):
        fallback_code = raw.get("fallback", "no_match")
        print(f"[no contexts] query='{query}' fallback='{fallback_code}' raw={raw}")
        response = ContextDeeplinkResponse(
            contexts=[],
            fallback=fallback_code,
            fallback_reason=_FALLBACK_EXPLANATIONS.get(
                fallback_code, f"No plan was generated (reason code: {fallback_code})."
            ) + (f" Cause: {raw['_error']}" if raw.get("_error") else ""),
        )
    else:
        for goal in raw["contexts"]:
            # Repair an over-long title programmatically rather than
            # discarding an otherwise-valid plan over one cosmetic field.
            # Live testing showed this fails ~40-60% of the time on some
            # models — not a rare edge case. See repair_title's docstring.
            if isinstance(goal.get("title"), str):
                goal["title"] = repair_title_case(repair_title(goal["title"], max_words=3), query)
            if isinstance(goal.get("goal"), str):
                goal["goal"] = repair_goal(goal["goal"], goal.get("title", ""))

            # .get(key, []) only supplies the default when the KEY IS
            # MISSING — if the LLM emits the key with an explicit null
            # (valid JSON: {"actions": null}), .get() happily returns
            # None, and the loop below crashes with the exact
            # 'NoneType is not subscriptable'-class error seen in testing.
            # `or []` catches both cases.
            actions = _fold_navigation_actions(goal.get("actions") or [])
            goal["actions"] = actions
            for action in actions:
                # Normalize before anything keys off these fields: a stray
                # "Auto" skipped deeplink resolution and then failed the enum.
                action["category"] = normalize_category(action.get("category"))
                if action["category"] != "critical" and is_critical_action(action.get("actionName", "")):
                    print(f"[category] {action.get('actionName')!r}: {action['category']} -> critical (spec 4.1)")
                    action["category"] = "critical"
                if isinstance(action.get("actionName"), str):
                    action["actionName"] = repair_action_name(action["actionName"])
                # Over-long descriptions are NOT truncated here any more:
                # blind cuts produced "It will test if device responds after".
                # The correction loop rewrites them; truncation is the last
                # resort afterwards.
                for g in action.get("stepGroups") or []:
                    # Samsung's sample_output ends every step with a period.
                    g["steps"] = [s.strip() if s.strip().endswith((".", "!", "?")) else s.strip() + "."
                                  for s in split_compound_steps([x for x in (g.get("steps") or []) if isinstance(x, str)])
                                  if s.strip()]

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
            actions = attach_validation_deeplinks(actions, deeplink_index.catalog_by_uri)
            actions = _drop_contradicting_twins(actions, siis_text)
            goal["actions"] = order_actions(actions)
            ambiguous_matches.extend(goal_ambiguous)
            deeplink_confidence.update(goal_confidence)

        # --- Correction loop for descriptions (spec pitfall 3: "correction
        # loops in the application layer"). Nemotron often writes 4-word
        # descriptions; one small call rewrites only those, before any action
        # is dropped. Anything still invalid afterwards is salvaged away.
        repair_usage = await _repair_descriptions(raw, query, t_start)
        for g in raw.get("contexts") or []:
            for a in g.get("actions") or []:
                if isinstance(a.get("description"), str) and len(a["description"].split()) > 7:
                    a["description"] = repair_description(a["description"])
        total_usage = TokenUsage(prompt_tokens=total_usage.prompt_tokens + repair_usage.prompt_tokens,
                                 completion_tokens=total_usage.completion_tokens + repair_usage.completion_tokens)

        if settings.GROUNDING_MIN_ACTION_SUPPORT > 0:
            rep = grounding_report(raw["contexts"], siis_text)
            for g in raw["contexts"]:
                before = len(g.get("actions") or [])
                g["actions"] = [a for a in g.get("actions") or []
                                if rep["per_action"].get(a.get("actionName", ""), 1.0) >= settings.GROUNDING_MIN_ACTION_SUPPORT]
                if len(g["actions"]) < before:
                    print(f"[grounding] dropped {before - len(g['actions'])} weakly grounded action(s) from '{g.get('title')}'")
            raw["contexts"] = [g for g in raw["contexts"] if g.get("actions")]
            if not raw["contexts"]:
                # Previously this produced contexts=[] with fallback=None: an
                # empty answer with no reason (S4-26 in a real run).
                raw["fallback"] = "insufficient_grounding"
                raw["fallback_reason"] = ("Every generated action had too few steps supported by the "
                                          "reference text, so no plan was returned rather than one with "
                                          "unsupported steps.")

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
            # Salvage: drop only the actions/goals that fail the schema instead
            # of discarding the whole plan. A real run lost an 8-action plan
            # because ONE description had 4 words.
            salvaged = _salvage_plan(raw)
            if salvaged is not None:
                response = salvaged
            else:
                response = ContextDeeplinkResponse(
                    contexts=[],
                    fallback="validation_failed",
                    fallback_reason=(
                        "The generated plan didn't conform to the required output "
                        "schema (e.g. a title or description of the wrong length). "
                        "Rather than return a malformed plan, no plan was returned."
                    ),
                )

    # --- Evidence-based score ---
    if response.fallback is None and settings.SCORE_MODE == "evidence" and siis_text:
        for g in response.contexts:
            pct = grounding_report([g.model_dump()], siis_text)["step_support_pct"]
            if pct is not None:
                g.score = round(float(g.score) * (0.5 + 0.5 * pct / 100.0), 2)

    # --- Cache write ---
    # NEVER cache a fallback/failure — otherwise a transient extraction
    # failure (e.g. missing reference text) gets "frozen" as the permanent
    # answer for that query and all its future paraphrases, even after the
    # underlying issue is fixed. Only cache genuine successful plans.
    if response.fallback is None:
        if lookup.status == "near_miss":
            cache.merge_into_cluster(lookup.cluster, query)
        elif lookup.status == "miss":
            # Seed the centroid from the raw query + canonical form + the
            # enrichment stage's paraphrases. Without the raw query in here,
            # even an identical resubmission misses (see insert_new_cluster).
            cache.insert_new_cluster(
                canonical_query,
                response,
                # While batch_run measures, the last CACHE_SEED_HOLDOUT paraphrases
                # are NOT stored so they can be replayed as genuinely unseen
                # phrasings (replaying stored ones measured a meaningless 100%).
                # In production the holdout is 0: storing every phrasing
                # maximizes recall (holding out cost the independent test 87.5% -> 75%).
                seed_texts=_seed_texts(query, canonical_query, variations, len(response.contexts)),
                variations=variations,
                reference_fp=ref_fp,
            )

    latency_ms = (time.perf_counter() - t_start) * 1000
    return TroubleshootResponse(
        query=query,
        query_variations=variations,
        response=response,
        ambiguous_matches=[AmbiguousMatch(**m) for m in ambiguous_matches],
        deeplink_confidence=deeplink_confidence,
        # Previously never set: the schema had these fields but every
        # response reported is_multi_issue=false even when split in two.
        is_multi_issue=len(response.contexts) > 1 or is_multi_issue,
        detected_sub_issues=sub_issues if (is_multi_issue or len(response.contexts) > 1) else [],
        step_sources=step_sources([c.model_dump() for c in response.contexts], siis_text) if response.contexts else {},
        meta=ResponseMeta(
            latency_ms=round(latency_ms, 2),
            cache_hit=False,
            model=settings.OPENROUTER_MODEL if settings.LLM_PROVIDER == "openrouter" else settings.LLM_MODEL,
            # Real token counts from both LLM calls this request made — see
            # TokenUsage in llm_client.py. cost_usd stays 0.0 for the free
            # tier (accurate, not faked), but token utilization is now
            # genuinely tracked rather than hardcoded, per the spec's own
            # "Cost Predictability" criterion.
            cost_usd=token_cost_usd(total_usage.prompt_tokens, total_usage.completion_tokens),
            prompt_tokens=total_usage.prompt_tokens,
            completion_tokens=total_usage.completion_tokens,
            cache_similarity=round(lookup.similarity, 4) if lookup.similarity >= 0 else None,
            relevance_similarity=round(relevance.similarity, 4),
            config_fingerprint=config_fingerprint(),
            reference_fp=ref_fp,
            step_grounding_pct=(grounding_report([c.model_dump() for c in response.contexts], siis_text)["step_support_pct"]
                                if response.contexts else None),
        ),
    )



async def run_pipeline(query: str, siis_response, deeplink_index, retrieval_overrides=None) -> TroubleshootResponse:
    """
    Multilingual entry point. A complaint in another language (Hindi, Korean,
    Spanish, romanized Hinglish, ...) is translated to English ONCE, then the
    normal pipeline runs on the English text: the embedding model, Samsung's
    SIIS documents and the deeplink catalog are all English, so without this
    a non-English complaint would be wrongly refused as siis_mismatch.
    English complaints skip this entirely (no extra call).
    """
    from app.pipeline.language import needs_translation, translate_query
    from app.pipeline.normalize import clean_complaint
    original_query, query = query, clean_complaint(query) or query
    t0 = time.perf_counter()
    language, english, usage = None, query, TokenUsage()
    if needs_translation(query):
        try:
            language, english, usage = await translate_query(query)
        except Exception as e:
            print(f"[translation FAILED] {type(e).__name__}: {e} -- continuing with the original text")
        if not language or language.strip().lower() == "english":
            language, english = None, query
    result = await _run_pipeline_core(english, siis_response, deeplink_index, retrieval_overrides)
    if len(result.query_variations) < 8:
        # Spec: 8-10 query_variations on every output line, fallbacks included
        # (deterministic registers; no LLM call).
        result.query_variations = top_up_variations(result.query_variations, english, english)
    result.query = original_query       # always echo the caller's own text
    if language:
        result.detected_language = language
        result.translated_query = english
        result.meta.latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        result.meta.prompt_tokens = (result.meta.prompt_tokens or 0) + usage.prompt_tokens
        result.meta.completion_tokens = (result.meta.completion_tokens or 0) + usage.completion_tokens
        result.meta.cost_usd = token_cost_usd(result.meta.prompt_tokens, result.meta.completion_tokens)
        if result.response.fallback_reason and "No LLM call was made" in result.response.fallback_reason:
            result.response.fallback_reason = result.response.fallback_reason.replace(
                "No LLM call was made.", f"Only the translation call ({language} → English) was made.")
        if result.meta.model in ("none", "relevance-check-only", "cache"):
            result.meta.model = f"{result.meta.model} + translation"
    return result
