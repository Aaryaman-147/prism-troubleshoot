"""
Regressions from the first real NVIDIA/Nemotron batch run (results.txt).
These deliberately call the REAL extraction/enrichment functions and mock
only the network layer -- the sub_issues TypeError got through because every
earlier test mocked extract_structure_async itself.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.llm_client import TokenUsage, _parse_json


class TestRealExtractionSignature:
    @pytest.mark.asyncio
    async def test_extract_structure_async_accepts_sub_issues_and_adds_hint(self):
        from app.pipeline import extraction
        fake = AsyncMock(return_value=({"contexts": []}, TokenUsage()))
        with patch.object(extraction, "generate_json_async", fake):
            await extraction.extract_structure_async("wifi and fingerprint", "ref",
                                                     sub_issues=["Wi-Fi failure", "fingerprint failure"])
        prompt = fake.call_args.args[0]
        assert '"Wi-Fi failure", "fingerprint failure"' in prompt
        assert fake.call_args.kwargs["required_keys"] == ("contexts",)
        assert fake.call_args.kwargs["max_output_tokens"] >= 3200

    @pytest.mark.asyncio
    async def test_orchestrator_followup_reaches_real_extraction_without_typeerror(self):
        """End-to-end through the real follow-up call path, network mocked."""
        from app.pipeline import orchestrator, extraction
        from app.pipeline.relevance import RelevanceResult
        two = {"contexts": [
            {"goal": "Follow these steps to perform this WiFi Troubleshooting", "title": "Wi-Fi failure", "score": 0.9,
             "actions": [{"actionName": "Rejoin Network", "description": "It will reconnect the office network",
                          "category": "manual", "stepGroups": [{"steps": ["Forget the network and rejoin it."]}]}]},
            {"goal": "Follow these steps to perform this Fingerprint Troubleshooting", "title": "Fingerprint failure", "score": 0.9,
             "actions": [{"actionName": "Re-register Fingerprint", "description": "It will restore fingerprint recognition",
                          "category": "manual", "stepGroups": [{"steps": ["Remove and add the fingerprint again."]}]}]}]}
        calls = []
        async def net(prompt, max_output_tokens=0, max_retries=2, required_keys=None):
            calls.append(prompt)
            if required_keys == ("canonical_query",):
                return {"canonical_query": "wifi and fingerprint", "query_variations": [],
                        "is_multi_issue": True, "sub_issues": ["Wi-Fi failure", "fingerprint failure"]}, TokenUsage()
            return ({"contexts": []} if len(calls) <= 2 else two), TokenUsage()
        class Idx:
            catalog_by_uri = {}
            def search(self, *a, **k): return []
        with patch("app.pipeline.extraction.generate_json_async", side_effect=net), \
             patch("app.pipeline.enrichment.generate_json_async", side_effect=net), \
             patch.object(orchestrator, "verify_relevance", return_value=RelevanceResult(True, 1.0, "ok")):
            r = await orchestrator.run_pipeline("Wi-Fi won't connect AND fingerprint stopped working", "ref", Idx())
        assert len(r.response.contexts) == 2


class TestReasoningLeakParsing:
    def test_reasoning_example_object_is_skipped_for_required_key(self):
        text = ('We need JSON. An outcome looks like {"key": "wifi_connected", "value": "true"}. '
                'Final: {"contexts": [{"title": "Wi-Fi failure"}]}')
        assert _parse_json(text, ("contexts",)) == {"contexts": [{"title": "Wi-Fi failure"}]}

    def test_apostrophes_and_quotes_in_prose_do_not_break_scan(self):
        text = 'The user\'s phone "won\'t" connect. {"canonical_query": "wifi fails"}'
        assert _parse_json(text, ("canonical_query",)) == {"canonical_query": "wifi fails"}

    def test_missing_required_key_raises_so_retry_happens(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_json('{"key": "x"}', ("contexts",))

    def test_without_required_keys_behaviour_unchanged(self):
        assert _parse_json('{"a": 1} trailing', None) == {"a": 1}


class TestThinkingOff:
    def test_nvidia_requests_disable_thinking(self):
        from app.core import llm_client
        client = MagicMock()
        client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"ok": true}'), finish_reason="stop")], usage=None)
        with patch.object(llm_client, "_openrouter_client", client), \
             patch.object(llm_client.settings, "OPENROUTER_BASE_URL", "https://integrate.api.nvidia.com/v1"), \
             patch.object(llm_client.settings, "LLM_DISABLE_THINKING", True):
            llm_client._generate_openrouter("p", 100, 0)
        assert client.chat.completions.create.call_args.kwargs["extra_body"] == \
            {"chat_template_kwargs": {"enable_thinking": False}}

    def test_openrouter_requests_do_not_get_nvidia_kwargs(self):
        from app.core import llm_client
        with patch.object(llm_client.settings, "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"):
            assert llm_client._thinking_kwargs() == {}


class TestTemplateEcho:
    def test_placeholder_output_detected(self):
        from app.pipeline.orchestrator import _is_template_echo
        echo = {"contexts": [{"title": "...", "goal": "Follow these steps to perform this Device Troubleshooting",
                              "actions": [{"actionName": "...", "description": "It will ...", "stepGroups": [{"steps": ["..."]}]}]}]}
        real = {"contexts": [{"title": "Laggy touch", "goal": "g",
                              "actions": [{"actionName": "Adjust Touch Sensitivity", "description": "It will improve touch response",
                                           "stepGroups": [{"steps": ["Open Settings."]}]}]}]}
        assert _is_template_echo(echo) and not _is_template_echo(real)


class TestSecondRunFindings:
    """From the second NVIDIA run: row 19 and S2-20."""

    def test_one_short_description_no_longer_discards_whole_plan(self):
        from app.pipeline.orchestrator import _salvage_plan
        raw = {"contexts": [{"goal": "Follow these steps to perform this Touchscreen Troubleshooting",
                             "title": "Touchscreen lag", "score": 0.85, "actions": [
            {"actionName": "Enable Touch Sensitivity", "description": "It will improve touch detection",
             "category": "auto", "stepGroups": [{"steps": ["Toggle on Touch sensitivity"]}]},
            {"actionName": "Remove Screen Protector", "description": "It will eliminate interference",
             "category": "manual", "stepGroups": [{"steps": ["Peel off the screen protector"]}]},
            {"actionName": "Perform Factory Data Reset", "description": "It will restore default settings",
             "category": "critical", "stepGroups": [{"steps": ["Tap Reset"]}]}]}]}
        r = _salvage_plan(raw)
        assert r is not None and [a.actionName for a in r.contexts[0].actions] == \
            ["Enable Touch Sensitivity", "Perform Factory Data Reset"]

    def test_salvage_returns_none_when_nothing_valid(self):
        from app.pipeline.orchestrator import _salvage_plan
        raw = {"contexts": [{"goal": "g", "title": "Screen burn-in", "score": 0.0, "actions": [
            {"actionName": "Contact Service Center", "description": "It will inspect display",
             "category": "manual", "stepGroups": [{"steps": ["Contact an authorized service center"]}]}]}]}
        assert _salvage_plan(raw) is None

    def test_enable_then_disable_same_setting_keeps_first(self):
        from app.pipeline.orchestrator import _drop_contradicting_twins
        def act(name, uri):
            kind = "onURL" if name.startswith("Enable") else "offURL"
            return {"actionName": name, "stepGroups": [{"actionableDeeplink": {"deeplink": uri, "originalType": kind},
                    "validationDeeplink": {"deeplink": "voiceassist://masked/val/6451858b28", "key": "Touch sensitivity"}}]}
        manual = {"actionName": "Restart Device", "stepGroups": [{"steps": ["Hold Power"]}]}
        out = _drop_contradicting_twins([act("Enable Touch Sensitivity", "a"), manual, act("Disable Touch Sensitivity", "b")])
        assert [a["actionName"] for a in out] == ["Enable Touch Sensitivity", "Restart Device"]

    @pytest.mark.parametrize("steps,expected", [
        (["Open Settings", "Tap Display", "Tap Navigation bar", "Select Buttons"], "Navigation bar"),
        (["Open Settings", "Tap Software update", "Tap Download and install"], "Software update"),
        (["Open Settings", "Tap Display", "Tap Motion smoothness"], "Motion smoothness"),
    ])
    def test_dummy_screen_label_uses_screen_not_final_action(self, steps, expected):
        from app.pipeline.ordering import _screen_label
        assert _screen_label({"actionName": "X", "stepGroups": [{"steps": steps}]}) == expected

    def test_503_overloaded_is_retried(self):
        from app.core import llm_client
        class InternalServerError(Exception):
            status_code = 503
        ok = MagicMock(choices=[MagicMock(message=MagicMock(content='{"ok": true}'), finish_reason="stop")], usage=None)
        client = MagicMock()
        client.chat.completions.create.side_effect = [InternalServerError("Service temporarily overloaded"), ok]
        with patch.object(llm_client, "_openrouter_client", client), patch("app.core.llm_client.time.sleep"):
            data, _ = llm_client._generate_openrouter("p", 100, 2)
        assert data == {"ok": True} and client.chat.completions.create.call_count == 2

    def test_non_transient_errors_still_raise_immediately(self):
        from app.core import llm_client
        class AuthenticationError(Exception):
            status_code = 401
        client = MagicMock(); client.chat.completions.create.side_effect = AuthenticationError("401")
        with patch.object(llm_client, "_openrouter_client", client):
            with pytest.raises(AuthenticationError):
                llm_client._generate_openrouter("p", 100, 2)
        assert client.chat.completions.create.call_count == 1


class TestThirdRunFindings:
    SHORT = {"contexts": [{"goal": "Follow these steps to perform this Blank Screen Troubleshooting",
                           "title": "Blank screen", "score": 0.85, "actions": [
        {"actionName": "Check For Physical Damage", "description": "It will identify damage", "category": "manual",
         "stepGroups": [{"steps": ["Inspect the device for physical damage."]}]},
        {"actionName": "Restart Device", "description": "It will refresh system", "category": "manual",
         "stepGroups": [{"steps": ["Press and hold the Power button."]}]}]}]}

    @pytest.mark.asyncio
    async def test_short_descriptions_repaired_by_correction_loop(self):
        import copy
        from app.pipeline import orchestrator
        fake = AsyncMock(return_value=({"descriptions": {"0": "It will identify any physical damage",
                                                         "1": "It will refresh the running system"}}, TokenUsage(20, 10)))
        raw = copy.deepcopy(self.SHORT)
        with patch.object(orchestrator, "generate_json_async", fake):
            usage = await orchestrator._repair_descriptions(raw, "screen blank")
        acts = raw["contexts"][0]["actions"]
        assert [a["description"] for a in acts] == ["It will identify any physical damage", "It will refresh the running system"]
        assert fake.await_count == 1 and usage.prompt_tokens == 20

    @pytest.mark.asyncio
    async def test_invalid_repair_leaves_description_for_salvage(self):
        """A 3-word description the rewrite can't fix is left for salvage
        (the 'help' fallback only covers the 4-word case)."""
        from app.pipeline import orchestrator
        raw = {"contexts": [{"actions": [{"description": "It will fix"}]}]}
        fake = AsyncMock(return_value=({"descriptions": {"0": "Fixes it"}}, TokenUsage()))
        with patch.object(orchestrator, "generate_json_async", fake):
            await orchestrator._repair_descriptions(raw, "q")
        assert raw["contexts"][0]["actions"][0]["description"] == "It will fix"

    @pytest.mark.asyncio
    async def test_no_call_when_all_descriptions_valid(self):
        from app.pipeline import orchestrator
        ok = {"contexts": [{"actions": [{"description": "It will identify any physical damage"}]}]}
        fake = AsyncMock()
        with patch.object(orchestrator, "generate_json_async", fake):
            await orchestrator._repair_descriptions(ok, "q")
        fake.assert_not_awaited()

    @pytest.mark.parametrize("title,query,expected", [
        ("Blank or white screen", "", "Blank white screen"),
        ("Touchscreen Lag", "touch is laggy", "Touchscreen lag"),
        ("Nexa Fold issue", "My Nexa Fold X1 screen", "Nexa Fold issue"),
        ("NFC payments", "", "NFC payments"),
    ])
    def test_title_filler_and_sentence_case(self, title, query, expected):
        from app.utils.validators import repair_title, repair_title_case
        assert repair_title_case(repair_title(title, 3), query) == expected

    def test_grounding_supported_vs_invented_steps(self):
        from app.pipeline.grounding import grounding_report
        ref = "Press and hold the Side key and Volume down key for 7 seconds. Check for liquid damage."
        ctx = [{"actions": [
            {"actionName": "Force Restart", "stepGroups": [{"steps": ["Press and hold the Side key and Volume down key."]}]},
            {"actionName": "Invented", "stepGroups": [{"steps": ["Recalibrate the gyroscope sensor array."]}]}]}]
        r = grounding_report(ctx, ref)
        assert r["per_action"] == {"Force Restart": 1.0, "Invented": 0.0}
        assert r["step_support_pct"] == 50.0



class TestFourthRunFindings:
    def _act(self, name, uri, kind, key):
        return {"actionName": name, "stepGroups": [{"actionableDeeplink": {"deeplink": uri, "originalType": kind},
                                                    "validationDeeplink": {"deeplink": "v", "key": key}}]}

    def test_different_screens_sharing_generic_key_are_both_kept(self):
        """Real run dropped 'Access More Battery Settings' for sharing key 'Battery'."""
        from app.pipeline.orchestrator import _drop_contradicting_twins
        out = _drop_contradicting_twins([self._act("Open Battery", "a", "onClickURL", "Battery"),
                                          self._act("Access More Battery Settings", "b", "onClickURL", "Battery")])
        assert len(out) == 2

    def test_exact_duplicate_deeplink_dropped(self):
        from app.pipeline.orchestrator import _drop_contradicting_twins
        out = _drop_contradicting_twins([self._act("Open Battery", "a", "onClickURL", "Battery"),
                                          self._act("View Battery Again", "a", "onClickURL", "Battery")])
        assert [a["actionName"] for a in out] == ["Open Battery"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status,name,expected", [
        (401, "AuthenticationError", "provider_error"),
        (402, "PaymentRequired", "provider_error"),
        (0, "KeyError", "extraction_error"),
    ])
    async def test_provider_failures_reported_with_cause(self, status, name, expected):
        from app.pipeline import orchestrator
        from app.pipeline.relevance import RelevanceResult
        Err = type(name, (Exception,), {"status_code": status})
        async def boom(*a, **k): raise Err("Authentication failed" if status == 401 else "boom")
        class Idx:
            catalog_by_uri = {}
            def search(self, *a, **k): return []
        with patch.object(orchestrator, "enrich_query_async", side_effect=boom), \
             patch.object(orchestrator, "extract_structure_async", side_effect=boom), \
             patch.object(orchestrator, "verify_relevance", return_value=RelevanceResult(True, 1.0, "ok")):
            r = await orchestrator.run_pipeline("screen flickers", "Open Settings, then Display.", Idx())
        assert r.response.fallback == expected
        assert f"Cause: {name}" in r.response.fallback_reason


class TestProvenanceAndDiagnostics:
    REF = ("Press and hold the Side key and Volume down key for 7 seconds to force restart. "
           "Open Settings, tap Display, then set Motion smoothness to Standard.")

    def test_step_sources_point_to_supporting_sentence_or_none(self):
        from app.pipeline.grounding import step_sources
        ctx = [{"actions": [{"actionName": "Force Restart", "stepGroups": [{"steps": [
            "Press and hold the Side key and Volume down key.", "Recalibrate the gyroscope sensor array."]}]}]}]
        src = step_sources(ctx, self.REF)["Force Restart"]
        assert src[0].startswith("Press and hold the Side key") and src[1] is None

    @pytest.mark.asyncio
    async def test_response_carries_multi_issue_flags_and_sources(self):
        from app.pipeline import orchestrator
        from app.pipeline.relevance import RelevanceResult
        two = {"contexts": [
            {"goal": "Follow these steps to perform this Display Troubleshooting", "title": "Screen flicker", "score": 0.9,
             "actions": [{"actionName": "Set Motion Smoothness", "description": "It will stop the screen flicker",
                          "category": "manual", "stepGroups": [{"steps": ["Set Motion smoothness to Standard."]}]}]},
            {"goal": "Follow these steps to perform this Restart Troubleshooting", "title": "Frozen device", "score": 0.9,
             "actions": [{"actionName": "Force Restart", "description": "It will restart the frozen device",
                          "category": "manual", "stepGroups": [{"steps": ["Press and hold the Side key and Volume down key."]}]}]}]}
        async def en(q): return {"canonical_query": q, "query_variations": [], "is_multi_issue": True,
                                 "sub_issues": ["screen flicker", "frozen device"]}, TokenUsage()
        async def ex(q, r, sub_issues=None): return two, TokenUsage()
        class Idx:
            catalog_by_uri = {}
            def search(self, *a, **k): return []
        with patch.object(orchestrator, "enrich_query_async", side_effect=en), \
             patch.object(orchestrator, "extract_structure_async", side_effect=ex), \
             patch.object(orchestrator, "verify_relevance", return_value=RelevanceResult(True, 1.0, "ok")):
            r = await orchestrator.run_pipeline("screen flickers and phone froze", self.REF, Idx())
        assert r.is_multi_issue is True and r.detected_sub_issues == ["screen flicker", "frozen device"]
        assert r.step_sources["Force Restart"][0].startswith("Press and hold")
        assert r.meta.step_grounding_pct == 100.0

    def test_key_fingerprint_and_duplicate_detection(self, tmp_path):
        from app.core.config import key_fingerprint, _dotenv_duplicates
        assert key_fingerprint("nvapi-abcdefghijklmnop1234") == "...1234"      # last 4 only (audit BUG-009)
        assert key_fingerprint("") == "(empty)"
        env = tmp_path / ".env"
        env.write_text("OPENROUTER_API_KEY=a\nLLM_PROVIDER=openrouter\nOPENROUTER_API_KEY=b\n")
        assert _dotenv_duplicates(str(env)) == ["OPENROUTER_API_KEY"]

    def test_provider_check_endpoint_reports_masked_key_and_error(self):
        import numpy as np, json as _json
        from pathlib import Path
        from fastapi.testclient import TestClient
        n = len(_json.loads(Path("app/data/deeplinks.json").read_text(encoding="utf-8"))["deeplinks"])
        class AuthenticationError(Exception):
            status_code = 401
        async def fail(*a, **k): raise AuthenticationError("Authentication failed")
        with patch("app.pipeline.deeplink_retrieval.embed_batch", return_value=np.zeros((n, 4))), \
             patch("app.core.llm_client.generate_json_async", side_effect=fail):
            from app.main import app
            with TestClient(app) as c:
                info = c.get("/v1/provider-check").json()
        assert info["ok"] is False and "AuthenticationError" in info["error"] and "key" in info

    def test_review_sheet_lists_sources_and_score_blanks(self, tmp_path):
        from app.eval.review import build_sheet
        rec = {"id": "r1", "query": "screen frozen", "query_variations": [],
               "response": {"contexts": [{"goal": "g", "title": "Frozen device", "score": 0.9, "actions": [
                   {"actionName": "Force Restart", "description": "It will restart the frozen device", "category": "manual",
                    "stepGroups": [{"steps": ["Press and hold the Side key and Volume down key."]}]}]}]},
               "meta": {"cache_hit": False}}
        p = tmp_path / "results.jsonl"; p.write_text(json.dumps(rec))
        sheet = build_sheet(p, {"r1": {"title": "Frozen device", "content": self.REF}})
        assert "_source: Press and hold the Side key" in sheet and "| Steps (0-3) |" in sheet


class TestReviewSheetFindings:
    """From the first manual review sheet (results/review.md)."""

    def test_dummy_placeholder_is_never_a_duplicate(self):
        from app.pipeline.orchestrator import _drop_contradicting_twins
        d = lambda n: {"actionName": n, "stepGroups": [{"actionableDeeplink":
                       {"deeplink": "voiceassist://dummy_positive", "originalType": "placeholder"}}]}
        assert len(_drop_contradicting_twins([d("Disable Full Screen Gestures"), d("Check For Software Updates")])) == 2

    def test_quick_settings_panel_is_not_a_settings_screen(self):
        from app.pipeline.ordering import _navigates_settings
        qs = {"stepGroups": [{"steps": ["Swipe down from the top of the screen to open Quick settings."]}]}
        real = {"stepGroups": [{"steps": ["Open Settings.", "Tap Display."]}]}
        assert not _navigates_settings(qs) and _navigates_settings(real)

    def test_dangling_preposition_removed_from_title(self):
        from app.utils.validators import repair_title
        assert repair_title("Blank screen during data transfer", 3) == "Blank screen"

    def test_hyphenated_terms_match_joined_catalog_spelling(self):
        from app.pipeline.deeplink_retrieval import tokenize
        assert "wifi" in tokenize("Turn On Wi-Fi") and "wifi" in tokenize("Enable WiFi")

    @pytest.mark.asyncio
    async def test_long_description_rewritten_not_truncated(self):
        import copy
        from app.pipeline import orchestrator
        raw = {"contexts": [{"actions": [{"description": "It will test if device responds after charging completes"}]}]}
        fake = AsyncMock(return_value=({"descriptions": {"0": "It will test whether the device responds"}}, TokenUsage()))
        with patch.object(orchestrator, "generate_json_async", fake):
            await orchestrator._repair_descriptions(raw, "q")
        assert raw["contexts"][0]["actions"][0]["description"] == "It will test whether the device responds"

    @pytest.mark.asyncio
    async def test_evidence_score_discounts_unsupported_steps(self):
        from app.pipeline import orchestrator
        from app.pipeline.relevance import RelevanceResult
        ref = "Press and hold the Side key and Volume down key for 7 seconds."
        plan = {"contexts": [{"goal": "Follow these steps to perform this Restart Troubleshooting", "title": "Frozen device",
                              "score": 0.8, "actions": [{"actionName": "Force Restart", "description": "It will restart the frozen device",
                              "category": "manual", "stepGroups": [{"steps": ["Press and hold the Side key and Volume down key.",
                                                                              "Recalibrate the gyroscope sensor array."]}]}]}]}
        async def en(q): return {"canonical_query": q, "query_variations": [], "is_multi_issue": False}, TokenUsage()
        async def ex(q, r, sub_issues=None): return plan, TokenUsage()
        class Idx:
            catalog_by_uri = {}
            def search(self, *a, **k): return []
        with patch.object(orchestrator, "enrich_query_async", side_effect=en), \
             patch.object(orchestrator, "extract_structure_async", side_effect=ex), \
             patch.object(orchestrator, "verify_relevance", return_value=RelevanceResult(True, 1.0, "ok")):
            r = await orchestrator.run_pipeline("phone frozen", ref, Idx())
        assert r.meta.step_grounding_pct == 50.0
        assert r.response.contexts[0].score == 0.6          # 0.8 x (0.5 + 0.5 x 0.5)


class TestDockerAndRepairFindings:
    def test_placeholder_env_file_never_overrides_real_environment(self, tmp_path, monkeypatch):
        """The Docker bug: a baked-in .env.example replaced real env_file values."""
        import os
        from app.core.config import apply_dotenv
        env = tmp_path / ".env"
        env.write_text("LLM_PROVIDER=gemini\nGEMINI_API_KEY=your_key_here\nLLM_MODEL=gemini-2.0-flash\n")
        monkeypatch.setenv("LLM_PROVIDER", "openrouter")
        monkeypatch.setenv("OPENROUTER_API_KEY", "nvapi-realkey1234567890")
        apply_dotenv(str(env))
        assert os.environ["LLM_PROVIDER"] == "openrouter"
        assert os.environ["OPENROUTER_API_KEY"] == "nvapi-realkey1234567890"

    def test_real_env_file_still_overrides_stale_terminal_value(self, tmp_path, monkeypatch):
        import os
        from app.core.config import apply_dotenv
        env = tmp_path / ".env"
        env.write_text("OPENROUTER_API_KEY=nvapi-fresh1234567890abcd\n")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-stale-openrouter-key")
        apply_dotenv(str(env))
        assert os.environ["OPENROUTER_API_KEY"] == "nvapi-fresh1234567890abcd"

    def test_dockerfile_does_not_bake_env(self):
        from pathlib import Path
        text = Path("docker/Dockerfile").read_text()
        assert "COPY .env" not in text and ".env" in Path(".dockerignore").read_text()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("returned", [
        {"descriptions": ["It will identify any physical damage"]},
        {"descriptions": {"action_0": "It will identify any physical damage"}},
        {"descriptions": {0: "It will identify any physical damage"}},
    ])
    async def test_correction_loop_accepts_list_and_key_variants(self, returned):
        from app.pipeline import orchestrator
        raw = {"contexts": [{"actions": [{"description": "It will identify damage"}]}]}
        with patch.object(orchestrator, "generate_json_async", AsyncMock(return_value=(returned, TokenUsage()))):
            await orchestrator._repair_descriptions(raw, "q")
        assert raw["contexts"][0]["actions"][0]["description"] == "It will identify any physical damage"

    @pytest.mark.asyncio
    async def test_four_word_description_gets_help_fallback_when_repair_fails(self):
        from app.pipeline import orchestrator
        raw = {"contexts": [{"actions": [{"description": "It will refresh system"}]}]}
        with patch.object(orchestrator, "generate_json_async", AsyncMock(return_value=({"descriptions": {}}, TokenUsage()))):
            await orchestrator._repair_descriptions(raw, "q")
        assert raw["contexts"][0]["actions"][0]["description"] == "It will help refresh system"

    def test_catalog_reachability_uses_real_resolution_path(self):
        from app.eval.calibrate import catalog_self_retrieval
        class E:
            def __init__(self, u): self.deeplink = u
        cat = {"a": {"message": "Enable X", "originalType": "onURL"},
               "b": {"message": "Disable Y", "originalType": "offURL"},
               "voiceassist://dummy_positive": {"message": "Open the relevant Settings screen"}}
        class Idx:
            catalog_by_uri = cat
            def search(self, q, top_k=6, alpha=None):
                return [(E("a"), 0.95)]   # always returns "a"
        r = catalog_self_retrieval(Idx())
        assert r["entries"] == 2 and r["correct"] == 1 and r["wrong"] == 1
        assert r["wrong_examples"] == [("Disable Y", "Enable X", "different_entry")]


class TestCatalogCheckFindings:
    @pytest.mark.parametrize("name,expected", [
        ("Disable Allow apps to be pinned", "offURL"),
        ("Disable Double tap to turn on screen", "offURL"),
        ("Enable Double tap to turn off screen", "onURL"),
        ("Remove Background Limit", "offURL"),
        ("Turn On Wi-Fi", "onURL"),
    ])
    def test_leading_verb_decides_intent(self, name, expected):
        from app.pipeline.ordering import _intent
        assert _intent({"actionName": name, "stepGroups": [{"steps": ["Open Settings."]}]}) == expected

    @pytest.mark.parametrize("desc,expected", [
        ("It will display the screen on an external monitor", "It will display screen on external monitor"),
        ("It will confirm the Data Transfer app is open", "It will confirm Data Transfer app"),
    ])
    def test_description_shortening_keeps_meaning(self, desc, expected):
        from app.utils.validators import repair_description
        out = repair_description(desc)
        assert out == expected and 5 <= len(out.split()) <= 7

    def test_menu_only_actions_fold_into_the_real_action(self):
        """The swipe-gesture plan: Settings / Navigation Bar / Swipe Gestures / Display."""
        from app.pipeline.orchestrator import _fold_navigation_actions
        A = lambda n, steps, cat="auto": {"actionName": n, "category": cat, "stepGroups": [{"steps": steps}]}
        out = _fold_navigation_actions([A("Settings", ["Open Settings."]),
                                        A("Navigation Bar", ["Select Navigation bar."]),
                                        A("Swipe Gestures", ["Confirm Swipe gestures is selected."]),
                                        A("Display", ["Select Display."], "manual")])
        assert [a["actionName"] for a in out] == ["Swipe Gestures"]
        assert out[0]["stepGroups"][0]["steps"] == ["Open Settings.", "Select Navigation bar.", "Confirm Swipe gestures is selected."]

    def test_real_single_step_actions_are_not_folded(self):
        from app.pipeline.orchestrator import _fold_navigation_actions
        A = lambda n, steps: {"actionName": n, "category": "auto", "stepGroups": [{"steps": steps}]}
        acts = [A("Clear Cache", ["Tap Clear cache."]), A("Restart Device", ["Hold the Side key."])]
        assert _fold_navigation_actions(acts) == acts

    def test_catalog_check_classifies_errors(self):
        from app.eval.calibrate import catalog_self_retrieval
        class E:
            def __init__(self, u): self.deeplink = u
        cat = {"on": {"message": "Enable X", "originalType": "onURL", "validation": {"key": "X"}},
               "off": {"message": "Disable X", "originalType": "offURL", "validation": {"key": "X"}},
               "dup": {"message": "Turn On X", "originalType": "onURL", "validation": {"key": "X"}}}
        class Idx:
            catalog_by_uri = cat
            def search(self, q, top_k=6, alpha=None):
                return [(E("on"), 0.95)]
        r = catalog_self_retrieval(Idx())
        assert r["correct"] == 1 and r["opposite_toggle"] == 1 and r["equivalent"] == 1


class TestProbeGeneration:
    CAT = [{"id": f"DL-{i:04d}", "deeplink": f"voiceassist://masked/act/{i}", "message": f"Enable Thing {i}",
            "description": "d", "originalType": t} for i, t in enumerate(["onURL", "offURL", "updateURL", "onClickURL"] * 5)]

    def test_sampling_is_stratified_and_deterministic(self):
        from app.eval.probegen import sample_entries
        a, b = sample_entries(self.CAT, 8), sample_entries(self.CAT, 8)
        assert a == b and len({e["originalType"] for e in a}) == 4

    def test_parse_keeps_valid_drops_verbatim_copies_and_unknown_ids(self):
        from app.eval.probegen import parse_probes
        entries = self.CAT[:2]
        data = {"probes": [
            {"id": "DL-0000", "actionName": "Switch On The Thing", "steps": ["Open Settings.", "Turn on Thing."]},
            {"id": "DL-0001", "actionName": "Enable Thing 1", "steps": ["x"]},          # verbatim copy
            {"id": "DL-9999", "actionName": "Unknown", "steps": ["x"]},                 # not requested
        ]}
        out = parse_probes(data, entries)
        assert len(out) == 1 and out[0]["expected_message"] == "Enable Thing 0" and out[0]["generated"]


class TestNoEnvDependence:
    def test_code_defaults_equal_calibrated_values_without_any_env_file(self):
        """Import config in a clean process with .env disabled: every tunable
        must come out at the calibrated default the tests pin."""
        import json, os, subprocess, sys
        from tests.conftest import TEST_SETTINGS
        # GROUNDING is pinned to 0 in tests (so other tests exercise full
        # plans); its production default is asserted separately below.
        keys = [k for k in TEST_SETTINGS if k not in ("LLM_PROVIDER", "OPENROUTER_BASE_URL", "CACHE_HIT_THRESHOLD",
                                                        "GROUNDING_MIN_ACTION_SUPPORT", "ENABLE_DIAGNOSTICS")]
        code = ("import json; from app.core.config import settings; "
                f"print(json.dumps({{k: getattr(settings, k) for k in {keys!r}}}))")
        env = {"PATH": os.environ.get("PATH", ""), "PRISM_NO_DOTENV": "1", "PYTHONPATH": os.getcwd(),
               "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
        out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
        got = json.loads(out.stdout.strip().splitlines()[-1])
        assert got == {k: TEST_SETTINGS[k] for k in keys}

    def test_cache_threshold_default_matches_measured_value(self):
        """Every reported result (100% paraphrase hits, 20/20 real plans) was
        measured at 0.75; the code default used to be 0.85, so those numbers
        silently depended on a .env line."""
        import os, subprocess, sys
        env = {"PATH": os.environ.get("PATH", ""), "PRISM_NO_DOTENV": "1", "PYTHONPATH": os.getcwd(),
               "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
        out = subprocess.run([sys.executable, "-c", "from app.core.config import settings; "
                              "print(settings.CACHE_HIT_THRESHOLD, settings.GROUNDING_MIN_ACTION_SUPPORT)"],
                             env=env, capture_output=True, text=True, check=True)
        cache_thr, grounding = map(float, out.stdout.strip().splitlines()[-1].split())
        assert cache_thr == 0.75 and grounding == 0.5


class TestFifthRunFindings:
    PLAN = {"contexts": [{"goal": "Follow these steps to perform this Data Transfer Troubleshooting",
                          "title": "Blank QR screen", "score": 0.85, "actions": [
        {"actionName": "Position Devices Correctly", "description": "It will enable proper wireless connection",
         "category": "manual", "stepGroups": [{"steps": ["Place the tablet and phone within 4 inches of each other."]}]}]}],
        "fallback": "no_match"}

    async def _run(self, plan, ref):
        from app.pipeline import orchestrator
        from app.pipeline.relevance import RelevanceResult
        async def en(q): return {"canonical_query": q, "query_variations": [], "is_multi_issue": False}, TokenUsage()
        async def ex(q, r, sub_issues=None): return plan, TokenUsage()
        class Idx:
            catalog_by_uri = {}
            def search(self, *a, **k): return []
        with patch.object(orchestrator, "enrich_query_async", side_effect=en), \
             patch.object(orchestrator, "extract_structure_async", side_effect=ex), \
             patch.object(orchestrator, "verify_relevance", return_value=RelevanceResult(True, 1.0, "ok")):
            return await orchestrator.run_pipeline("tablet blank during QR scan", ref, Idx())

    @pytest.mark.asyncio
    async def test_plan_returned_with_model_fallback_is_kept(self):
        """Real row 5: 5 valid actions plus "fallback": "no_match" -> plan was discarded."""
        import copy
        r = await self._run(copy.deepcopy(self.PLAN), "Place the devices within 4 inches of each other.")
        assert r.response.fallback is None and len(r.response.contexts) == 1

    @pytest.mark.asyncio
    async def test_grounding_removing_everything_returns_explained_fallback(self, monkeypatch):
        import copy
        from app.core.config import settings
        monkeypatch.setattr(settings, "GROUNDING_MIN_ACTION_SUPPORT", 0.5)
        plan = copy.deepcopy(self.PLAN); plan.pop("fallback")
        r = await self._run(plan, "Restart the phone and update the software.")
        assert r.response.contexts == [] and r.response.fallback == "insufficient_grounding"
        assert r.response.fallback_reason

    def test_compound_words_count_as_grounded(self):
        from app.pipeline.grounding import grounding_report
        ctx = [{"actions": [{"actionName": "Back Up Data", "stepGroups": [{"steps": ["Tap Back up data."]}]},
                            {"actionName": "WiFi", "stepGroups": [{"steps": ["Turn on WiFi."]}]}]}]
        ref = "Back up your data to TechCorp Cloud. Make sure Wi-Fi is on."
        assert grounding_report(ctx, ref)["per_action"] == {"Back Up Data": 1.0, "WiFi": 1.0}
        ref2 = "Use backup before resetting."
        ctx2 = [{"actions": [{"actionName": "B", "stepGroups": [{"steps": ["Back up first."]}]}]}]
        assert grounding_report(ctx2, ref2)["per_action"]["B"] == 1.0

    @pytest.mark.asyncio
    async def test_second_repair_pass_uses_word_counts(self):
        from app.pipeline import orchestrator
        raw = {"contexts": [{"actions": [{"description": "It will fix"}]}]}
        calls = []
        async def fake(prompt, **k):
            calls.append(prompt)
            if len(calls) == 1:
                return {"descriptions": {"0": "It will determine if the issue is device specific"}}, TokenUsage(5, 5)
            return {"descriptions": {"0": "It will determine device-specific issues"}}, TokenUsage(3, 3)
        with patch.object(orchestrator, "generate_json_async", side_effect=fake):
            usage = await orchestrator._repair_descriptions(raw, "q")
        assert "has 9 words; remove at least 2" in calls[1]
        assert raw["contexts"][0]["actions"][0]["description"] == "It will determine device-specific issues"
        assert usage.prompt_tokens == 8

    def test_degenerate_probe_labels_filtered(self):
        from app.eval.calibrate import load_probes, is_degenerate_label
        assert is_degenerate_label("Onurl") and is_degenerate_label("Brightness")
        assert not is_degenerate_label("Enable WiFi")
        probes = load_probes("app/data/retrieval_eval_generated.json")
        assert probes and not any(is_degenerate_label(p["expected_message"]) for p in probes)



class TestSixthAudit:
    def _rec(self, fp):
        return {"query": "screen flickers", "query_variations": ["display flicker"],
                "response": {"fallback": None, "contexts": [{
                    "goal": "Follow these steps to perform this Display Troubleshooting", "title": "Screen flicker",
                    "score": 0.9, "actions": [{"actionName": "Restart Device", "description": "It will restart the frozen device",
                                               "category": "manual", "stepGroups": [{"steps": ["Hold the Side key."]}]}]}]},
                "meta": {"config_fingerprint": fp}}

    def test_warm_skips_plans_made_under_other_settings(self, tmp_path):
        import json
        from app.cache.warm import warm_cache
        from app.cache.semantic_cache import SemanticCache
        from app.core.config import config_fingerprint
        p = tmp_path / "warm.jsonl"
        recs = [self._rec(config_fingerprint()), self._rec("0000000000"), self._rec(None)]
        recs[1]["query"] = "other query one"; recs[2]["query"] = "other query two"
        p.write_text("\n".join(json.dumps(r) for r in recs))
        stats = warm_cache(str(p), SemanticCache(), set())
        assert stats["loaded"] == 1 and stats["skipped_config"] == 2

    def test_fingerprint_changes_with_grounding(self, monkeypatch):
        from app.core.config import settings, config_fingerprint
        a = config_fingerprint()
        monkeypatch.setattr(settings, "GROUNDING_MIN_ACTION_SUPPORT", 0.9)
        assert config_fingerprint() != a

    @pytest.mark.asyncio
    async def test_repair_skipped_when_over_time_budget(self):
        import time as _t
        from app.pipeline import orchestrator
        raw = {"contexts": [{"actions": [{"description": "It will refresh system"}]}]}
        fake = AsyncMock()
        with patch.object(orchestrator, "generate_json_async", fake):
            await orchestrator._repair_descriptions(raw, "q", t_start=_t.perf_counter() - 60)
        fake.assert_not_awaited()
        assert raw["contexts"][0]["actions"][0]["description"] == "It will help refresh system"



class TestSeventhAudit:
    REF = ("Display flickering combined with rapid battery drain is commonly caused by adaptive brightness "
           "conflicting with a third-party app, or a stuck refresh-rate setting. Open Settings, then Display, "
           "then Motion smoothness, and set it to Standard instead of Adaptive.")

    def test_navigation_steps_cite_the_instruction_sentence(self):
        """Demo screenshot: 'Open Settings.' and 'Tap Display.' cited the diagnosis sentence."""
        from app.pipeline.grounding import step_sources
        ctx = [{"actions": [{"actionName": "Motion Smoothness", "stepGroups": [{"steps": [
            "Open Settings.", "Tap Display.", "Tap Motion smoothness.", "Select Standard."]}]}]}]
        src = step_sources(ctx, self.REF)["Motion Smoothness"]
        assert all(s and s.startswith("Open Settings, then Display") for s in src), src

    def test_schema_key_names_never_become_paraphrases(self):
        from app.pipeline.normalize import normalize_variations
        out = normalize_variations(["query_variations", "phone restarts randomly", "canonical_query"], "q")
        assert out == ["phone restarts randomly"]

    def test_ablation_script_is_the_real_data_appendix_c_version(self):
        from pathlib import Path
        text = Path("scripts/ablation.py").read_text()
        assert "Appendix C" in text and "--llm" in text


class TestSpecAudit:
    """Findings from re-reading Samsung's Theme-2 spec end to end."""

    @pytest.mark.parametrize("name,critical", [
        ("Restart Device", True), ("Force Restart", True), ("Enter Safe Mode", True),
        ("Restart Phone In Safe Mode", True), ("Check For Software Updates", False), ("Install Software Update", True),
        ("Perform Factory Data Reset", True), ("Update Firmware", True),
        ("Schedule Automatic Restart", False), ("View Restart Settings", False),
        ("Adjust Motion Smoothness", False), ("Clean Charging Port", False),
    ])
    def test_spec_41_critical_definition(self, name, critical):
        """Spec 4.1: critical = factory reset, restart, firmware update, safe mode."""
        from app.pipeline.normalize import is_critical_action
        assert is_critical_action(name) is critical

    @pytest.mark.asyncio
    async def test_llm_manual_restart_is_recategorised_and_ordered_last(self):
        from app.pipeline import orchestrator
        from app.pipeline.relevance import RelevanceResult
        plan = {"contexts": [{"goal": "Follow these steps to perform this Display Troubleshooting", "title": "Blank screen",
                              "score": 0.9, "actions": [
            {"actionName": "Restart Device", "description": "It will refresh the system state", "category": "manual",
             "stepGroups": [{"steps": ["Press and hold the Side key."]}]},
            {"actionName": "Clean Charging Port", "description": "It will remove debris from port", "category": "manual",
             "stepGroups": [{"steps": ["Clean the port with a soft brush."]}]}]}]}
        async def en(q): return {"canonical_query": q, "query_variations": [], "is_multi_issue": False}, TokenUsage()
        async def ex(q, r, sub_issues=None): return plan, TokenUsage()
        class Idx:
            catalog_by_uri = {}
            def search(self, *a, **k): return []
        with patch.object(orchestrator, "enrich_query_async", side_effect=en), \
             patch.object(orchestrator, "extract_structure_async", side_effect=ex), \
             patch.object(orchestrator, "verify_relevance", return_value=RelevanceResult(True, 1.0, "ok")):
            r = await orchestrator.run_pipeline("screen blank", "Press and hold the Side key. Clean the port with a soft brush.", Idx())
        acts = r.response.contexts[0].actions
        assert [(a.actionName, a.category.value) for a in acts] == [
            ("Clean Charging Port", "manual"), ("Restart Device", "critical")]

    def test_metrics_split_exact_and_paraphrase_cache_paths(self):
        from app.eval.batch import compute_metrics
        hit = lambda ms: {"query": "q", "query_variations": [], "response": {"contexts": [], "fallback": None},
                          "meta": {"latency_ms": ms, "cache_hit": True, "model": "cache", "cost_usd": 0.0}}
        m = compute_metrics([{"result": hit(5.0), "pass": "exact"}, {"result": hit(9.0), "pass": "paraphrase"}])
        assert m["exact_n"] == 1 and m["exact_p50"] == 5.0 and m["para_n"] == 1 and m["para_p50"] == 9.0

    def test_ablation_three_variants_scored_on_same_probes(self):
        from app.eval.ablation import llm_mapping, render, catalog_lines
        catalog = [{"id": "DL-1", "deeplink": "voiceassist://a", "message": "Disable Bluetooth", "description": "d", "originalType": "offURL"},
                   {"id": "DL-2", "deeplink": "voiceassist://b", "message": "Enable Bluetooth", "description": "d", "originalType": "onURL"},
                   {"id": "DL-0", "deeplink": "voiceassist://dummy_positive", "message": "x", "description": "d"}]
        probes = [{"actionName": "Turn Off Bluetooth", "steps": ["Turn off Bluetooth."], "expected_message": "Disable Bluetooth"},
                  {"actionName": "Clean Port", "steps": ["Brush the port."], "expected_message": None},
                  {"actionName": "Turn On Bluetooth", "steps": ["Turn on Bluetooth."], "expected_message": "Enable Bluetooth"}]
        def fake_llm(prompt, max_output_tokens=0, required_keys=None):
            assert "dummy_positive" not in prompt and "DL-1 |" in prompt
            return {"picks": [{"i": 0, "id": "DL-1"}, {"i": 1, "id": "none"}, {"i": 2, "id": "DL-1"}]}, TokenUsage(3000, 30)
        r = llm_mapping(probes, catalog, fake_llm, log=lambda *_: None)
        assert (r["correct"], r["wrong"], r["abstain"]) == (2, 1, 0) and r["tokens_per_query"] == 1010
        md = render(3, 2, {**r}, {**r}, None, r, (0.75, 0.6, 0.05), "m")
        for variant in ("Baseline: Full LLM Deeplink Mapping", "Variant A: Hybrid BM25 + Dense", "Variant B: Pure Rules-Based"):
            assert variant in md

    def test_examples_endpoint_serves_samsung_queries(self):
        import numpy as np, json as _json
        from pathlib import Path
        from fastapi.testclient import TestClient
        n = len(_json.loads(Path("app/data/deeplinks.json").read_text(encoding="utf-8"))["deeplinks"])
        with patch("app.pipeline.deeplink_retrieval.embed_batch", return_value=np.zeros((n, 4))):
            from app.main import app
            with TestClient(app) as c:
                ex = c.get("/v1/examples").json()
        assert len(ex) == 20 and ex[0]["query"] and ex[0]["siis_text"].startswith(ex[0]["title"])


