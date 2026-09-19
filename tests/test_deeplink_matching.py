"""
Tests for deeplink match-text construction, the confidence floor and the
ambiguity margin (app/pipeline/ordering.py + app/pipeline/deeplink_retrieval.py).

These cover the "confidently wrong deeplink" class of bug: attaching a
plausible-looking but incorrect settings screen to an action. A wrong
deeplink is worse than a missing one — it fails the spec's screen-resolution
scoring while looking correct to a user.

Run with: pytest tests/test_deeplink_matching.py -v
"""
import copy

import numpy as np
import pytest

from app.pipeline.ordering import _match_text, resolve_deeplinks


MOTION_SMOOTHNESS_ACTION = {
    "actionName": "Motion Smoothness",
    "description": "It will stop flicker and save battery",
    "category": "auto",
    "stepGroups": [{"steps": [
        "Open Settings", "Tap Display", "Tap Motion smoothness", "Select Standard",
    ]}],
}


class FakeIndex:
    """Returns a scripted ranking so the floor/margin logic can be tested
    without the real catalog, BM25 index or embedding model."""

    def __init__(self, ranking):
        self._ranking = ranking
        self.catalog_by_uri = {
            uri: {"description": f"desc for {uri}", "message": ""}
            for uri, _ in ranking
        }

    def search(self, query_text, top_k=5):
        class E:
            def __init__(self, uri):
                self.deeplink = uri
        return [(E(uri), score) for uri, score in self._ranking[:top_k]]


def _deeplink_of(actions):
    sg = actions[0]["stepGroups"][0]
    return sg.get("actionableDeeplink", {}).get("deeplink")


class TestMatchText:
    def test_benefit_description_is_excluded_from_match_text(self):
        """The description says "save battery" but the destination is a
        DISPLAY screen — including it is what pulled back a battery deeplink
        for a display fix in the demo."""
        text = _match_text(MOTION_SMOOTHNESS_ACTION).lower()
        assert "battery" not in text
        assert "motion smoothness" in text
        assert "tap display" in text

    def test_action_name_is_weighted_above_step_text(self):
        text = _match_text(MOTION_SMOOTHNESS_ACTION).lower()
        assert text.count("motion smoothness") >= 2


class TestConfidenceFloorAndMargin:
    def test_low_confidence_top_match_is_rejected(self):
        index = FakeIndex([("bixby://a", 0.20), ("bixby://b", 0.01)])
        result = resolve_deeplinks([copy.deepcopy(MOTION_SMOOTHNESS_ACTION)], index)
        assert _deeplink_of(result) is None

    def test_confident_unambiguous_match_is_attached(self):
        index = FakeIndex([("bixby://a", 0.80), ("bixby://b", 0.10)])
        result = resolve_deeplinks([copy.deepcopy(MOTION_SMOOTHNESS_ACTION)], index)
        assert _deeplink_of(result) == "bixby://a"

    def test_near_tie_abstains_rather_than_guessing(self):
        """Two entries score almost identically: the index has no real basis
        for preferring either, so sending the user to an arbitrary one is a
        coin flip dressed up as an answer."""
        index = FakeIndex([("bixby://a", 0.60), ("bixby://b", 0.59)])
        result = resolve_deeplinks([copy.deepcopy(MOTION_SMOOTHNESS_ACTION)], index)
        assert _deeplink_of(result) is None

    def test_manual_actions_never_get_deeplinks(self):
        action = copy.deepcopy(MOTION_SMOOTHNESS_ACTION)
        action["category"] = "manual"
        index = FakeIndex([("bixby://a", 0.95), ("bixby://b", 0.10)])
        result = resolve_deeplinks([action], index)
        assert _deeplink_of(result) is None


class TestBM25Normalization:
    def test_weak_top_match_does_not_score_one(self):
        """Max-normalization forced the best entry to exactly 1.0 on every
        query regardless of match quality, which structurally defeated the
        confidence floor. The saturating transform must keep weak matches low.
        """
        from app.pipeline.deeplink_retrieval import DeeplinkIndex
        norm = DeeplinkIndex._normalize_bm25
        index = type("X", (), {"bm25_saturation_k": 3.0})()
        weak = norm(index, np.array([0.3, 0.1, 0.0]))
        strong = norm(index, np.array([30.0, 0.1, 0.0]))
        assert weak.max() < 0.2, "a weak best-match must not saturate to ~1.0"
        assert strong.max() > 0.8
        assert weak.max() < strong.max()
