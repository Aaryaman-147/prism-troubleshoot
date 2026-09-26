"""
Tests for multi-issue complaint handling's follow-up mechanism.

Design (see orchestrator.py for the full rationale): enrichment and the
first extraction call fire CONCURRENTLY, so the first extraction attempt
cannot see enrichment's is_multi_issue/sub_issues signal -- extraction's
own prompt tries to split into up to 2 contexts on its own judgment, and
usually agrees with enrichment. The follow-up call exists for the
remaining disagreement case: enrichment confidently reports N distinct
sub_issues but the first (blind) attempt returned fewer contexts than
that. Only then does the orchestrator re-run extraction ONCE with the
sub_issues as an explicit hint, and only adopts that follow-up's result
if it did at least as well as the first attempt.

Run with: pytest tests/test_multi_issue.py -v
"""
import asyncio
import numpy as np
import pytest
from unittest.mock import patch

from app.core.llm_client import TokenUsage, LLMRateLimitError
from app.pipeline import orchestrator


def fake_embed(text: str) -> np.ndarray:
    vocab = ["screen", "flicker", "battery", "dies", "fast", "camera", "crash"]
    words = set(text.lower().split())
    vec = np.array([1.0 if w in words else 0.0 for w in vocab])
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


@pytest.fixture(autouse=True)
def patched_embeddings():
    # SIIS relevance-verification bypass, same rationale as
    # test_orchestrator.py's fresh_cache fixture: this file's fixtures use
    # generic placeholder reference text not designed to pass a real
    # topical-similarity check, and these tests exist to test the
    # multi-issue follow-up mechanism specifically, not relevance
    # checking (that's test_relevance.py's job).
    from app.pipeline.relevance import RelevanceResult

    with patch("app.cache.semantic_cache.embed", side_effect=fake_embed), \
         patch.object(
             orchestrator, "verify_relevance",
             return_value=RelevanceResult(is_relevant=True, similarity=1.0, reason="bypassed_for_test"),
         ):
        yield


class FakeDeeplinkIndex:
    """Matches the DeeplinkIndex.search signature used by ordering.py."""

    def __init__(self):
        self.catalog_by_uri = {}

    def search(self, query_text, top_k=1, alpha=None):
        return []


@pytest.fixture
def fresh_cache():
    from app.cache.semantic_cache import SemanticCache
    fresh = SemanticCache(hit_threshold=0.85, near_miss_threshold=0.5)
    with patch.object(orchestrator, "cache", fresh):
        yield fresh


SINGLE_ISSUE_ENRICHMENT = ({
    "canonical_query": "screen flickering",
    "query_variations": ["screen flickers", "display glitching"],
    "is_multi_issue": False,
    "sub_issues": [],
}, TokenUsage(prompt_tokens=40, completion_tokens=60))

MULTI_ISSUE_ENRICHMENT = ({
    "canonical_query": "screen flicker and battery drain",
    "query_variations": ["screen flickers and battery dies fast"],
    "is_multi_issue": True,
    "sub_issues": ["screen flickering", "battery draining fast"],
}, TokenUsage(prompt_tokens=45, completion_tokens=70))

SINGLE_GOAL_EXTRACTION = ({
    "contexts": [{
        "goal": "Follow these steps to perform this Display Troubleshooting",
        "title": "Screen flicker",
        "score": 0.9,
        "actions": [{
            "actionName": "Display Settings",
            "description": "It will reduce screen flickering issue",
            "category": "auto",
            "stepGroups": [{"steps": ["Open Settings", "Tap Display"]}],
        }],
    }]
}, TokenUsage(prompt_tokens=200, completion_tokens=150))