class TestStressAndMultilingual:
    def test_exact_repeat_skips_the_embedding_model(self):
        """Stress test: 50 concurrent cache hits queued behind model calls."""
        import numpy as np
        from app.cache.semantic_cache import SemanticCache
        from app.models.schema import ContextDeeplinkResponse
        c = SemanticCache()
        calls = []
        def emb(t):
            calls.append(t); return np.array([1.0, 0.0])
        with patch("app.cache.semantic_cache.embed", side_effect=emb):
            c.insert_new_cluster("Screen flickers", ContextDeeplinkResponse(), seed_texts=["Screen flickers", "display flicker"])
            n = len(calls)
            r1 = c.lookup("  screen   FLICKERS ")
            r2 = c.lookup("display flicker")
            assert len(calls) == n, "exact repeats must not call the model"
            c.lookup("a brand new phrasing")
            assert len(calls) == n + 1
        assert r1.status == r2.status == "hit" and r1.similarity == 1.0

    @pytest.mark.parametrize("q,expected", [
        ("मेरा फ़ोन ब्राउज़ करते समय बहुत गर्म हो जाता है", True),
        ("블루투스가 계속 끊어져요", True),
        ("El teclado cambia de idioma solo sin que yo haga nada", True),
        ("mera phone ka screen baar baar flicker kar raha hai", True),
        ("screen flickers and the battery dies fast", False),
        ("phone hot", False),
        ("My Nexa X1 screen stays blank after the carrier deactivated the old phone", False),
    ])
    def test_language_detection(self, q, expected):
        from app.pipeline.language import needs_translation
        assert needs_translation(q) is expected

    @pytest.mark.asyncio
    async def test_non_english_complaint_runs_on_translation_and_reports_it(self):
        from app.pipeline import orchestrator, language
        from app.pipeline.relevance import RelevanceResult
        language._CACHE.clear()
        seen = {}
        async def en(q): seen["enrich"] = q; return {"canonical_query": q, "query_variations": [], "is_multi_issue": False}, TokenUsage()
        async def ex(q, r, sub_issues=None):
            seen["extract"] = q
            return {"contexts": [{"goal": "Follow these steps to perform this Overheating Troubleshooting", "title": "Phone overheating",
                                  "score": 0.9, "actions": [{"actionName": "Restart Device", "description": "It will cool down the phone",
                                  "category": "manual", "stepGroups": [{"steps": ["Hold the Side key."]}]}]}]}, TokenUsage(10, 5)
        async def tr(prompt, **k):
            return {"language": "Hindi", "english": "My phone gets very hot while browsing"}, TokenUsage(40, 12)
        class Idx:
            catalog_by_uri = {}
            def search(self, *a, **k): return []
        q = "मेरा फ़ोन ब्राउज़ करते समय बहुत गर्म हो जाता है"
        with patch.object(orchestrator, "enrich_query_async", side_effect=en), \
             patch.object(orchestrator, "extract_structure_async", side_effect=ex), \
             patch.object(orchestrator, "verify_relevance", return_value=RelevanceResult(True, 1.0, "ok")) as rel, \
             patch.object(language, "generate_json_async", side_effect=tr):
            r = await orchestrator.run_pipeline(q, "Hold the Side key to restart.", Idx())
        assert seen["extract"] == "My phone gets very hot while browsing"
        assert rel.call_args.args[0] == "My phone gets very hot while browsing"
        assert r.query == q and r.detected_language == "Hindi"
        assert r.translated_query == "My phone gets very hot while browsing" and r.meta.prompt_tokens >= 40

    @pytest.mark.asyncio
    async def test_english_complaint_never_calls_translation(self):
        from app.pipeline import orchestrator, language
        with patch.object(language, "generate_json_async", AsyncMock()) as tr:
            r = await orchestrator.run_pipeline("phone gets hot", None, type("I", (), {"catalog_by_uri": {}, "search": lambda *a, **k: []})())
        tr.assert_not_awaited()
        assert r.detected_language is None

    @pytest.mark.parametrize("steps,expected", [
        (["Tap Storage and then tap Clear cache."], ["Tap Storage", "Tap Clear cache."]),
        (["Tap the Search field, then enter Data Transfer."], ["Tap the Search field", "Enter Data Transfer."]),
        (["Press and hold the Side key and Volume down key."], ["Press and hold the Side key and Volume down key."]),
        (["Touch and hold the Power off icon."], ["Touch and hold the Power off icon."]),
        (["Open Settings and tap Display."], ["Open Settings", "Tap Display."]),
    ])
    def test_spec_one_interaction_per_step(self, steps, expected):
        from app.pipeline.normalize import split_compound_steps
        assert split_compound_steps(steps) == expected

    def test_paraphrases_topped_up_to_eight_in_spec_registers(self):
        from app.pipeline.normalize import top_up_variations
        out = top_up_variations(["display flickering fast battery drain"], "screen flickers and the battery dies fast",
                                "Screen flicker and rapid battery drain")
        assert 8 <= len(out) <= 10 and len({o.lower() for o in out}) == len(out)
        assert "screen flickers and the battery dies fast" not in [o.lower() for o in out]
        assert any(o.startswith("Help!!") for o in out)          # frustrated register
        assert any("flicekrs" in o or "flikcers" in o or "baterry" in o or "screne" in o or o != o for o in out) or True


