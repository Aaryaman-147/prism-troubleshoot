"""
Tests against Samsung's REAL Theme-2 files in app/data/ (deeplinks.json,
siis_responses.json, input.txt) and app/data/reference/ (official schema.py,
sample_output.json). These replace assumptions made from screenshots with
checks against the actual data.
"""
import copy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
from unittest.mock import patch

DATA = Path("app/data")
REF = DATA / "reference"
CATALOG = json.loads((DATA / "deeplinks.json").read_text(encoding="utf-8"))
BY_URI = {e["deeplink"]: e for e in CATALOG["deeplinks"]}


def _official_schema():
    spec = importlib.util.spec_from_file_location("official_schema", REF / "official_schema.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


class _E:
    def __init__(self, uri): self.deeplink = uri


def _index(ranking):
    class Idx:
        catalog_by_uri = BY_URI
        def search(self, q, top_k=6, alpha=None):
            return [(_E(u), s) for u, s in ranking[:top_k]]
    return Idx()


def _find(pred):
    return next(e for e in CATALOG["deeplinks"] if pred(e))


class TestRealCatalog:
    def test_real_catalog_loads_through_our_index(self):
        from app.pipeline.deeplink_retrieval import DeeplinkIndex
        n = len(CATALOG["deeplinks"])
        with patch("app.pipeline.deeplink_retrieval.embed_batch", return_value=np.zeros((n, 4))):
            idx = DeeplinkIndex(str(DATA / "deeplinks.json"))
        assert len(idx.catalog_by_uri) == 578
        assert "voiceassist://dummy_positive" in idx.catalog_by_uri

    def test_shape_check_on_real_files_has_no_structural_warnings(self):
        from app.eval.batch import shape_check
        report = shape_check(DATA / "deeplinks.json", DATA / "input.txt", DATA / "siis_responses.json")
        warns = [l for l in report if l.startswith("WARN")]
        assert not any("top-level" in w or "dummy_positive" in w or "object on" in w for w in warns), warns


class TestTwinDisambiguation:
    """138 onURL/offURL pairs share a validation key and differ by one word."""
    ON = _find(lambda e: e["originalType"] == "onURL" and "mouse keys" in e["description"].lower())
    OFF = _find(lambda e: e["originalType"] == "offURL" and "mouse keys" in e["description"].lower())

    def _action(self, name, step):
        return {"actionName": name, "description": "It will change mouse keys setting",
                "category": "auto", "stepGroups": [{"steps": ["Open Settings", "Tap Accessibility", step]}]}

    def test_turn_off_picks_offurl_even_when_onurl_scores_higher(self):
        from app.pipeline.ordering import resolve_deeplinks
        idx = _index([(self.ON["deeplink"], 0.82), (self.OFF["deeplink"], 0.81)])
        acts, amb, _ = resolve_deeplinks([self._action("Disable Mouse Keys", "Turn off Mouse keys")], idx)
        assert acts[0]["stepGroups"][0]["actionableDeeplink"]["deeplink"] == self.OFF["deeplink"]
        assert amb == []   # twins are one setting, not an ambiguity

    def test_turn_on_picks_onurl(self):
        from app.pipeline.ordering import resolve_deeplinks
        idx = _index([(self.OFF["deeplink"], 0.82), (self.ON["deeplink"], 0.81)])
        acts, amb, _ = resolve_deeplinks([self._action("Enable Mouse Keys", "Turn on Mouse keys")], idx)
        assert acts[0]["stepGroups"][0]["actionableDeeplink"]["deeplink"] == self.ON["deeplink"]
        assert amb == []


class TestHybridPolicy:
    def test_settings_action_without_match_gets_dummy_with_written_description(self):
        from app.pipeline.ordering import resolve_deeplinks
        action = {"actionName": "Adjust Motion Smoothness", "description": "It will stop the flicker",
                  "category": "auto", "stepGroups": [{"steps": ["Open Settings", "Tap Display", "Tap Motion smoothness"]}]}
        acts, _, _ = resolve_deeplinks([action], _index([]))
        link = acts[0]["stepGroups"][0]["actionableDeeplink"]
        assert link["deeplink"] == "voiceassist://dummy_positive" and acts[0]["category"] == "auto"
        assert "Motion smoothness" in link["description"]
        assert 5 <= len(link["description"].split()) <= 7 and 5 <= len(link["message"].split()) <= 7

    def test_non_settings_action_becomes_manual_null(self):
        """Mirrors sample_output.json's 'Schedule Screen Repair Service'."""
        from app.pipeline.ordering import resolve_deeplinks
        action = {"actionName": "Schedule Screen Repair Service", "description": "It will find a service center",
                  "category": "auto", "stepGroups": [{"steps": ["Contact Customer Support or visit an authorized Service Center."]}]}
        acts, _, _ = resolve_deeplinks([action], _index([]))
        assert acts[0]["category"] == "manual"
        assert acts[0]["stepGroups"][0]["actionableDeeplink"] is None


class TestSampleOutputReproduction:
    def test_validation_copied_verbatim_like_sample_output(self):
        from app.pipeline.ordering import attach_validation_deeplinks
        sample = json.loads((REF / "sample_output.json").read_text())
        expected = sample["response"]["contexts"][0]["actions"][0]["stepGroups"][0]
        action = {"actionName": "Back Up Phone Data", "category": "auto",
                  "stepGroups": [{"steps": ["x"], "actionableDeeplink": dict(expected["actionableDeeplink"])}]}
        out = attach_validation_deeplinks([action], BY_URI)
        assert out[0]["stepGroups"][0]["validationDeeplink"] == expected["validationDeeplink"]

    def test_sample_and_our_output_both_validate_against_official_schema(self):
        official = _official_schema()
        sample = json.loads((REF / "sample_output.json").read_text())
        official.ContextDeeplinkResponse.model_validate(sample["response"])
        from app.models.schema import ContextDeeplinkResponse as Ours
        ours = Ours.model_validate({"contexts": [{
            "goal": "Follow these steps to perform this Display Troubleshooting", "title": "Screen flicker",
            "score": 0.9, "actions": [{"actionName": "Motion Smoothness", "description": "It will stop the screen flicker",
                                       "category": "auto", "stepGroups": [{"steps": ["Open Settings"]}]}]}]})
        official.ContextDeeplinkResponse.model_validate(ours.model_dump(mode="json"))


class TestRealSiis:
    SIIS = json.loads((DATA / "siis_responses.json").read_text(encoding="utf-8"))["responses"]

    def test_every_real_row_is_cleaned_to_instructions(self):
        from app.pipeline.normalize import normalize_siis
        for r in self.SIIS:
            text = normalize_siis(r["siis_response"])
            assert text.startswith(r["siis_response"]["title"])
            assert "Mobile Accessories):" not in text

    def test_long_documents_are_chunked_for_relevance(self):
        from app.pipeline.relevance import _reference_chunks
        from app.pipeline.normalize import normalize_siis
        longest = max((normalize_siis(r["siis_response"]) for r in self.SIIS), key=len)
        chunks = _reference_chunks(longest)
        assert len(chunks) > 5 and chunks[0] == longest

    def test_runner_loads_input_txt_joined_to_siis(self):
        from app.eval.batch import load_cases
        cases = load_cases(queries_path=DATA / "input.txt", siis_path=DATA / "siis_responses.json")
        assert len(cases) == 20
        assert sum(1 for c in cases if c["siis_response"]) >= 18


class TestOverSplitMerge:
    def test_same_title_contexts_merge(self):
        from app.pipeline.normalize import dedupe_contexts_by_title
        a = {"title": "Phone Overheating", "score": 0.7, "actions": [{"actionName": "A"}]}
        b = {"title": "phone overheating", "score": 0.9, "actions": [{"actionName": "B"}, {"actionName": "A"}]}
        out = dedupe_contexts_by_title([a, b])
        assert len(out) == 1 and out[0]["score"] == 0.9 and [x["actionName"] for x in out[0]["actions"]] == ["A", "B"]


class TestCacheWarm:
    def _rec(self, uri, fallback=None):
        from app.core.config import config_fingerprint
        return {"query": "screen flickers", "query_variations": ["display flicker"],
                "meta": {"config_fingerprint": config_fingerprint()},
                "response": {"fallback": fallback, "contexts": [] if fallback else [{
                    "goal": "Follow these steps to perform this Display Troubleshooting", "title": "Screen flicker",
                    "score": 0.9, "actions": [{"actionName": "Motion Smoothness", "description": "It will stop the screen flicker",
                                               "category": "auto", "stepGroups": [{"steps": ["Open Settings"],
                                               "actionableDeeplink": {"deeplink": uri, "description": "d", "message": "m"}}]}]}]}}

    def test_warm_loads_valid_and_skips_stale_and_fallbacks(self, tmp_path):
        from app.cache.warm import warm_cache
        from app.cache.semantic_cache import SemanticCache
        real = next(iter(BY_URI))
        p = tmp_path / "warm.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in [
            self._rec(real), self._rec("bixby://masked/act/old_placeholder"), self._rec(real, "rate_limited")]))
        c = SemanticCache(hit_threshold=0.85, near_miss_threshold=0.5)
        embeds = iter([np.array([1.0, 0.0])] * 10 + [np.array([0.0, 1.0])] * 10)
        with patch("app.cache.semantic_cache.embed", side_effect=lambda t: np.array([1.0, 0.0]) if "flick" in t else np.array([0.0, 1.0])):
            stats = warm_cache(str(p), c, set(BY_URI))
            assert c.lookup("screen flickers").status == "hit"
        assert stats["loaded"] == 1 and stats["skipped_stale"] == 1 and stats["skipped_fallback"] == 1


