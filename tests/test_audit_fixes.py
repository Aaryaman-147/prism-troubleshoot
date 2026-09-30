"""
Regression tests for the full-pipeline audit. Each test pins a concrete
defect found by reading the code against Samsung's real data shapes
(deeplinks.json / siis_responses.json / sample_output.json) and the
Theme-2 meeting guidance.

Run with: pytest tests/test_audit_fixes.py -v
"""
import copy
import json

import numpy as np
import pytest
from unittest.mock import patch

from app.pipeline.normalize import (
    clean_siis_content, normalize_siis, normalize_category, normalize_variations,
)
from app.pipeline.ordering import resolve_deeplinks, attach_validation_deeplinks, order_actions
from app.models.schema import Action, StepGroup, TroubleshootRequest, SiisPayload
from app.utils.validators import repair_action_name, repair_description

SAMSUNG_CONTENT = ("Smartphone,Others Mobile,Tablet,Mobile Accessories Blank or black display "
                   "on a smartphone or tablet ( Smartphone,Others Mobile,Tablet,Mobile Accessories): "
                   "Restart the device. If the screen stays black, check the brightness setting.")


class TestSiisNormalization:
    def test_category_tag_prefix_and_parenthetical_are_stripped(self):
        out = clean_siis_content("Blank or black display on a smartphone or tablet", SAMSUNG_CONTENT)
        assert out.startswith("Restart the device.")
        assert "Mobile Accessories" not in out

    def test_object_payload_normalizes_to_title_plus_clean_body(self):
        text = normalize_siis({"title": "Blank or black display on a smartphone or tablet",
                               "content": SAMSUNG_CONTENT})
        assert text.startswith("Blank or black display")
        assert "Restart the device." in text and "Mobile Accessories" not in text

    def test_plain_string_passes_through(self):
        assert normalize_siis("  Open Settings.  ") == "Open Settings."

    def test_none_and_empty(self):
        assert normalize_siis(None) == "" and normalize_siis({"title": "", "content": ""}) == ""

    def test_real_instructions_before_title_are_never_dropped(self):
        """Only a tag-list-looking prefix is stripped, not sentences."""
        content = "Check this first. Battery drain fix: disable background apps."
        assert "Check this first." in clean_siis_content("Battery drain fix", content)

    def test_api_accepts_samsung_object_shape(self):
        req = TroubleshootRequest(query="screen black", siis_response={"title": "t", "content": "c"})
        assert isinstance(req.siis_response, SiisPayload)


class TestCategoryAndVariations:
    @pytest.mark.parametrize("raw,expected", [
        ("Auto", "auto"), (" critical ", "critical"), ("safe", "manual"), (None, "manual")])
    def test_category_normalization(self, raw, expected):
        assert normalize_category(raw) == expected

    def test_ordering_never_crashes_on_unknown_category(self):
        """Previously Enum('Auto') raised outside any try -> HTTP 500."""
        out = order_actions([{"category": "CRITICAL"}, {"category": "Auto"}, {"category": "weird"}])
        assert [a["category"] for a in out] == ["Auto", "weird", "CRITICAL"]

    def test_variations_deduped_query_removed_and_capped(self):
        v = ["A b", "a B", "screen flickers", "x"] + [f"p{i}" for i in range(15)]
        out = normalize_variations(v, "Screen flickers")
        assert out[0] == "A b" and "screen flickers" not in [x.lower() for x in out]
        assert len(out) == 10


class TestSchemaRepairs:
    def test_acronyms_are_valid_title_case(self):
        Action(actionName="Configure NFC Settings", description="It will enable tap to pay",
               stepGroups=[StepGroup(steps=["Open Settings"])])

    def test_lowercase_word_still_rejected(self):
        with pytest.raises(Exception):
            Action(actionName="Configure nfc Settings", description="It will enable tap to pay",
                   stepGroups=[StepGroup(steps=["Open Settings"])])

    def test_repair_action_name_preserves_acronyms(self):
        assert repair_action_name("configure NFC settings") == "Configure NFC Settings"

    def test_repair_description_trims_long_and_leaves_short(self):
        long = "It will reduce flicker and save a lot of battery quickly"
        assert 5 <= len(repair_description(long).split()) <= 7
        assert repair_description("It will fix it") == "It will fix it"


class _E:
    def __init__(self, uri):
        self.deeplink = uri


def _index(ranking, catalog):
    class Idx:
        catalog_by_uri = catalog
        def search(self, q, top_k=3, alpha=None):
            return [(_E(u), s) for u, s in ranking[:top_k]]
    return Idx()


ACTION = {"actionName": "Motion Smoothness", "description": "It will stop screen flicker",
          "category": "auto", "stepGroups": [{"steps": ["Open Settings", "Tap Display"]}]}


class TestManualNullPolicy:
    """Samsung meeting: 'If no relevant deeplink exists, set it to None/null
    and mark the action as manual.' This is now the default."""

    def test_unmatched_auto_becomes_manual_with_null_deeplink(self, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "UNMATCHED_AUTO_POLICY", "manual_null")
        idx = _index([("voiceassist://masked/act/a", 0.10)],
                     {"voiceassist://masked/act/a": {}, "voiceassist://dummy_positive": {}})
        actions, _, conf = resolve_deeplinks([copy.deepcopy(ACTION)], idx)
        assert actions[0]["category"] == "manual"
        assert actions[0]["stepGroups"][0]["actionableDeeplink"] is None
        assert conf == {}

    def test_confident_match_stays_auto_and_carries_original_type(self):
        idx = _index([("voiceassist://masked/act/a", 0.90), ("voiceassist://masked/act/b", 0.10)],
                     {"voiceassist://masked/act/a": {"description": "d", "message": "m", "originalType": "onURL"},
                      "voiceassist://masked/act/b": {}})
        actions, _, _ = resolve_deeplinks([copy.deepcopy(ACTION)], idx)
        link = actions[0]["stepGroups"][0]["actionableDeeplink"]
        assert actions[0]["category"] == "auto"
        assert link["deeplink"] == "voiceassist://masked/act/a" and link["originalType"] == "onURL"