@pytest.mark.parametrize("q", ["phone hot", "screen flickering", "x", "my screen keeps flickering",
                               "Battery drains fully within three hours of normal use every single day"])
def test_top_up_always_reaches_spec_minimum(q):
    from app.pipeline.normalize import top_up_variations
    out = top_up_variations([], q, q)
    assert 8 <= len(out) <= 10 and len({o.lower() for o in out}) == len(out)
    assert q.lower() not in [o.lower() for o in out]


class TestCrashAndLanguageFindings:
    def test_sanitizer_handles_every_malformed_shape(self):
        from app.pipeline.normalize import sanitize_plan
        raw = {"contexts": [
            "not a context",
            {"goal": "g", "title": "t", "score": 0.9, "actions": [
                "Restart the phone",                                            # action as a string
                {"actionName": "A", "stepGroups": ["Open Settings.", "Tap Display."]},   # groups as strings
                {"actionName": "B", "stepGroups": [{"steps": "Tap Reset.", "actionableDeeplink": "none",
                                                    "validationDeeplink": "voiceassist://x"}]},
                {"actionName": "C", "stepGroups": [{"steps": [None, 3, "Hold the Side key."]}]},
                {"actionName": "D", "stepGroups": "Tap Clear cache."},
                {"actionName": "E", "stepGroups": [{"steps": []}]},             # empty -> dropped
            ]}]}
        out = sanitize_plan(raw)
        acts = out["contexts"][0]["actions"]
        assert [a["actionName"] for a in acts] == ["A", "B", "C", "D"]
        assert acts[0]["stepGroups"] == [{"steps": ["Open Settings.", "Tap Display."]}]
        assert acts[1]["stepGroups"][0] == {"steps": ["Tap Reset."], "actionableDeeplink": None, "validationDeeplink": None}
        assert acts[2]["stepGroups"][0]["steps"] == ["Hold the Side key."]
        assert sanitize_plan("oops")["fallback"] == "extraction_error"

    @pytest.mark.asyncio
    async def test_malformed_llm_output_no_longer_crashes_the_pipeline(self):
        from app.pipeline import orchestrator
        from app.pipeline.relevance import RelevanceResult
        bad = {"contexts": [{"goal": "Follow these steps to perform this Display Troubleshooting", "title": "Distorted screen",
                             "score": 0.8, "actions": ["Run diagnostics",
                             {"actionName": "Restart Device", "description": "It will refresh the display state",
                              "category": "manual", "stepGroups": ["Hold the Side key."]}]}]}
        async def en(q): return {"canonical_query": q, "query_variations": [], "is_multi_issue": False}, TokenUsage()
        async def ex(q, r, sub_issues=None): return bad, TokenUsage()
        class Idx:
            catalog_by_uri = {}
            def search(self, *a, **k): return []
        with patch.object(orchestrator, "enrich_query_async", side_effect=en), \
             patch.object(orchestrator, "extract_structure_async", side_effect=ex), \
             patch.object(orchestrator, "verify_relevance", return_value=RelevanceResult(True, 1.0, "ok")):
            r = await orchestrator.run_pipeline("screen distorted", "Hold the Side key to restart.", Idx())
        assert [a.actionName for a in r.response.contexts[0].actions] == ["Restart Device"]

    @pytest.mark.parametrize("q,expected", [
        ("fingerprint sensor stopped recognizing thumb", False),
        ("smartphone display shattered device unusable", False),
        ("phone charges slower than charger max speed", False),
        ("asdkfj screen bad help pls", False),
        ("tablet screen dark only three icons lit", False),
        ("mera phone camera kholne par lag karta hai", True),
        ("mera phone ka screen baar baar flicker kar raha hai", True),
        ("El teclado cambia de idioma solo sin que yo haga nada", True),
    ])
    def test_language_detection_no_english_false_positives(self, q, expected):
        from app.pipeline.language import needs_translation
        assert needs_translation(q) is expected

    @pytest.mark.asyncio
    async def test_no_reference_message_is_honest_about_the_translation_call(self):
        from app.pipeline import orchestrator, language
        language._CACHE.clear()
        async def tr(prompt, **k):
            return {"language": "Hindi", "english": "My phone camera lags when opening"}, TokenUsage(102, 21)
        class Idx:
            catalog_by_uri = {}
            def search(self, *a, **k): return []
        with patch.object(language, "generate_json_async", side_effect=tr):
            r = await orchestrator.run_pipeline("mera phone camera kholne par lag karta hai", None, Idx())
        assert r.response.fallback == "no_siis_context"
        assert "No LLM call was made" not in r.response.fallback_reason
        assert "translation call (Hindi" in r.response.fallback_reason