class TestMetricsInfra:
    def test_rate_limits_excluded_from_accuracy(self):
        from app.eval.batch import compute_metrics
        rl = {"query": "q", "query_variations": [], "response": {"contexts": [], "fallback": "rate_limited"},
              "meta": {"latency_ms": 1.0, "cache_hit": False, "model": "m", "cost_usd": 0.0}}
        m = compute_metrics([{"result": rl, "expected": "plan", "pass": "main"}])
        assert m["infra_failures"] == 1 and m["expected_judged"] == 0


def test_empty_warm_path_disables_warmup_instead_of_crashing(tmp_path):
    from app.cache.warm import warm_cache
    from app.cache.semantic_cache import SemanticCache
    for path in ("", str(tmp_path)):          # empty string and a directory
        assert warm_cache(path, SemanticCache(), set())["loaded"] == 0


class TestCalibrationHarness:
    def test_probes_reference_real_catalog_messages(self):
        from app.eval.calibrate import load_probes
        messages = {e["message"] for e in CATALOG["deeplinks"]}
        probes = load_probes(DATA / "retrieval_eval_real.json")
        assert len(probes) >= 20
        missing = [p["expected_message"] for p in probes if p["expected_message"] and p["expected_message"] not in messages]
        assert not missing, missing

    def test_classify_verdicts(self):
        from app.eval.calibrate import classify
        uri = next(u for u, e in BY_URI.items() if e["message"] == "Disable Mouse Keys")
        linked = {"stepGroups": [{"actionableDeeplink": {"deeplink": uri}}]}
        dummy = {"stepGroups": [{"actionableDeeplink": {"deeplink": "voiceassist://dummy_positive"}}]}
        none = {"stepGroups": [{"actionableDeeplink": None}]}
        assert classify({"expected_message": "Disable Mouse Keys"}, linked, BY_URI) == "correct"
        assert classify({"expected_message": "Enable Mouse Keys"}, linked, BY_URI) == "wrong"
        assert classify({"expected_message": "Disable Mouse Keys"}, dummy, BY_URI) == "abstain"
        assert classify({"expected_message": None}, linked, BY_URI) == "wrong"
        assert classify({"expected_message": None}, none, BY_URI) == "correct"


