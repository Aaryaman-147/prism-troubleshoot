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
    r"(https?://\S+|ftp://\S+|www\.\S+|\[.*?\]\(.*?\)|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}/\S*"
    r"|\b[a-z0-9-]+\.(com|org|net|io|co|ly|in|me|app)\b\S*)",
    re.IGNORECASE,
)
EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")


def contains_leaked_url(text: str) -> bool:
    """Zero URL Leaks constraint: catch http(s), www., markdown links, bare domains."""
    return bool(URL_PATTERN.search(text))


def scrub_urls(text: str) -> str:
    """Remove URLs and whole e-mail addresses (no 'care@' fragments), then
    repair the sentence: where a URL followed "go to / visit / at / via / on /
    from", put "the official support website"; elsewhere just drop it.
    'Go to bit.ly/x for help.' -> 'Go to the official support website for help.'"""
    def _mark(m):   # keep sentence punctuation the URL pattern swallowed ("…example.com.")
        trail = re.search(r"[.,;:!?)]+$", m.group(0))
        return " \x00 " + (trail.group(0) if trail else "")
    marked = URL_PATTERN.sub(_mark, EMAIL_PATTERN.sub("the support team", text))
    marked = re.sub(r"\b(to|visit|at|via|on|from)\s+\x00", r"\1 the official support website", marked, flags=re.I)
    cleaned = marked.replace("\x00", "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return re.sub(r"\s+([.,;:!?])", r"\1", cleaned)


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
    _TRAILING_STOPWORDS = {"and", "or", "the", "a", "an", "with", "for", "in", "on", "during", "when",
                           "while", "after", "before", "at", "by", "from", "of", "to", "into", "via"}

    _FILLER = {"or", "and", "the", "a", "an", "of", "on", "in", "with", "for", "to"}
    raw_words = title.strip().split()
    if len(raw_words) > max_words:
        # "and" joins two topics ("Screen flicker and battery") -> keep the first.
        lw = [w.lower() for w in raw_words]
        if "and" in lw and 2 <= lw.index("and") <= max_words:
            return " ".join(raw_words[:lw.index("and")])
        # Drop filler first: "Blank or white screen" -> "Blank white screen",
        # not the truncated "Blank or white" seen in a real run.
        content = [w for w in raw_words if w.lower() not in _FILLER]
        if 2 <= len(content) <= max_words:
            return " ".join(content)
        title = " ".join(content) if len(content) >= 2 else title
    words = title.strip().split()
    if len(words) <= max_words:
        return title.strip()

    truncated = words[:max_words]
    while len(truncated) > 1 and truncated[-1].lower() in _TRAILING_STOPWORDS:
        truncated = truncated[:-1]

    return " ".join(truncated)


def repair_action_name(name: str) -> str:
    """Capitalize the first letter of each word, preserving acronyms
    ("configure NFC settings" -> "Configure NFC Settings")."""
    return " ".join(w[:1].upper() + w[1:] for w in str(name or "").split())


def repair_description(desc: str, max_words: int = 7) -> str:
    """Trim an over-long 'It will ...' description to max_words, dropping a
    dangling trailing stopword. Too-short or wrongly-prefixed descriptions
    are left alone -- padding or rewording would change meaning."""
    stop = {"and", "or", "the", "a", "an", "with", "for", "in", "on", "to", "of", "is", "are", "if",
            "that", "which", "whether", "can", "be", "by", "from", "into", "at", "via", "your", "its"}
    filler = {"the", "a", "an", "any", "your", "its", "all", "proper", "correct", "properly", "correctly"}
    words = str(desc or "").strip().rstrip(".").split()
    if len(words) <= max_words:
        return " ".join(words)
    # First drop articles/filler after "It will" -- "It will display the
    # screen on an external monitor" (9) -> "It will display screen on
    # external monitor" (7) keeps the meaning; a blind cut did not.
    head, rest = words[:2], [w for w in words[2:] if w.lower() not in filler]
    words = head + rest
    words = words[:max_words]
    while len(words) > 5 and words[-1].lower().strip(".,") in stop:
        words = words[:-1]
    return " ".join(words).rstrip(",")


_GOAL_PREFIX = "Follow these steps to perform this"


def repair_goal(goal: str, title: str = "") -> str:
    """Spec: 'Follow these steps to perform this <Topic> Troubleshooting'
    (or '... Configuration'). Only the prefix was enforced; a missing suffix
    passed silently. Append ' Troubleshooting' when neither suffix is
    present; rebuild from the title if the prefix itself is missing."""
    g = str(goal or "").strip().rstrip(".")
    if not g.startswith(_GOAL_PREFIX):
        topic = str(title or "").strip().rstrip(".").title() or "Device"
        return f"{_GOAL_PREFIX} {topic} Troubleshooting"
    if not (g.endswith("Troubleshooting") or g.endswith("Configuration")):
        g += " Troubleshooting"
    return g


def repair_title_case(title: str, query: str = "") -> str:
    """Spec: title in sentence case ("Screen display damage"). Capitalize the
    first word; lowercase later Capitalized words ("Touchscreen Lag" ->
    "Touchscreen lag") unless they're acronyms, contain digits, or appear
    capitalized in the user's own complaint (device names: "Nexa Fold")."""
    words = str(title or "").strip().split()
    if not words:
        return ""
    proper = set(re.findall(r"\b[A-Z][\w-]*", query or ""))
    out = [words[0][:1].upper() + words[0][1:]]
    for w in words[1:]:
        if w.isalpha() and w[:1].isupper() and w[1:].islower() and w not in proper:
            w = w.lower()
        out.append(w)
    return " ".join(out)