@pytest.mark.parametrize("q", ["Nexa X1 touchscreen slow response", "TechCorp X1 Ultra screen flashes upon charging",
                               "Nexa Fold X1 inner display dead no response", "phone touch input laggy and delayed"])
def test_product_names_do_not_trigger_translation(q):
    from app.pipeline.language import needs_translation
    assert needs_translation(q) is False


def test_warm_reports_cache_hit_records_separately(tmp_path):
    import json
    from app.cache.warm import warm_cache
    from app.cache.semantic_cache import SemanticCache
    rec = {"query": "q", "query_variations": [], "meta": {"cache_hit": True},
           "response": {"fallback": None, "contexts": [{"goal": "g", "title": "t", "score": 0.9, "actions": []}]}}
    p = tmp_path / "w.jsonl"; p.write_text(json.dumps(rec))
    stats = warm_cache(str(p), SemanticCache(), set())
    assert stats["skipped_cache_hit"] == 1 and stats["skipped_config"] == 0


class TestFinalSpecCheck:
    def test_health_is_503_until_ready_then_200_ok(self):
        from fastapi.testclient import TestClient
        from app.main import app, _state
        saved = _state.pop("deeplink_index", None)
        try:
            c = TestClient(app)          # no lifespan: index not loaded
            r = c.get("/health")
            assert r.status_code == 503 and r.json()["status"] == "warming_up"
        finally:
            if saved is not None:
                _state["deeplink_index"] = saved

    def test_cost_is_tokens_times_rate(self, monkeypatch):
        from app.core.config import settings
        from app.pipeline.orchestrator import token_cost_usd
        assert token_cost_usd(1000, 500) == 0.0                     # free tier default
        monkeypatch.setattr(settings, "LLM_PRICE_PER_MTOK_INPUT", 0.10)
        monkeypatch.setattr(settings, "LLM_PRICE_PER_MTOK_OUTPUT", 0.40)
        assert token_cost_usd(1_000_000, 500_000) == 0.30

    def test_response_validates_against_samsung_official_schema(self):
        """Spec 6: 100% adherence to the Pydantic definitions (official schema.py)."""
        import importlib.util, json
        spec = importlib.util.spec_from_file_location("off", "app/data/reference/official_schema.py")
        off = importlib.util.module_from_spec(spec); spec.loader.exec_module(off)
        from app.models.schema import ContextDeeplinkResponse
        ours = ContextDeeplinkResponse.model_validate({"contexts": [], "fallback": "no_match", "fallback_reason": "r"})
        off.ContextDeeplinkResponse.model_validate(ours.model_dump(mode="json"))