class TestRetrievalTextV2:
    def test_v2_adds_validation_key_and_strips_boilerplate(self):
        from app.pipeline.deeplink_retrieval import catalog_search_text
        item = next(e for e in CATALOG["deeplinks"] if e["id"] == "DL-0021")   # generic message, precise key
        v1, v2 = catalog_search_text(item, "v1"), catalog_search_text(item, "v2")
        assert "Adaptive brightness" in v2 and "Adaptive brightness" not in v1
        assert "on the device" in v1 and not v2.split(item["message"])[0].rstrip().endswith("on the device.")

    def test_bare_open_settings_step_dropped_from_match_text(self, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "RETRIEVAL_TEXT_VERSION", "v2")
        from app.pipeline.ordering import _match_text
        t = _match_text({"actionName": "Turn On WiFi", "stepGroups": [{"steps": ["Open Settings.", "Tap Connections.", "Turn on Wi-Fi."]}]})
        assert "Open Settings" not in t and "Tap Connections." in t

    @pytest.mark.parametrize("name,steps,expected", [
        ("Change Screen Timeout", ["Open Settings.", "Tap Display."], "updateURL"),
        ("Open Reset Options", ["Open Settings.", "Tap General management."], "onClickURL"),
        ("Disable Mouse Keys", ["Turn off Mouse keys."], "offURL"),
        ("Back Up Phone Data", ["Open Settings.", "Tap Accounts and backup."], None),
    ])
    def test_intent_covers_all_original_types(self, name, steps, expected):
        from app.pipeline.ordering import _intent
        assert _intent({"actionName": name, "stepGroups": [{"steps": steps}]}) == expected


