"""
Tests for app/pipeline/enrichment.py — mainly the configurable paraphrase
count (ENRICHMENT_PARAPHRASE_COUNT) and its prompt templating.

Run with: pytest tests/test_enrichment.py -v
"""
from unittest.mock import patch

from app.pipeline.enrichment import _build_prompt, enrich_query


def test_build_prompt_substitutes_given_count():
    """_build_prompt takes count as a parameter — tests the templating,
    not the configured default (see test_enrich_query_uses_configured_default_when_not_overridden
    for that). Config default is 8 per the spec's 8-10 requirement."""
    prompt = _build_prompt("screen flickers", 5)
    assert "... 5 total" in prompt


def test_count_is_actually_substituted():
    prompt = _build_prompt("screen flickers", 9)
    assert "... 9 total" in prompt
    assert "... 5 total" not in prompt


def test_prompt_braces_are_single_not_doubled():
    """
    Regression test: an earlier edit quadrupled the brace-escaping
    ({{{{ instead of {{) when the count placeholder was introduced,
    which made every generated prompt literally ask the LLM for JSON
    wrapped in double braces ('{{ ... }}') instead of single ones
    ('{ ... }') — a real prompt bug that would have degraded every
    extraction call, not just a cosmetic issue.
    """
    prompt = _build_prompt("screen flickers", 5)
    assert "{{" not in prompt
    assert "}}" not in prompt
    assert prompt.count("{") == 1
    assert prompt.count("}") == 1


def test_enrich_query_uses_configured_default_when_not_overridden():
    with patch("app.pipeline.enrichment.settings") as mock_settings, \
         patch("app.pipeline.enrichment.generate_json") as mock_generate:
        mock_settings.ENRICHMENT_PARAPHRASE_COUNT = 7
        mock_generate.return_value = ({"canonical_query": "x", "query_variations": []}, None)

        enrich_query("screen flickers")

        called_prompt = mock_generate.call_args[0][0]
        assert "... 7 total" in called_prompt


def test_enrich_query_explicit_override_wins_over_env_default():
    with patch("app.pipeline.enrichment.settings") as mock_settings, \
         patch("app.pipeline.enrichment.generate_json") as mock_generate:
        mock_settings.ENRICHMENT_PARAPHRASE_COUNT = 5  # env says 5
        mock_generate.return_value = ({"canonical_query": "x", "query_variations": []}, None)

        enrich_query("screen flickers", paraphrase_count=9)  # caller overrides to 9

        called_prompt = mock_generate.call_args[0][0]
        assert "... 9 total" in called_prompt