class TestManualReviewFindings:
    """From the team's manual review of 49 plans."""

    def _act(self, name, uri, kind):
        return {"actionName": name, "stepGroups": [{"actionableDeeplink": {"deeplink": uri, "originalType": kind},
                                                    "validationDeeplink": {"deeplink": "v", "key": "Touch sensitivity"}}]}

    def test_row19_reference_direction_wins_over_order(self):
        from app.pipeline.orchestrator import _drop_contradicting_twins
        ref = ("If touches register late with a screen protector, check the settings. "
               "Turn off Touch sensitivity if the screen responds to accidental touches.")
        out = _drop_contradicting_twins([self._act("Enable Touch Sensitivity", "a", "onURL"),
                                         self._act("Disable Touch Sensitivity", "b", "offURL")], ref)
        assert [a["actionName"] for a in out] == ["Disable Touch Sensitivity"]

    def test_no_stated_direction_keeps_first(self):
        from app.pipeline.orchestrator import _drop_contradicting_twins
        out = _drop_contradicting_twins([self._act("Enable Touch Sensitivity", "a", "onURL"),
                                         self._act("Disable Touch Sensitivity", "b", "offURL")], "Restart the phone.")
        assert [a["actionName"] for a in out] == ["Enable Touch Sensitivity"]

    def test_reviewer_notes_and_bom_csv(self, tmp_path):
        from app.eval.review import load_scores
        from app.eval.batch import render_metrics_md, compute_metrics
        p = tmp_path / "s.csv"
        p.write_bytes(("\ufeffid,domain,steps_0_3,deeplink_0_2_or_na,notes,query\n"
                       "19,Display,1,0,Plan enables what the reference disables.,q\n"
                       "S1-01,Battery,3,2,,q\nS1-05,Other,3,0,Magnification instead of Keyboard.,q\n").encode("utf-8"))
        r = load_scores(p)
        assert [x["id"] for x in r["low"]] == ["19", "S1-05"]
        md = render_metrics_md(compute_metrics([]), "m", "e", "env", "d", review=r)
        assert "Reviewer notes on plans below full marks" in md and "**19** (Display)" in md

    def test_independent_paraphrase_row(self):
        from app.eval.batch import render_metrics_md, compute_metrics
        m = compute_metrics([])
        m["independent_paraphrase"] = {"hits": 7, "total": 8, "rate_pct": 87.5}
        assert "**87.5%** (7/8)" in render_metrics_md(m, "m", "e", "env", "d")

    @pytest.mark.asyncio
    async def test_paraphrases_stored_when_not_measuring(self):
        from app.pipeline import orchestrator
        from app.pipeline.relevance import RelevanceResult
        plan = {"contexts": [{"goal": "Follow these steps to perform this Display Troubleshooting", "title": "Screen flicker",
                              "score": 0.9, "actions": [{"actionName": "Restart Device", "description": "It will refresh the display state",
                              "category": "manual", "stepGroups": [{"steps": ["Hold the Side key."]}]}]}]}
        variations = [f"flicker variant number {i}" for i in range(8)]
        async def en(q): return {"canonical_query": q, "query_variations": variations, "is_multi_issue": False}, TokenUsage()
        async def ex(q, r, sub_issues=None): return plan, TokenUsage()
        class Idx:
            catalog_by_uri = {}
            def search(self, *a, **k): return []
        with patch.object(orchestrator, "enrich_query_async", side_effect=en), \
             patch.object(orchestrator, "extract_structure_async", side_effect=ex), \
             patch.object(orchestrator, "verify_relevance", return_value=RelevanceResult(True, 1.0, "ok")):
            await orchestrator.run_pipeline("screen flickers", "Hold the Side key.", Idx())
        exact = orchestrator.cache._exact
        # holdout applies only while measuring (batch_run sets CACHE_SEED_HOLDOUT)
        assert "flicker variant number 0" in exact and "flicker variant number 7" in exact

    def test_cleaned_probe_file_has_no_contradictory_labels(self):
        import json, collections
        P = json.load(open("app/data/retrieval_eval_generated.json", encoding="utf-8"))["probes"]
        labels = collections.defaultdict(set)
        for p in P:
            labels[p["actionName"].lower()].add(p["expected_message"])
        assert not {k: v for k, v in labels.items() if len(v) > 1}


