"""
Programmatic validation layer. Per the spec's own pitfalls list:
"Prompt-Only Constraints: Asking an LLM to respect word count constraints
in natural language is unreliable. Enforce programmatic validation,
trimming, and correction loops in the application layer."

Never trust the LLM's output directly — always run it through here first.
"""
import re
from typing import Optional

# Catches full http(s)/www URLs, markdown links, and bare domains
# (e.g. "samsung.com/support") that LLMs tend to inject from pretraining
# memory even without a scheme prefix.
URL_PATTERN = re.compile(
    r"(https?://\S+|www\.\S+|\[.*?\]\(.*?\)|\b[a-z0-9-]+\.(com|org|net|io|co)\b\S*)",
    re.IGNORECASE,
)


def contains_leaked_url(text: str) -> bool:
    """Zero URL Leaks constraint: catch http(s), www., markdown links, bare domains."""
    return bool(URL_PATTERN.search(text))


def scrub_urls(text: str) -> str:
    cleaned = URL_PATTERN.sub("", text)
    return re.sub(r"\s+", " ", cleaned).strip()


def verify_deeplink_in_catalog(deeplink_uri: str, catalog: dict[str, dict]) -> bool:
    """
    Catalog Integrity constraint: the deeplink URI must be a VERBATIM match
    from deeplinks.json. Never accept an LLM-generated or altered URI.
    """
    return deeplink_uri in catalog


def enforce_word_count(text: str, min_words: int, max_words: int) -> Optional[str]:
    """Returns None if valid, else an error message describing the violation."""
    n = len(text.strip().split())
    if not (min_words <= n <= max_words):
        return f"expected {min_words}-{max_words} words, got {n}"
    return None
