"""
Regression tests for the 'NoneType' object is not subscriptable crash seen
in live testing via scripts/measure_determinism_and_cache.py.

Run with: pytest tests/test_llm_client.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import json
from app.core.llm_client import (
    _generate_openrouter,
    _clean_json_text,
    generate_json_async,
    TokenUsage,
)


class FakeChoice:
    def __init__(self, content, finish_reason="stop"):
        self.message = MagicMock(content=content)
        self.finish_reason = finish_reason


class FakeCompletion:
    def __init__(self, choices, usage=None):
        self.choices = choices
        self.usage = usage


def test_choices_none_raises_clear_valueerror_not_typeerror():
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = FakeCompletion(choices=None)

    with patch("app.core.llm_client._openrouter_client", fake_client), \
         patch("app.core.llm_client.settings") as mock_settings:
        mock_settings.OPENROUTER_MODEL = "test-model"
        mock_settings.OPENROUTER_API_KEY = "test-key"

        with pytest.raises(ValueError, match="no choices"):
            _generate_openrouter("prompt", max_output_tokens=500, max_retries=0)


def test_choices_empty_list_raises_clear_valueerror():
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = FakeCompletion(choices=[])

    with patch("app.core.llm_client._openrouter_client", fake_client), \
         patch("app.core.llm_client.settings") as mock_settings:
        mock_settings.OPENROUTER_MODEL = "test-model"
        mock_settings.OPENROUTER_API_KEY = "test-key"

        with pytest.raises(ValueError, match="no choices"):
            _generate_openrouter("prompt", max_output_tokens=500, max_retries=0)


def test_choices_present_but_content_none_still_raises_content_error():
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = FakeCompletion(
        choices=[FakeChoice(content=None, finish_reason="length")]
    )

    with patch("app.core.llm_client._openrouter_client", fake_client), \
         patch("app.core.llm_client.settings") as mock_settings:
        mock_settings.OPENROUTER_MODEL = "test-model"
        mock_settings.OPENROUTER_API_KEY = "test-key"

        with pytest.raises(ValueError, match="no content"):
            _generate_openrouter("prompt", max_output_tokens=500, max_retries=0)


def test_normal_response_still_parses_correctly():
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = FakeCompletion(
        choices=[FakeChoice(content='{"ok": true}')],
        usage=MagicMock(prompt_tokens=10, completion_tokens=5),
    )

    with patch("app.core.llm_client._openrouter_client", fake_client), \
         patch("app.core.llm_client.settings") as mock_settings:
        mock_settings.OPENROUTER_MODEL = "test-model"
        mock_settings.OPENROUTER_API_KEY = "test-key"

        result, usage = _generate_openrouter("prompt", max_output_tokens=500, max_retries=0)

    assert result == {"ok": True}
    assert usage.prompt_tokens == 10
    assert usage.completion_tokens == 5


@pytest.mark.asyncio
async def test_async_path_also_guards_none_choices():
    fake_async_client = MagicMock()
    fake_async_client.chat.completions.create = AsyncMock(
        return_value=FakeCompletion(choices=None)
    )

    with patch("app.core.llm_client._openrouter_async_client", fake_async_client), \
         patch("app.core.llm_client._async_client_loop") as mock_loop, \
         patch("app.core.llm_client.settings") as mock_settings:
        mock_settings.LLM_PROVIDER = "openrouter"
        mock_settings.OPENROUTER_MODEL = "test-model"
        mock_settings.OPENROUTER_API_KEY = "test-key"

        import asyncio
        mock_loop_obj = asyncio.get_running_loop()
        with patch("app.core.llm_client._async_client_loop", mock_loop_obj):
            with pytest.raises(ValueError, match="no choices"):
                await generate_json_async("prompt", max_output_tokens=500, max_retries=0)


class TestEmptyResponseRetry:
    def test_sync_retries_then_succeeds_after_transient_empty_response(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = [
            FakeCompletion(choices=None),
            FakeCompletion(choices=[FakeChoice(content='{"ok": true}')]),
        ]

        with patch("app.core.llm_client._openrouter_client", fake_client), \
             patch("app.core.llm_client.time.sleep") as mock_sleep, \
             patch("app.core.llm_client.settings") as mock_settings:
            mock_settings.OPENROUTER_MODEL = "test-model"
            mock_settings.OPENROUTER_API_KEY = "test-key"
            mock_settings.LLM_TEMPERATURE = 0.2

            result, usage = _generate_openrouter("prompt", max_output_tokens=500, max_retries=2)

        assert result == {"ok": True}
        assert fake_client.chat.completions.create.call_count == 2
        mock_sleep.assert_called_once_with(5)

    def test_sync_raises_valueerror_after_exhausting_retries(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = FakeCompletion(choices=None)

        with patch("app.core.llm_client._openrouter_client", fake_client), \
             patch("app.core.llm_client.time.sleep"), \
             patch("app.core.llm_client.settings") as mock_settings:
            mock_settings.OPENROUTER_MODEL = "test-model"
            mock_settings.OPENROUTER_API_KEY = "test-key"
            mock_settings.LLM_TEMPERATURE = 0.2

            with pytest.raises(ValueError, match="no choices"):
                _generate_openrouter("prompt", max_output_tokens=500, max_retries=2)

        assert fake_client.chat.completions.create.call_count == 3

    @pytest.mark.asyncio
    async def test_async_retries_then_succeeds_after_transient_empty_response(self):
        fake_async_client = MagicMock()
        fake_async_client.chat.completions.create = AsyncMock(
            side_effect=[
                FakeCompletion(choices=None),
                FakeCompletion(choices=[FakeChoice(content='{"ok": true}')]),
            ]
        )

        with patch("app.core.llm_client._openrouter_async_client", fake_async_client), \
             patch("app.core.llm_client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
             patch("app.core.llm_client.settings") as mock_settings:
            mock_settings.LLM_PROVIDER = "openrouter"
            mock_settings.OPENROUTER_MODEL = "test-model"
            mock_settings.OPENROUTER_API_KEY = "test-key"
            mock_settings.LLM_TEMPERATURE = 0.2

            import asyncio
            loop = asyncio.get_running_loop()
            with patch("app.core.llm_client._async_client_loop", loop):
                result, usage = await generate_json_async("prompt", max_output_tokens=500, max_retries=2)

        assert result == {"ok": True}
        mock_sleep.assert_awaited_once_with(5)


def test_retry_check_catches_both_empty_response_message_shapes():
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [
        FakeCompletion(choices=[FakeChoice(content=None, finish_reason="length")]),
        FakeCompletion(choices=[FakeChoice(content='{"ok": true}')]),
    ]

    with patch("app.core.llm_client._openrouter_client", fake_client), \
         patch("app.core.llm_client.time.sleep") as mock_sleep, \
         patch("app.core.llm_client.settings") as mock_settings:
        mock_settings.OPENROUTER_MODEL = "test-model"
        mock_settings.OPENROUTER_API_KEY = "test-key"
        mock_settings.LLM_TEMPERATURE = 0.2

        result, usage = _generate_openrouter("prompt", max_output_tokens=500, max_retries=2)

    assert result == {"ok": True}
    assert fake_client.chat.completions.create.call_count == 2
    mock_sleep.assert_called_once()


def test_persistent_empty_response_does_not_masquerade_as_rate_limit():
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = FakeCompletion(choices=None)

    with patch("app.core.llm_client._openrouter_client", fake_client), \
         patch("app.core.llm_client.time.sleep"), \
         patch("app.core.llm_client.settings") as mock_settings:
        mock_settings.OPENROUTER_MODEL = "test-model"
        mock_settings.OPENROUTER_API_KEY = "test-key"
        mock_settings.LLM_TEMPERATURE = 0.2

        with pytest.raises(ValueError) as exc_info:
            _generate_openrouter("prompt", max_output_tokens=500, max_retries=2)

        from app.core.llm_client import LLMRateLimitError
        assert not isinstance(exc_info.value, LLMRateLimitError)


class TestCleanJsonText:
    def test_trailing_commentary_after_valid_json_is_stripped(self):
        raw = '{"a": 1, "b": [1, 2]}\nThat covers the plan for this case.'
        cleaned = _clean_json_text(raw)
        assert json.loads(cleaned) == {"a": 1, "b": [1, 2]}

    def test_trailing_commentary_containing_its_own_braces_is_stripped(self):
        raw = '{"a": 1}\nFor example, {"other": "example"} is not what we want here.'
        cleaned = _clean_json_text(raw)
        assert json.loads(cleaned) == {"a": 1}

    def test_leading_chain_of_thought_still_stripped(self):
        raw = 'We need to produce JSON. Thus: {"a": 1, "nested": {"b": 2}}'
        cleaned = _clean_json_text(raw)
        assert json.loads(cleaned) == {"a": 1, "nested": {"b": 2}}

    def test_nested_objects_with_matching_braces_still_parse(self):
        raw = '{"a": {"b": {"c": 1}}, "d": 2}'
        assert json.loads(_clean_json_text(raw)) == {"a": {"b": {"c": 1}}, "d": 2}

    def test_brace_characters_inside_string_values_do_not_confuse_depth_counting(self):
        raw = '{"description": "Use the {gear} icon to open settings"}'
        cleaned = _clean_json_text(raw)
        assert json.loads(cleaned) == {"description": "Use the {gear} icon to open settings"}

    def test_genuinely_truncated_json_still_raises_a_clear_error(self):
        raw = '{"a": 1, "b": ["incomplete'
        cleaned = _clean_json_text(raw)
        with pytest.raises(json.JSONDecodeError):
            json.loads(cleaned)

    def test_markdown_fences_still_stripped_before_brace_scan(self):
        raw = '```json\n{"a": 1}\n```'
        assert json.loads(_clean_json_text(raw)) == {"a": 1}


class TestJSONDecodeErrorRetry:
    def test_openrouter_sync_retries_then_succeeds_after_malformed_json(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = [
            FakeCompletion(choices=[FakeChoice(content='{"a": 1')]),
            FakeCompletion(choices=[FakeChoice(content='{"a": 1}')]),
        ]

        with patch("app.core.llm_client._openrouter_client", fake_client), \
             patch("app.core.llm_client.time.sleep") as mock_sleep, \
             patch("app.core.llm_client.settings") as mock_settings:
            mock_settings.OPENROUTER_MODEL = "test-model"
            mock_settings.OPENROUTER_API_KEY = "test-key"
            mock_settings.LLM_TEMPERATURE = 0.2

            result, usage = _generate_openrouter("prompt", max_output_tokens=500, max_retries=2)

        assert result == {"a": 1}
        assert fake_client.chat.completions.create.call_count == 2
        mock_sleep.assert_called_once_with(3)

    def test_openrouter_sync_gives_up_after_persistent_malformed_json(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = FakeCompletion(
            choices=[FakeChoice(content='not json at all')]
        )

        with patch("app.core.llm_client._openrouter_client", fake_client), \
             patch("app.core.llm_client.time.sleep"), \
             patch("app.core.llm_client.settings") as mock_settings:
            mock_settings.OPENROUTER_MODEL = "test-model"
            mock_settings.OPENROUTER_API_KEY = "test-key"
            mock_settings.LLM_TEMPERATURE = 0.2

            from app.core.llm_client import LLMRateLimitError
            with pytest.raises(ValueError) as exc_info:
                _generate_openrouter("prompt", max_output_tokens=500, max_retries=2)
            assert not isinstance(exc_info.value, LLMRateLimitError)

        assert fake_client.chat.completions.create.call_count == 3

    @pytest.mark.asyncio
    async def test_openrouter_async_retries_then_succeeds_after_malformed_json(self):
        fake_async_client = MagicMock()
        fake_async_client.chat.completions.create = AsyncMock(
            side_effect=[
                FakeCompletion(choices=[FakeChoice(content='{"a": 1')]),
                FakeCompletion(choices=[FakeChoice(content='{"a": 1}')]),
            ]
        )

        with patch("app.core.llm_client._openrouter_async_client", fake_async_client), \
             patch("app.core.llm_client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
             patch("app.core.llm_client.settings") as mock_settings:
            mock_settings.LLM_PROVIDER = "openrouter"
            mock_settings.OPENROUTER_MODEL = "test-model"
            mock_settings.OPENROUTER_API_KEY = "test-key"
            mock_settings.LLM_TEMPERATURE = 0.2

            import asyncio
            loop = asyncio.get_running_loop()
            with patch("app.core.llm_client._async_client_loop", loop):
                result, usage = await generate_json_async("prompt", max_output_tokens=500, max_retries=2)

        assert result == {"a": 1}
        mock_sleep.assert_awaited_once_with(3)

    def test_gemini_sync_retries_then_succeeds_after_malformed_json(self):
        fake_model = MagicMock()
        bad_resp = MagicMock()
        bad_resp.candidates = [MagicMock(finish_reason="STOP")]
        bad_resp.text = '{"a": 1'
        good_resp = MagicMock()
        good_resp.candidates = [MagicMock(finish_reason="STOP")]
        good_resp.text = '{"a": 1}'
        good_resp.usage_metadata = MagicMock(prompt_token_count=5, candidates_token_count=3)
        fake_model.generate_content.side_effect = [bad_resp, good_resp]

        with patch("app.core.llm_client._gemini_model", fake_model), \
             patch("app.core.llm_client._configured", True), \
             patch("app.core.llm_client.time.sleep") as mock_sleep, \
             patch("app.core.llm_client.settings") as mock_settings:
            mock_settings.LLM_MODEL = "test-gemini-model"
            mock_settings.LLM_TEMPERATURE = 0.2
            mock_settings.GEMINI_API_KEY = "test-key"

            from app.core.llm_client import _generate_gemini
            result, usage = _generate_gemini("prompt", max_output_tokens=500, max_retries=2)

        assert result == {"a": 1}
        assert fake_model.generate_content.call_count == 2
        mock_sleep.assert_called_once_with(3)