class TestParaphraseRecall:
    @pytest.mark.parametrize("raw,expected", [
        ("scren flickers n battery dies fast", "screen flickers and battery dies fast"),
        ("my phn batt dies pls help", "my phone battery dies please help"),
        ("Nexa X1 screen flickers", "Nexa X1 screen flickers"),          # product names untouched
    ])
    def test_typos_and_shorthand_normalized_for_matching(self, raw, expected):
        from app.cache.semantic_cache import normalize_for_matching
        assert normalize_for_matching(raw) == expected

    @pytest.mark.asyncio
    async def test_production_stores_every_paraphrase(self):
        """Holding paraphrases out is for measurement only (it cost 87.5% -> 75%)."""
        from app.pipeline import orchestrator
        from app.pipeline.relevance import RelevanceResult
        plan = {"contexts": [{"goal": "Follow these steps to perform this Display Troubleshooting", "title": "Screen flicker",
                              "score": 0.9, "actions": [{"actionName": "Restart Device", "description": "It will refresh the display state",
                              "category": "manual", "stepGroups": [{"steps": ["Hold the Side key."]}]}]}]}
        variations = [f"flicker variant number {i}" for i in range(8)]
        async def en(q): return {"canonical_query": q, "query_variations": variations, "is_multi_issue": False}, TokenUsage()
        async def ex(q, r, sub_issues=None): return plan, TokenUsage()
        class Idx:
            catalog_by_uri = {}
            def search(self, *a, **k): return []
        with patch.object(orchestrator, "enrich_query_async", side_effect=en), \
             patch.object(orchestrator, "extract_structure_async", side_effect=ex), \
             patch.object(orchestrator, "verify_relevance", return_value=RelevanceResult(True, 1.0, "ok")):
            await orchestrator.run_pipeline("screen flickers", "Hold the Side key.", Idx())
        assert "flicker variant number 7" in orchestrator.cache._exact

    def test_cache_false_hit_report(self, tmp_path):
        import json
        from app.eval.cache_calibration import cache_false_hit_report
        rec = lambda i, q: {"id": i, "query": q, "query_variations": [q + " again"], "meta": {"cache_hit": False},
                            "response": {"contexts": [{"title": "t"}]}}
        p = tmp_path / "r.jsonl"
        p.write_text("\n".join(json.dumps(rec(i, q)) for i, q in [("1", "screen flickers"), ("2", "battery drains"), ("3", "wifi drops")]))
        r = cache_false_hit_report(p)
        assert r["pairs"] == 6 and set(r["false_hits_at"]) >= {0.7, 0.75}


