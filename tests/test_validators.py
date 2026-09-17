"""
Tests for programmatic validators (app/utils/validators.py) — the "Zero
URL Leaks" and "Catalog Integrity" hard constraints from the spec.
Run with: pytest tests/test_validators.py -v
"""
from app.utils.validators import contains_leaked_url, scrub_urls, verify_deeplink_in_catalog


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
