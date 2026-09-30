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
from unittest.mock import patch

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

    def search(self, query_text, top_k=5, alpha=None):
        class E:
            def __init__(self, uri):
                self.deeplink = uri
        return [(E(uri), score) for uri, score in self._ranking[:top_k]]


def _deeplink_of(result):
    actions = result[0] if isinstance(result, tuple) else result
    sg = actions[0]["stepGroups"][0]
    return (sg.get("actionableDeeplink") or {}).get("deeplink")


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
        """Max-normalization forced the best entry to 1.0 on every query,
        defeating the confidence floor. Coverage normalization (raw score /
        IDF mass of the query's terms) keeps a weak best-match low and a
        strong one high, independent of catalog size."""
        from app.pipeline.deeplink_retrieval import DeeplinkIndex
        norm = DeeplinkIndex._normalize_bm25
        index = type("X", (), {"_bm25": type("B", (), {"idf": {"screen": 2.0, "flicker": 3.0, "fix": 1.0}})()})()
        q = ["screen", "flicker", "fix"]                  # IDF mass = 6.0
        weak = norm(index, np.array([0.9, 0.1, 0.0]), q)
        strong = norm(index, np.array([5.7, 0.1, 0.0]), q)
        assert weak.max() < 0.2, "a weak best-match must not saturate to ~1.0"
        assert strong.max() > 0.8
        assert norm(index, np.array([60.0]), q).max() == 1.0   # clipped

    def test_repeated_query_words_do_not_inflate_coverage(self):
        """Real-catalog regression: 'service' repeated in the match text
        pushed a repair action to 0.86 coverage on one shared word."""
        from app.pipeline.deeplink_retrieval import tokenize
        assert tokenize("Tap Mouse keys. Turn OFF keys!") == ["tap", "mouse", "keys", "turn", "off", "keys"]
        assert list(dict.fromkeys(tokenize("service service Service"))) == ["service"]


class TestAmbiguousMatchesSurfaced:
    def test_near_tie_is_returned_as_ambiguous_not_just_discarded(self):
        """The margin-abstain case previously just dropped the runner-up.
        Both candidates must now be returned so a caller can disambiguate."""
        index = FakeIndex([("bixby://a", 0.60), ("bixby://b", 0.59)])
        actions, ambiguous, confidence = resolve_deeplinks(
            [copy.deepcopy(MOTION_SMOOTHNESS_ACTION)], index
        )
        assert len(ambiguous) == 1
        assert ambiguous[0]["actionName"] == "Motion Smoothness"
        deeplinks = {c["deeplink"] for c in ambiguous[0]["candidates"]}
        assert deeplinks == {"bixby://a", "bixby://b"}
        assert confidence == {}  # nothing confidently resolved

    def test_low_confidence_floor_reject_is_not_reported_as_ambiguous(self):
        """A single weak match (floor rejection) is a different failure mode
        from two close matches (margin rejection) — must not conflate them
        into the same "ambiguous" bucket."""
        index = FakeIndex([("bixby://a", 0.20), ("bixby://b", 0.01)])
        actions, ambiguous, confidence = resolve_deeplinks(
            [copy.deepcopy(MOTION_SMOOTHNESS_ACTION)], index
        )
        assert ambiguous == []
        assert confidence == {}

    def test_confident_match_is_recorded_in_confidences(self):
        index = FakeIndex([("bixby://a", 0.80), ("bixby://b", 0.10)])
        actions, ambiguous, confidence = resolve_deeplinks(
            [copy.deepcopy(MOTION_SMOOTHNESS_ACTION)], index
        )
        assert ambiguous == []
        assert confidence == {"Motion Smoothness": 0.80}