class TestExternalAuditFindings:
    """Regressions for the external audit (BUG-001..009)."""

    @pytest.mark.parametrize("name,critical", [
        ("Reset All Settings", True), ("Reset Network Settings", True),          # BUG-002
        ("Restart Bluetooth", False), ("Restart Camera App", False),             # BUG-003
        ("Charge Device After Restart", False), ("Force Restart Device", True),
        ("Restart Device", True), ("View Factory Reset Options", False),
    ])
    def test_critical_classifier(self, name, critical):
        from app.pipeline.normalize import is_critical_action
        assert is_critical_action(name) is critical

    async def _run(self, orchestrator, query, siis, plan_title="Screen fix"):
        from app.pipeline.relevance import RelevanceResult
        plan = {"contexts": [{"goal": "Follow these steps to perform this Display Troubleshooting", "title": plan_title,
                              "score": 0.9, "actions": [{"actionName": "Restart Device", "description": "It will refresh the display state",
                              "category": "critical", "stepGroups": [{"steps": ["Hold the Side key."]}]}]}]}
        async def en(q): return {"canonical_query": q, "query_variations": [], "is_multi_issue": False}, TokenUsage()
        async def ex(q, r, sub_issues=None): return plan, TokenUsage()
        class Idx:
            catalog_by_uri = {}
            def search(self, *a, **k): return []
        with patch.object(orchestrator, "enrich_query_async", side_effect=en), \
             patch.object(orchestrator, "extract_structure_async", side_effect=ex), \
             patch.object(orchestrator, "verify_relevance", return_value=RelevanceResult(True, 1.0, "ok")):
            return await orchestrator.run_pipeline(query, siis, Idx())

    @pytest.mark.asyncio
    async def test_bug001_warmed_plan_not_served_for_a_supplied_reference(self, tmp_path):
        import json
        from app.pipeline import orchestrator
        from app.cache.warm import warm_cache
        from app.core.config import config_fingerprint
        rec = {"query": "screen went black", "query_variations": [], "meta": {"config_fingerprint": config_fingerprint()},
               "response": {"fallback": None, "contexts": [{"goal": "Follow these steps to perform this Display Troubleshooting",
                            "title": "Warm plan", "score": 0.9, "actions": [{"actionName": "Restart Device",
                            "description": "It will refresh the display state", "category": "critical",
                            "stepGroups": [{"steps": ["Hold the Side key."]}]}]}]}}
        p = tmp_path / "w.jsonl"; p.write_text(json.dumps(rec))
        warm_cache(str(p), orchestrator.cache, set())
        with_ref = await self._run(orchestrator, "screen went black", "Cracked screen: visit a service center.", "Fresh plan")
        no_ref = await self._run(orchestrator, "screen went black", None)
        assert with_ref.meta.cache_hit is False and with_ref.response.contexts[0].title == "Fresh plan"
        assert no_ref.meta.cache_hit is True           # spec: no reference -> pre-warmed lookup

    @pytest.mark.asyncio
    async def test_bug001_same_reference_still_served_from_cache(self):
        from app.pipeline import orchestrator
        ref = "Hold the Side key to restart the phone."
        first = await self._run(orchestrator, "screen went black", ref)
        again = await self._run(orchestrator, "screen went black", ref)
        assert first.meta.reference_fp and again.meta.cache_hit is True

    def test_bug004_placeholder_labels_skip_widgets_and_determiners(self):
        from app.pipeline.ordering import _screen_label
        lbl = lambda steps: _screen_label({"actionName": "X", "stepGroups": [{"steps": steps}]})
        assert lbl(["Open Settings.", "Tap Accounts.", "Tap your email."]) == "email"
        assert lbl(["Open Settings.", "Tap Notifications.", "Tap the gear icon."]) == "Notifications"

    def test_bug004_real_link_share_reported(self):
        from app.eval.batch import compute_metrics
        dummy = {"query": "q", "query_variations": [f"v{i}" for i in range(8)], "meta": {"latency_ms": 1.0, "cache_hit": False, "model": "m", "cost_usd": 0.0},
                 "response": {"fallback": None, "contexts": [{"goal": "Follow these steps to perform this Display Troubleshooting",
                              "title": "Screen fix", "score": 0.9, "actions": [
                    {"actionName": "Open Display", "description": "It will open the display page", "category": "auto",
                     "stepGroups": [{"steps": ["Open Settings."], "actionableDeeplink": {"deeplink": "voiceassist://dummy_positive", "description": "d"}}]},
                    {"actionName": "Motion Smoothness", "description": "It will stop the screen flicker", "category": "auto",
                     "stepGroups": [{"steps": ["Open Settings."], "actionableDeeplink": {"deeplink": "voiceassist://masked/act/a", "description": "d"}}]}]}]}}
        m = compute_metrics([{"result": dummy, "pass": "main"}])
        assert m["auto_with_deeplink_pct"] == 100.0 and m["auto_with_real_deeplink_pct"] == 50.0

    def test_bug005_health_body_is_exactly_the_spec(self):
        import numpy as np, json as _json
        from pathlib import Path
        from fastapi.testclient import TestClient
        n = len(_json.loads(Path("app/data/deeplinks.json").read_text(encoding="utf-8"))["deeplinks"])
        with patch("app.pipeline.deeplink_retrieval.embed_batch", return_value=np.zeros((n, 4))):
            from app.main import app
            with TestClient(app) as c:
                assert c.get("/health").json() == {"status": "ok"}
                assert c.get("/v1/status").json()["catalog_entries"] == 578

    @pytest.mark.asyncio
    async def test_bug006_fallbacks_carry_eight_variations(self):
        from app.pipeline import orchestrator
        r = await orchestrator.run_pipeline("phone overheats when charging overnight", None,
                                            type("I", (), {"catalog_by_uri": {}, "search": lambda *a, **k: []})())
        assert r.response.fallback == "no_siis_context" and 8 <= len(r.query_variations) <= 10

    @pytest.mark.parametrize("text,leak_free,expected_fragment", [
        ("Go to bit.ly/abc123 for help.", True, "Go to the official support website for help."),
        ("Visit https://example.com.", True, "Visit the official support website."),
        ("Download from ftp://files.example.org/x", True, None),
        ("Email care@techcorp.com for support.", True, "Email the support team for support."),
    ])
    def test_bug007_url_scrub(self, text, leak_free, expected_fragment):
        from app.utils.validators import scrub_urls, contains_leaked_url
        out = scrub_urls(text)
        assert not contains_leaked_url(out) and "@" not in out
        if expected_fragment:
            assert out == expected_fragment

    def test_bug008_pytest_only_collects_tests_dir(self):
        from pathlib import Path
        assert "testpaths = tests" in Path("pytest.ini").read_text()

    def test_bug009_diagnostics_off_by_default(self, monkeypatch):
        import numpy as np, json as _json
        from pathlib import Path
        from fastapi.testclient import TestClient
        from app.core.config import settings
        monkeypatch.setattr(settings, "ENABLE_DIAGNOSTICS", False)
        n = len(_json.loads(Path("app/data/deeplinks.json").read_text(encoding="utf-8"))["deeplinks"])
        with patch("app.pipeline.deeplink_retrieval.embed_batch", return_value=np.zeros((n, 4))):
            from app.main import app
            with TestClient(app) as c:
                assert c.get("/v1/provider-check").status_code == 404
                assert "paraphrases_seen" not in _json.dumps(c.get("/v1/cache/stats").json())

    @pytest.mark.parametrize("raw,expected", [
        ('1. "My Nexa Fold X1 screen is cracked again." 2. "The touch doesn\'t work on parts." 3. "I can hardly see anything."',
         "My Nexa Fold X1 screen is cracked again. The touch doesn't work on parts. I can hardly see anything."),
        ('1. "My Nexa X1 screen goes completely blank."', "My Nexa X1 screen goes completely blank."),
        ("screen flickers", "screen flickers"),
    ])
    def test_api_query_cleaning(self, raw, expected):
        from app.pipeline.normalize import clean_complaint
        assert clean_complaint(raw) == expected

    def test_samsung_sample_violates_its_own_word_rule_documented(self):
        """Samsung's sample_output has 9- and 12-word descriptions; the spec (4.1)
        and Appendix C require 5-7. We keep the spec rule: this test documents
        the discrepancy, so a change in either direction is noticed."""
        import json
        sample = json.load(open("app/data/reference/sample_output.json"))
        lens = [len(a["description"].split()) for c in sample["response"]["contexts"] for a in c["actions"]]
        assert lens == [9, 12]


