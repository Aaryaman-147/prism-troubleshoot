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


def repair_title(title: str, max_words: int = 3) -> str:
    """
    Trims an over-long title down to max_words rather than discarding the
    whole plan over a cosmetic field. This is a direct implementation of
    the spec's own stated fix for its "Prompt-Only Constraints" pitfall:
    "Enforce programmatic validation, trimming, and correction loops in
    the application layer" — asking an LLM to count words reliably in
    natural language generation doesn't work, so don't rely on it alone.

    Live testing found this genuinely necessary, not theoretical: 3 of 5
    identical repeated queries against the same model failed validation
    on this exact rule (e.g. "Screen flicker and battery" — 4 words,
    trying to cram two symptoms into one title). Discarding an otherwise-
    correct, schema-valid plan over a title being one word too long is a
    worse outcome than truncating it.

    Truncates from the end (keeps the front-loaded subject, which is
    where LLM-generated titles tend to put the actual topic), then strips
    any trailing conjunction/stopword left dangling by the cut
    ("Screen flicker and" -> "Screen flicker") so the result still reads
    like a title rather than a clipped sentence.
    """
    _TRAILING_STOPWORDS = {"and", "or", "the", "a", "an", "with", "for", "in", "on"}

    words = title.strip().split()
    if len(words) <= max_words:
        return title.strip()

    truncated = words[:max_words]
    while len(truncated) > 2 and truncated[-1].lower() in _TRAILING_STOPWORDS:
        truncated = truncated[:-1]

    return " ".join(truncated)