class TestValidationDeeplinkWiring:
    def test_llm_expected_outcome_never_produces_validation_without_catalog(self):
        """Validation deeplinks are catalog data only. An LLM-proposed
        expectedOutcome with no catalog validation entry yields nothing
        (previously it reused the actionable URI with an invented key)."""
        action = copy.deepcopy(MOTION_SMOOTHNESS_ACTION)
        action["stepGroups"][0]["actionableDeeplink"] = {"deeplink": "bixby://masked/act/display_brightness"}
        action["expectedOutcome"] = {"key": "motion_smoothness_mode", "resultType": "str",
                                     "condition": "equal", "value": "Standard"}
        from app.pipeline.ordering import attach_validation_deeplinks
        result = attach_validation_deeplinks([action], {})
        assert "validationDeeplink" not in result[0]["stepGroups"][0]
        assert "expectedOutcome" not in result[0]

    def test_no_actionable_deeplink_means_no_validation_deeplink(self):
        """Nothing to verify against if nothing was resolved — must not
        attach a validation target when there's no actionable one."""
        from app.pipeline.ordering import attach_validation_deeplinks

        action = copy.deepcopy(MOTION_SMOOTHNESS_ACTION)
        action["expectedOutcome"] = {
            "key": "x", "resultType": "str", "condition": "equal", "value": "y",
        }
        result = attach_validation_deeplinks([action])
        assert "validationDeeplink" not in result[0]["stepGroups"][0]

    def test_malformed_expected_outcome_is_silently_dropped(self):
        """A bonus field should degrade gracefully, not raise, on bad LLM
        output — missing/invalid resultType or condition here."""
        from app.pipeline.ordering import attach_validation_deeplinks

        action = copy.deepcopy(MOTION_SMOOTHNESS_ACTION)
        action["expectedOutcome"] = {"key": "x", "resultType": "not_a_real_type"}
        action["stepGroups"][0]["actionableDeeplink"] = {
            "deeplink": "bixby://masked/act/display_brightness",
            "description": "d", "message": "",
        }
        result = attach_validation_deeplinks([action])  # must not raise
        assert "validationDeeplink" not in result[0]["stepGroups"][0]

    def test_missing_expected_outcome_is_a_noop(self):
        from app.pipeline.ordering import attach_validation_deeplinks

        action = copy.deepcopy(MOTION_SMOOTHNESS_ACTION)
        action["stepGroups"][0]["actionableDeeplink"] = {
            "deeplink": "bixby://masked/act/display_brightness",
            "description": "d", "message": "",
        }
        result = attach_validation_deeplinks([action])  # must not raise
        assert "validationDeeplink" not in result[0]["stepGroups"][0]


class TestAlphaOverride:
    def test_search_alpha_override_changes_ranking_without_rebuilding_index(self):
        """Per-call alpha must actually change fusion, proving the live
        demo slider would have a real effect — not just accept the param."""
        from app.pipeline.deeplink_retrieval import DeeplinkIndex
        import numpy as np

        idx = DeeplinkIndex.__new__(DeeplinkIndex)
        idx.alpha = 0.5
        idx.bm25_saturation_k = 3.0

        class E:
            def __init__(self, name):
                self.deeplink = name

        idx.entries = [E("a"), E("b")]
        idx._catalog_by_uri = {"a": {}, "b": {}}

        class FakeBM25:
            idf = {}
            def get_scores(self, tokens):
                return np.array([10.0, 0.0])  # a wins on BM25

        idx._bm25 = FakeBM25()
        idx._dense_matrix = np.array([[1.0, 0.0], [0.0, 1.0]])  # b wins on dense (row 1 . q_vec)

        with patch("app.pipeline.deeplink_retrieval.embed", return_value=np.array([0.0, 1.0])):
            bm25_leaning = idx.search("query", top_k=1, alpha=0.0)
            dense_leaning = idx.search("query", top_k=1, alpha=1.0)

        assert bm25_leaning[0][0].deeplink == "a"
        assert dense_leaning[0][0].deeplink == "b"