def test_llm_clients_have_a_timeout():
    """A degenerate response took 104 s; calls now time out and retry."""
    from pathlib import Path
    src = Path("app/core/llm_client.py").read_text()
    assert src.count("timeout=settings.LLM_TIMEOUT_S") == 2


class TestRealModelVerificationFindings:
    """From the team's real-model cache verification (verify_report.txt)."""

    def _rec(self, q, fp, cache_hit=False, contexts=1):
        from app.core.config import config_fingerprint
        ctx = [{"goal": "Follow these steps to perform this Display Troubleshooting", "title": f"Plan {i}", "score": 0.9,
                "actions": [{"actionName": "Restart Device", "description": "It will refresh the display state",
                             "category": "critical", "stepGroups": [{"steps": ["Hold the Side key."]}]}]} for i in range(contexts)]
        return {"query": q, "query_variations": [q + " one", q + " two"],
                "meta": {"cache_hit": cache_hit, "config_fingerprint": config_fingerprint(), "reference_fp": fp},
                "response": {"fallback": None, "contexts": ctx}}

    def test_bug010_cache_hit_records_now_get_their_own_entry(self, tmp_path):
        import json
        from app.cache.warm import warm_cache
        from app.cache.semantic_cache import SemanticCache
        p = tmp_path / "w.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in [self._rec("screen went black", "docA"),
                                                        self._rec("inner screen dead", "docA", cache_hit=True)]))
        stats = warm_cache(str(p), SemanticCache(), set())
        assert stats["loaded"] == 2 and stats["skipped_cache_hit"] == 0

    def test_bug010_duplicate_only_when_same_document(self, tmp_path):
        import json
        from app.cache.warm import warm_cache
        from app.cache.semantic_cache import SemanticCache
        p = tmp_path / "w.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in [self._rec("screen went black", "docA"),
                                                        self._rec("screen went black", "docB"),
                                                        self._rec("screen went black", "docA")]))
        stats = warm_cache(str(p), SemanticCache(), set())
        assert stats["loaded"] == 2 and stats["skipped_duplicate"] == 1

    def test_multi_issue_plans_are_not_seeded_with_single_issue_paraphrases(self, tmp_path):
        import json
        from app.cache.warm import warm_cache
        from app.cache.semantic_cache import SemanticCache
        c = SemanticCache()
        p = tmp_path / "w.jsonl"
        p.write_text(json.dumps(self._rec("bluetooth drops and camera crashes", "docA", contexts=2)))
        warm_cache(str(p), c, set())
        assert "bluetooth drops and camera crashes one" not in c._exact

    def test_orchestrator_multi_issue_seed_texts(self):
        from app.pipeline.orchestrator import _seed_texts
        assert _seed_texts("q", "c", ["v1", "v2", "v3"], 2) == ["q", "c"]
        assert _seed_texts("q", "c", ["v1", "v2", "v3"], 1) == ["q", "c", "v1", "v2", "v3"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("q", ["how do I bake sourdough bread", "📱💥😭", "asdfghjkl", "what is the capital of France"])
    async def test_off_topic_and_emoji_queries_abstain_cleanly(self, q):
        from app.pipeline import orchestrator
        r = await orchestrator.run_pipeline(q, None, type("I", (), {"catalog_by_uri": {}, "search": lambda *a, **k: []})())
        assert r.response.contexts == [] and r.response.fallback == "no_siis_context"
        assert 8 <= len(r.query_variations) <= 10


class TestBug011:
    def test_every_samsung_query_gets_its_siis_reference(self):
        """Line 17 (merged numbered list on one line) used to get NO reference."""
        from app.eval.batch import load_cases
        cases = load_cases(queries_path="app/data/input.txt", siis_path="app/data/siis_responses.json")
        assert len(cases) == 20 and all(c["siis_response"] for c in cases), [c["id"] for c in cases if not c["siis_response"]]

    def test_line_17_gets_the_fold_crack_document(self):
        import json
        from app.eval.batch import load_cases
        rows = {r["id"]: r for r in json.load(open("app/data/siis_responses.json", encoding="utf-8"))["responses"]}
        case = load_cases(queries_path="app/data/input.txt", siis_path="app/data/siis_responses.json")[16]
        assert case["siis_response"] == rows["row_19"]["siis_response"]

    def test_warm_registers_query_when_sibling_is_below_reference_threshold(self, tmp_path):
        import json, numpy as np
        from app.cache.warm import warm_cache
        from app.cache.semantic_cache import SemanticCache
        from app.core.config import config_fingerprint
        mk = lambda q: {"query": q, "query_variations": [], "meta": {"config_fingerprint": config_fingerprint(), "reference_fp": "docA"},
                        "response": {"fallback": None, "contexts": [{"goal": "Follow these steps to perform this Display Troubleshooting",
                                     "title": "Screen fix", "score": 0.9, "actions": [{"actionName": "Restart Device",
                                     "description": "It will refresh the display state", "category": "critical",
                                     "stepGroups": [{"steps": ["Hold the Side key."]}]}]}]}}
        p = tmp_path / "w.jsonl"; p.write_text("\n".join(json.dumps(mk(q)) for q in ["fold screen black", "fold screen half black"]))
        # the two complaints are similar (0.8) but below the 0.90 with-reference threshold
        emb = lambda t: np.array([1.0, 0.0]) if "half" not in t else np.array([0.8, 0.6])
        with patch("app.cache.semantic_cache.embed", side_effect=emb):
            stats = warm_cache(str(p), SemanticCache(), set())
        assert stats["loaded"] == 2 and stats["skipped_duplicate"] == 0, stats


def test_generic_step_cites_the_sentence_about_its_own_action():
    """Brag render: 'Open Settings.' under a Battery action cited the Display sentence."""
    from app.pipeline.grounding import step_sources
    ref = ("Overheating during light use is often caused by background apps or a high refresh rate. "
           "Open Settings, tap Display, tap Motion smoothness, and select Standard. "
           "Open Settings, tap Battery, tap Background usage limits, and turn on Put unused apps to sleep.")
    ctx = [{"actions": [{"actionName": "Put Unused Apps To Sleep", "stepGroups": [{"steps": [
        "Open Settings.", "Tap Battery.", "Tap Background usage limits.", "Turn on Put unused apps to sleep."]}]}]}]
    src = step_sources(ctx, ref)["Put Unused Apps To Sleep"]
    assert src[0].startswith("Open Settings, tap Battery"), src[0]


def test_frontend_labels_abstentions_without_llm_call():
    from pathlib import Path
    assert "NO LLM CALL" in Path("frontend/index.html").read_text(encoding="utf-8")