TWO_GOAL_EXTRACTION = ({
    "contexts": [
        {
            "goal": "Follow these steps to perform this Display Troubleshooting",
            "title": "Screen flicker",
            "score": 0.9,
            "actions": [{
                "actionName": "Display Settings",
                "description": "It will reduce screen flickering issue",
                "category": "auto",
                "stepGroups": [{"steps": ["Open Settings", "Tap Display"]}],
            }],
        },
        {
            "goal": "Follow these steps to perform this Battery Troubleshooting",
            "title": "Battery drain",
            "score": 0.85,
            "actions": [{
                "actionName": "Battery Settings",
                "description": "It will limit background app power usage",
                "category": "auto",
                "stepGroups": [{"steps": ["Open Settings", "Tap Battery"]}],
            }],
        },
    ]
}, TokenUsage(prompt_tokens=350, completion_tokens=280))


@pytest.mark.asyncio
async def test_single_issue_complaint_does_not_trigger_followup_call(fresh_cache):
    """The common case: enrichment reports is_multi_issue=False, so no
    follow-up call fires regardless of what extraction returned."""
    call_count = 0

    async def counting_extract(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return SINGLE_GOAL_EXTRACTION

    with patch.object(orchestrator, "enrich_query_async", return_value=SINGLE_ISSUE_ENRICHMENT), \
         patch.object(orchestrator, "extract_structure_async", side_effect=counting_extract):

        result = await orchestrator.run_pipeline(
            "screen flickers", "some reference", FakeDeeplinkIndex()
        )

    assert call_count == 1, "Single-issue enrichment must NOT trigger a follow-up extraction call"
    assert len(result.response.contexts) == 1


@pytest.mark.asyncio
async def test_multi_issue_agreement_does_not_trigger_followup_call(fresh_cache):
    """If the first (blind) extraction attempt ALREADY returned as many
    contexts as enrichment's sub_issues named, the two mechanisms agree
    and no follow-up call is needed -- avoids paying for a second LLM
    call when the first one already got it right."""
    call_count = 0

    async def counting_extract(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return TWO_GOAL_EXTRACTION  # already produced 2 contexts, matching 2 sub_issues

    with patch.object(orchestrator, "enrich_query_async", return_value=MULTI_ISSUE_ENRICHMENT), \
         patch.object(orchestrator, "extract_structure_async", side_effect=counting_extract):

        result = await orchestrator.run_pipeline(
            "screen flickers and battery dies fast", "reference", FakeDeeplinkIndex()
        )

    assert call_count == 1, "First attempt already matching sub_issues count must not trigger a follow-up"
    assert len(result.response.contexts) == 2


@pytest.mark.asyncio
async def test_multi_issue_disagreement_triggers_followup_and_upgrades_result(fresh_cache):
    """The core follow-up case: first (blind) attempt under-delivers
    (1 context) but enrichment confidently named 2 sub_issues -- a
    follow-up call fires, and its better result (2 contexts) replaces
    the first attempt's."""
    call_log = []

    async def logging_extract(complaint, reference, sub_issues=None):
        call_log.append(sub_issues)
        if sub_issues:
            return TWO_GOAL_EXTRACTION
        return SINGLE_GOAL_EXTRACTION  # first, blind attempt under-delivers

    with patch.object(orchestrator, "enrich_query_async", return_value=MULTI_ISSUE_ENRICHMENT), \
         patch.object(orchestrator, "extract_structure_async", side_effect=logging_extract):

        result = await orchestrator.run_pipeline(
            "screen flickers and battery dies fast", "reference covering both issues", FakeDeeplinkIndex()
        )

    assert len(call_log) == 2
    assert call_log[0] is None  # first, concurrent call -- fired before enrichment resolved
    assert call_log[1] == ["screen flickering", "battery draining fast"]  # the follow-up call

    assert len(result.response.contexts) == 2
    assert result.response.contexts[0].title == "Screen flicker"
    assert result.response.contexts[1].title == "Battery drain"


@pytest.mark.asyncio
async def test_multi_issue_followup_token_usage_is_included(fresh_cache):
    """Cost tracking must account for the extra LLM call the follow-up
    makes -- otherwise reported cost silently undercounts."""
    async def extract(complaint, reference, sub_issues=None):
        return TWO_GOAL_EXTRACTION if sub_issues else SINGLE_GOAL_EXTRACTION

    with patch.object(orchestrator, "enrich_query_async", return_value=MULTI_ISSUE_ENRICHMENT), \
         patch.object(orchestrator, "extract_structure_async", side_effect=extract):

        result = await orchestrator.run_pipeline(
            "screen flickers and battery dies fast", "reference", FakeDeeplinkIndex()
        )

    # enrichment (45+70) + first, blind extraction (200+150)
    # + follow-up extraction (350+280)
    expected_prompt = 45 + 200 + 350
    expected_completion = 70 + 150 + 280
    assert result.meta.prompt_tokens == expected_prompt
    assert result.meta.completion_tokens == expected_completion


@pytest.mark.asyncio
async def test_multi_issue_followup_rate_limit_keeps_first_attempt_result(fresh_cache):
    """If the follow-up call is rate-limited, the request must still
    return the first attempt's (possibly single-issue) plan rather than
    losing the plan entirely."""
    call_count = 0

    async def extract(complaint, reference, sub_issues=None):
        nonlocal call_count
        call_count += 1
        if sub_issues:
            raise LLMRateLimitError("simulated rate limit on followup call")
        return SINGLE_GOAL_EXTRACTION

    with patch.object(orchestrator, "enrich_query_async", return_value=MULTI_ISSUE_ENRICHMENT), \
         patch.object(orchestrator, "extract_structure_async", side_effect=extract):

        result = await orchestrator.run_pipeline(
            "screen flickers and battery dies fast", "reference", FakeDeeplinkIndex()
        )

    assert call_count == 2
    assert len(result.response.contexts) == 1
    assert result.response.fallback is None


@pytest.mark.asyncio
async def test_followup_that_does_worse_than_first_attempt_is_discarded(fresh_cache):
    """Defensive case: if the follow-up call, for whatever reason, returns
    FEWER contexts than the first attempt already had, the first attempt's
    (better) result must be kept -- a follow-up is only ever an upgrade,
    never allowed to make things worse."""
    async def extract(complaint, reference, sub_issues=None):
        if sub_issues:
            return SINGLE_GOAL_EXTRACTION  # follow-up does WORSE than first attempt
        return TWO_GOAL_EXTRACTION  # first, blind attempt already got both

    with patch.object(orchestrator, "enrich_query_async", return_value=MULTI_ISSUE_ENRICHMENT), \
         patch.object(orchestrator, "extract_structure_async", side_effect=extract):

        result = await orchestrator.run_pipeline(
            "screen flickers and battery dies fast", "reference", FakeDeeplinkIndex()
        )

    # First attempt already had 2 contexts matching sub_issues count, so
    # per the "agreement" rule this shouldn't even trigger a follow-up --
    # but this test defends the case regardless (e.g. if that check were
    # ever loosened): a worse follow-up result must never win.
    assert len(result.response.contexts) == 2


@pytest.mark.asyncio
async def test_enrichment_reporting_multi_issue_with_fewer_than_two_subissues_is_ignored(fresh_cache):
    """Defends against a malformed/inconsistent LLM response: is_multi_issue
    true but sub_issues has 0 or 1 entries isn't a real multi-issue case --
    must not trigger the follow-up call."""
    call_count = 0

    async def counting_extract(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return SINGLE_GOAL_EXTRACTION

    malformed_enrichment = ({
        "canonical_query": "screen flickering",
        "query_variations": ["screen flickers"],
        "is_multi_issue": True,
        "sub_issues": ["screen flickering"],  # only one -- inconsistent with is_multi_issue=True
    }, TokenUsage(prompt_tokens=40, completion_tokens=60))

    with patch.object(orchestrator, "enrich_query_async", return_value=malformed_enrichment), \
         patch.object(orchestrator, "extract_structure_async", side_effect=counting_extract):

        result = await orchestrator.run_pipeline(
            "screen flickers", "reference", FakeDeeplinkIndex()
        )

    assert call_count == 1, "A single sub_issue must not trigger the multi-issue follow-up path"
