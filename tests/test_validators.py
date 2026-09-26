"""
Tests for programmatic validators (app/utils/validators.py) — the "Zero
URL Leaks" and "Catalog Integrity" hard constraints from the spec.
Run with: pytest tests/test_validators.py -v
"""
from app.utils.validators import contains_leaked_url, scrub_urls, verify_deeplink_in_catalog, repair_title


class TestUrlLeakDetection:
    def test_https_url_detected(self):
        assert contains_leaked_url("Visit https://samsung.com/support for help") is True

    def test_www_url_detected(self):
        assert contains_leaked_url("Go to www.samsung.com for details") is True

    def test_markdown_link_detected(self):
        assert contains_leaked_url("Check [here](http://example.com)") is True

    def test_bare_domain_detected(self):
        """LLMs often inject bare domains without a scheme — the spec
        explicitly calls this out as a common pitfall."""
        assert contains_leaked_url("Visit samsung.com/support for help") is True

    def test_clean_text_not_flagged(self):
        assert contains_leaked_url("It will fix the display flickering issue") is False

    def test_clean_text_with_settings_path_not_flagged(self):
        assert contains_leaked_url("Open Settings, then Display, then Motion smoothness") is False


class TestUrlScrubbing:
    def test_scrub_removes_full_url(self):
        result = scrub_urls("Visit https://samsung.com/support for help")
        assert "https://" not in result
        assert "samsung.com" not in result

    def test_scrub_removes_bare_domain(self):
        result = scrub_urls("Visit samsung.com/support for help")
        assert "samsung.com" not in result

    def test_scrub_collapses_extra_whitespace(self):
        result = scrub_urls("Visit https://samsung.com/support for help")
        assert "  " not in result  # no double spaces left behind


class TestCatalogVerification:
    def test_deeplink_in_catalog_verified(self):
        catalog = {"bixby://masked/act/battery": {}}
        assert verify_deeplink_in_catalog("bixby://masked/act/battery", catalog) is True

    def test_hallucinated_deeplink_rejected(self):
        catalog = {"bixby://masked/act/battery": {}}
        assert verify_deeplink_in_catalog("bixby://fake/hallucinated", catalog) is False

    def test_altered_deeplink_rejected(self):
        """Even a near-identical but non-verbatim URI must fail — the spec
        requires an exact catalog match, not a fuzzy one."""
        catalog = {"bixby://masked/act/battery_optimization": {}}
        assert verify_deeplink_in_catalog("bixby://masked/act/battery_optimisation", catalog) is False


class TestTitleRepair:
    """
    Regression tests for a real, frequent failure found via live testing:
    scripts/measure_determinism_and_cache.py showed 3 of 5 identical
    repeated queries failing schema validation on this exact rule, always
    from the LLM cramming two symptoms into one title
    ("Screen flicker and battery" — 4 words, schema requires 2-3).
    """
    def test_four_word_title_trimmed_to_valid_length(self):
        result = repair_title("Screen flicker and battery", max_words=3)
        assert 2 <= len(result.split()) <= 3

    def test_trailing_conjunction_is_stripped_after_truncation(self):
        """A naive truncation of 'Screen flicker and battery' to 3 words
        leaves 'Screen flicker and' — reads like a clipped sentence, not
        a title. The trailing stopword should be stripped too."""
        result = repair_title("Screen flicker and battery", max_words=3)
        assert result == "Screen flicker"

    def test_already_valid_title_is_untouched(self):
        result = repair_title("Screen flicker fix", max_words=3)
        assert result == "Screen flicker fix"

    def test_two_word_title_is_untouched(self):
        result = repair_title("Battery drain", max_words=3)
        assert result == "Battery drain"

    def test_stopword_stripping_never_drops_below_two_words(self):
        """Guard against over-stripping: a title that's already exactly
        at max_words and ends in a stopword should NOT be touched, since
        it wasn't over length to begin with."""
        result = repair_title("The screen and", max_words=3)
        assert len(result.split()) >= 2

    def test_exact_failure_case_from_live_testing(self):
        """The precise strings observed failing in production testing."""
        assert 2 <= len(repair_title("Display flicker and battery").split()) <= 3