class TestCatalogValidationDeeplink:
    def test_validation_comes_from_catalog_not_reused_actionable(self):
        """Samsung's catalog entries carry their own validation {deeplink, key}."""
        catalog = {"voiceassist://masked/act/a": {
            "validation": {"deeplink": "voiceassist://masked/val/v1", "key": "Motion smoothness"}}}
        action = copy.deepcopy(ACTION)
        action["stepGroups"][0]["actionableDeeplink"] = {"deeplink": "voiceassist://masked/act/a"}
        action["expectedOutcome"] = {"key": "llm_key", "resultType": "str", "condition": "equal", "value": "Standard"}
        out = attach_validation_deeplinks([action], catalog)
        v = out[0]["stepGroups"][0]["validationDeeplink"]
        assert v["deeplink"] == "voiceassist://masked/val/v1"
        assert v["key"] == "Motion smoothness"          # catalog key, not LLM-invented
        # Catalog entry has no resultType/value -> none are invented from the LLM
        assert "value" not in v and "condition" not in v


class TestCatalogShape:
    def test_samsung_wrapped_catalog_loads(self, tmp_path):
        """Real deeplinks.json is {"_readme","count","deeplinks":[...]} — the
        bare-list loader crashed on it at startup."""
        p = tmp_path / "deeplinks.json"
        p.write_text(json.dumps({"_readme": "x", "count": 1, "deeplinks": [
            {"id": "DL-0001", "deeplink": "voiceassist://masked/act/a", "description": "Opens display settings"}]}))
        with patch("app.pipeline.deeplink_retrieval.embed_batch", return_value=np.array([[1.0, 0.0]])):
            from app.pipeline.deeplink_retrieval import DeeplinkIndex
            idx = DeeplinkIndex(str(p))
        assert "voiceassist://masked/act/a" in idx.catalog_by_uri


class TestOrchestratorAuditPaths:
    @pytest.fixture
    def fresh(self):
        from app.cache.semantic_cache import SemanticCache
        from app.pipeline import orchestrator
        c = SemanticCache(hit_threshold=0.85, near_miss_threshold=0.5)
        with patch("app.cache.semantic_cache.embed", return_value=np.array([1.0, 0.0])), \
             patch.object(orchestrator, "cache", c):
            yield orchestrator

    @pytest.mark.asyncio
    async def test_no_reference_skips_llm_and_returns_no_siis_context(self, fresh):
        with patch.object(fresh, "extract_structure_async") as ex, \
             patch.object(fresh, "enrich_query_async") as en:
            r = await fresh.run_pipeline("phone gets hot", None, _index([], {}))
            ex.assert_not_called(); en.assert_not_called()
        assert r.response.fallback == "no_siis_context"
        assert r.response.fallback_reason


class TestSecondAudit:
    def test_goal_suffix_repaired(self):
        from app.utils.validators import repair_goal
        assert repair_goal("Follow these steps to perform this Display") == \
            "Follow these steps to perform this Display Troubleshooting"
        assert repair_goal("Follow these steps to perform this Wi-Fi Configuration") == \
            "Follow these steps to perform this Wi-Fi Configuration"
        assert repair_goal("Fix the display", "screen flicker") == \
            "Follow these steps to perform this Screen Flicker Troubleshooting"

    def test_title_sentence_case(self):
        from app.utils.validators import repair_title_case
        assert repair_title_case("screen flicker") == "Screen flicker"
        assert repair_title_case("NFC payments") == "NFC payments"

    def test_prompts_agree_on_signature_example(self):
        """Enrichment used 'screen flickers AND battery dies fast' as its
        multi-issue example while extraction called it one issue -> the
        follow-up call fired on the team's own demo query every time."""
        from app.pipeline.enrichment import ENRICHMENT_PROMPT_TEMPLATE
        assert "battery dies fast\" is usually a single" in ENRICHMENT_PROMPT_TEMPLATE

    def test_cache_hit_returns_generated_variations(self):
        from app.cache.semantic_cache import SemanticCache
        from app.models.schema import ContextDeeplinkResponse
        c = SemanticCache(hit_threshold=0.85, near_miss_threshold=0.5)
        with patch("app.cache.semantic_cache.embed", return_value=np.array([1.0, 0.0])):
            c.insert_new_cluster("q", ContextDeeplinkResponse(), seed_texts=["q"],
                                 variations=[f"p{i}" for i in range(9)])
            hit = c.lookup("q")
        assert hit.status == "hit" and len(hit.cluster.variations) == 9

    @pytest.mark.asyncio
    async def test_mismatch_reports_relevance_not_as_cache_similarity(self):
        from app.cache.semantic_cache import SemanticCache
        from app.pipeline import orchestrator
        emb = lambda t: np.array([1.0, 0.0]) if "battery" in t.lower() else np.array([0.0, 1.0])
        with patch("app.pipeline.relevance.embed", side_effect=emb), \
             patch("app.cache.semantic_cache.embed", side_effect=emb), \
             patch.object(orchestrator, "cache", SemanticCache()):
            r = await orchestrator.run_pipeline("battery drains", "swipe gestures reversed", _index([], {}))
        assert r.response.fallback == "siis_mismatch"
        assert r.meta.relevance_similarity is not None and r.meta.cache_similarity is None
