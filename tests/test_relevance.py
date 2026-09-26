"""
Tests for SIIS relevance verification (app/pipeline/relevance.py) — the
Samsung-requested check that reference text actually addresses the
complaint before extraction attempts to build a plan from it.

Run with: pytest tests/test_relevance.py -v
"""
import numpy as np
import pytest
from unittest.mock import patch

from app.pipeline.relevance import verify_relevance


def fake_embed(text: str) -> np.ndarray:
    """Keyword-presence pseudo-embedding — same trick used elsewhere in
    this suite. Topically related text (shared vocabulary) scores high
    similarity; unrelated text scores low.

    Uses word-boundary matching (exact word or a >=4-char substring
    match) rather than naive `w in v or v in w`, which spuriously matches
    tiny words like "a"/"to" against any vocab word containing that
    letter sequence (e.g. "a" is a substring of "battery" and "drain") —
    that bug inflated similarity for genuinely unrelated text in an
    earlier version of this fixture."""
    vocab = ["screen", "flicker", "battery", "drain", "swipe", "gesture",
              "navigation", "storage", "full", "camera", "crash"]
    words = {w for w in text.lower().split() if len(w) >= 4}
    vec = np.array([
        1.0 if any(v in w or w in v for w in words) else 0.0
        for v in vocab
    ])
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


@pytest.fixture(autouse=True)
def patched_embed():
    with patch("app.pipeline.relevance.embed", side_effect=fake_embed):
        yield


class TestRelevanceVerification:
    def test_matching_complaint_and_reference_is_relevant(self):
        result = verify_relevance(
            "screen flickers and battery drains fast",
            "Display flicker is caused by a stuck refresh rate; battery drain is often "
            "caused by background apps.",
        )
        assert result.is_relevant is True

    def test_mismatched_complaint_and_reference_is_not_relevant(self):
        """The exact scenario Samsung asked to catch: reference text about
        a completely different domain than the complaint."""
        result = verify_relevance(
            "screen flickers and battery drains fast",
            "Swipe gesture navigation can default to scroll-style movement after "
            "installing a new app.",
        )
        assert result.is_relevant is False
        assert "below threshold" in result.reason

    def test_empty_reference_is_treated_as_relevant_not_mismatched(self):
        """An EMPTY reference is a different case from a MISMATCHED one —
        that's handled downstream by extraction's own no_match fallback
        ('no source material'). This function's job is specifically
        catching a present-but-wrong reference, so empty must not be
        flagged as a relevance failure (which would produce a confusing
        'mismatch' reason for what's actually just 'nothing given')."""
        result = verify_relevance("screen flickers", "")
        assert result.is_relevant is True
        assert result.reason == "no_reference_provided"

    def test_whitespace_only_reference_is_treated_as_empty(self):
        result = verify_relevance("screen flickers", "   \n  ")
        assert result.is_relevant is True
        assert result.reason == "no_reference_provided"

    def test_custom_threshold_override(self):
        """A caller can override the default threshold — e.g. for tuning
        experiments, matching the pattern already used for deeplink
        confidence/margin overrides."""
        # A borderline-similarity pair: some shared vocabulary, not total overlap.
        complaint = "screen flickers"
        reference = "screen navigation gesture settings"

        lenient = verify_relevance(complaint, reference, min_similarity=0.1)
        strict = verify_relevance(complaint, reference, min_similarity=0.9)

        assert lenient.is_relevant is True
        assert strict.is_relevant is False

    def test_similarity_score_is_reported(self):
        """The similarity score itself must be surfaced, not just the
        boolean verdict — needed for both debugging and for the frontend
        to potentially show it (matching the pattern used for deeplink
        confidence)."""
        result = verify_relevance(
            "screen flickers and battery drains fast",
            "Display flicker is caused by a stuck refresh rate.",
        )
        assert 0.0 <= result.similarity <= 1.0


class TestFallbackReasonSurfacing:
    """
    Confirms the orchestrator-level integration: a SIIS mismatch produces
    a human-readable fallback_reason, not just the bare fallback code —
    directly implementing Samsung's "design explicit abstention behavior"
    guidance for a demo/judge audience, not just internal logs.
    """

    @pytest.mark.asyncio
    async def test_siis_mismatch_includes_human_readable_reason(self):
        import asyncio
        from unittest.mock import patch as patch2
        from app.pipeline import orchestrator

        class FakeDeeplinkIndex:
            def __init__(self):
                self.catalog_by_uri = {}
            def search(self, query_text, top_k=1, alpha=None):
                return []

        def mismatched_embed(text):
            # Query and reference embed to orthogonal vectors -> guaranteed mismatch
            if "battery" in text.lower():
                return np.array([1.0, 0.0])
            return np.array([0.0, 1.0])

        with patch2("app.pipeline.relevance.embed", side_effect=mismatched_embed):
            result = await orchestrator.run_pipeline(
                "my battery drains fully within 3 hours",
                "Swipe gesture navigation defaults to scroll-style movement.",
                FakeDeeplinkIndex(),
            )

        assert result.response.fallback == "siis_mismatch"
        assert result.response.fallback_reason is not None
        assert "reference material" in result.response.fallback_reason.lower()