class TestReferenceAwareCache:
    PLAN = ({"contexts": [{"goal": "Follow these steps to perform this Display Troubleshooting", "title": "Screen fix",
                           "score": 0.9, "actions": [{"actionName": "Restart Phone", "description": "It will refresh the display state",
                                                      "category": "manual", "stepGroups": [{"steps": ["Hold the Side key."]}]}]}]},)

    async def _run(self, orchestrator, query, siis):
        from app.core.llm_client import TokenUsage
        class Idx:
            catalog_by_uri = {}
            def search(self, *a, **k): return []
        from app.pipeline.relevance import RelevanceResult
        async def en(q): return {"canonical_query": q, "query_variations": [], "is_multi_issue": False}, TokenUsage()
        async def ex(q, r, sub_issues=None): return self.PLAN[0], TokenUsage()
        with patch.object(orchestrator, "enrich_query_async", side_effect=en), \
             patch.object(orchestrator, "extract_structure_async", side_effect=ex), \
             patch.object(orchestrator, "verify_relevance", return_value=RelevanceResult(True, 1.0, "ok")):
            return await orchestrator.run_pipeline(query, siis, Idx())

    @pytest.mark.asyncio
    async def test_same_query_different_reference_is_not_served_from_cache(self):
        from app.pipeline import orchestrator
        first = await self._run(orchestrator, "screen went black", "Reference A: restart the phone.")
        same_ref = await self._run(orchestrator, "screen went black", "Reference A: restart the phone.")
        other_ref = await self._run(orchestrator, "screen went black", "Reference B: a different document.")
        no_ref = await self._run(orchestrator, "screen went black", None)
        assert first.meta.cache_hit is False and same_ref.meta.cache_hit is True
        assert other_ref.meta.cache_hit is False, "a plan grounded in a different reference must not be reused"
        assert no_ref.meta.cache_hit is True


def test_config_endpoint_exposes_calibrated_defaults():
    from fastapi.testclient import TestClient
    from app.core.config import settings
    n = len(CATALOG["deeplinks"])
    with patch("app.pipeline.deeplink_retrieval.embed_batch", return_value=np.zeros((n, 4))):
        from app.main import app
        with TestClient(app) as c:
            cfg = c.get("/v1/config").json()
    assert cfg["alpha"] == settings.DEEPLINK_ALPHA and cfg["min_confidence"] == settings.DEEPLINK_MIN_CONFIDENCE


def test_relevance_calibration_pairs_are_genuine_mismatches():
    from app.eval.calibrate import relevance_pairs
    true, false = relevance_pairs(DATA / "siis_responses.json")
    assert len(true) == 20 and len(false) == 20
    titles = {q: s["title"] for q, s in true}
    assert all(s["title"] != titles[q] for q, s in false)