class TestDummyPositiveFallback:
    """These tests cover the OPTIONAL dummy_positive policy (spec PDF). The
    default is now manual_null per Samsung's meeting guidance -- see
    TestManualNullPolicy below."""

    @pytest.fixture(autouse=True)
    def _dummy_policy(self, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "UNMATCHED_AUTO_POLICY", "dummy_positive")

    """
    bixby://dummy_positive is a real catalog entry (per the theme spec:
    "reserved generic placeholder used exclusively when a step opens a
    valid Settings screen not currently indexed in the catalog"), not a
    code constant. Left to compete in normal ranking it's effectively dead
    (its own description is generic filler text that rarely wins) -- these
    tests confirm it's used as an explicit fallback instead, and never
    contaminates normal matching or the ambiguous-candidates list.
    """

    def _index_with_dummy(self, ranking):
        catalog = {uri: {"description": f"desc for {uri}", "message": f"msg for {uri}"}
                   for uri, _ in ranking}
        catalog["bixby://dummy_positive"] = {
            "description": "Generic placeholder for unindexed but valid settings screen",
            "message": "Opens a valid settings screen not currently in catalog",
        }

        class E:
            def __init__(self, uri):
                self.deeplink = uri

        class Idx:
            def __init__(self):
                self.catalog_by_uri = catalog

            def search(self, query_text, top_k=3, alpha=None):
                return [(E(uri), score) for uri, score in ranking[:top_k]]

        return Idx()

    def test_low_confidence_action_falls_back_to_dummy_positive(self):
        index = self._index_with_dummy([("bixby://a", 0.20), ("bixby://b", 0.01)])
        actions, ambiguous, confidence = resolve_deeplinks(
            [copy.deepcopy(MOTION_SMOOTHNESS_ACTION)], index
        )
        sg = actions[0]["stepGroups"][0]
        assert sg["actionableDeeplink"]["deeplink"] == "bixby://dummy_positive"
        assert confidence == {}  # dummy fallback isn't a confident real match

    def test_ambiguous_action_gets_both_dummy_fallback_and_candidates(self):
        """The auto action still carries SOME actionable deeplink (the
        placeholder) even while the real disambiguation is offered
        separately via ambiguous_matches."""
        index = self._index_with_dummy([("bixby://a", 0.60), ("bixby://b", 0.59)])
        actions, ambiguous, confidence = resolve_deeplinks(
            [copy.deepcopy(MOTION_SMOOTHNESS_ACTION)], index
        )
        sg = actions[0]["stepGroups"][0]
        assert sg["actionableDeeplink"]["deeplink"] == "bixby://dummy_positive"
        assert len(ambiguous) == 1
        assert {c["deeplink"] for c in ambiguous[0]["candidates"]} == {"bixby://a", "bixby://b"}

    def test_confident_match_never_uses_dummy_positive(self):
        index = self._index_with_dummy([("bixby://a", 0.80), ("bixby://b", 0.10)])
        actions, ambiguous, confidence = resolve_deeplinks(
            [copy.deepcopy(MOTION_SMOOTHNESS_ACTION)], index
        )
        sg = actions[0]["stepGroups"][0]
        assert sg["actionableDeeplink"]["deeplink"] == "bixby://a"

    def test_dummy_positive_itself_is_never_offered_as_a_normal_or_ambiguous_match(self):
        """If dummy_positive happens to rank highly on its own generic text
        (weak query), it must be filtered before floor/margin logic --
        never attached as if it were a real specific match, and never
        listed alongside real candidates in ambiguous_matches."""
        index = self._index_with_dummy([
            ("bixby://dummy_positive", 0.90),  # ranks first on its own vague text
            ("bixby://a", 0.85),
            ("bixby://b", 0.10),
        ])
        actions, ambiguous, confidence = resolve_deeplinks(
            [copy.deepcopy(MOTION_SMOOTHNESS_ACTION)], index
        )
        sg = actions[0]["stepGroups"][0]
        # "a" at 0.85 clears the floor and isn't ambiguous against "b" at
        # 0.10 once dummy_positive is filtered out of the ranking.
        assert sg["actionableDeeplink"]["deeplink"] == "bixby://a"
        assert ambiguous == []

    def test_missing_dummy_positive_in_catalog_degrades_to_no_deeplink(self):
        """Defensive: if a future/real catalog doesn't include the
        placeholder, fall back to the old behavior (no deeplink) rather
        than crashing."""
        class E:
            def __init__(self, uri):
                self.deeplink = uri

        class IdxNoDummy:
            catalog_by_uri = {"bixby://a": {"description": "d", "message": "m"}}

            def search(self, query_text, top_k=3, alpha=None):
                return [(E("bixby://a"), 0.20)]  # below floor

        actions, ambiguous, confidence = resolve_deeplinks(
            [copy.deepcopy(MOTION_SMOOTHNESS_ACTION)], IdxNoDummy()
        )
        sg = actions[0]["stepGroups"][0]
        # No placeholder available -> degrades to the manual/null policy.
        assert sg.get("actionableDeeplink") is None
        assert actions[0]["category"] == "manual"
