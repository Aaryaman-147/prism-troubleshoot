"""
Stage 0.5: SIIS Relevance Verification.

Directly implements a specific requirement from the Samsung PRISM Theme-2
discussion meeting: "We need a robust policy for situations where
retrieved SIIS content does not actually match the user's complaint.
Design this around relevance verification and abstention rather than
forcing the retrieved content into an answer."

Why this exists: extraction.py currently trusts whatever siis_response
text is handed to it and tries to build a plan from it unconditionally.
If a caller (or, in the real deployment, an upstream retrieval step
outside this system) passes reference text that doesn't actually address
the complaint -- e.g. a battery-drain complaint paired with swipe-gesture
troubleshooting text -- extraction has no way to notice and will either
hallucinate a forced connection or produce a low-confidence-but-present
plan. Samsung was explicit that null/abstention is PREFERRED over that.

Design: a cheap, fast, LOCAL check (cosine similarity between complaint
and reference embeddings) runs BEFORE the expensive extraction LLM call.
This is deliberately not an LLM call itself -- it needs to be fast enough
to run on every request without meaningfully affecting latency, and the
existing embedding model is already warm (used by the cache and deeplink
retrieval), so this adds a few milliseconds, not seconds.

This is a NECESSARY but not SUFFICIENT check: high embedding similarity
between complaint and reference doesn't guarantee extraction will
succeed (the reference might still lack an actual fix), but low
similarity is a strong, cheap signal that the reference is very likely
irrelevant -- exactly the case Samsung asked to catch and abstain on
rather than force.
"""
import re
from dataclasses import dataclass, field

from app.core.embeddings import embed, cosine_sim

# Splits a complaint into candidate sub-issue clauses on common conjunctions
# and punctuation. Deliberately simple and over-eager: splitting a
# single-issue complaint ("flickers and goes blank") into two clauses is
# harmless here, because we only ever take the MAX similarity across the
# full complaint and its clauses -- extra clauses can only make the check
# more lenient toward a genuinely relevant reference, never stricter.
_CLAUSE_SPLIT = re.compile(r"\b(?:and|also|plus|but|as well as)\b|[,;]", re.IGNORECASE)
_MIN_CLAUSE_WORDS = 3  # too-short fragments ("my phone") match everything vaguely


_CHUNK_WORDS = 80
_MAX_CHUNKS = 40


def _reference_chunks(reference: str) -> list[str]:
    words = reference.split()
    if len(words) <= _CHUNK_WORDS * 1.5:
        return [reference]
    chunks = [" ".join(words[i:i + _CHUNK_WORDS]) for i in range(0, len(words), _CHUNK_WORDS)]
    return [reference] + chunks[:_MAX_CHUNKS]


def _clauses(complaint: str) -> list[str]:
    parts = [p.strip() for p in _CLAUSE_SPLIT.split(complaint)]
    return [p for p in parts if len(p.split()) >= _MIN_CLAUSE_WORDS]
from app.core.config import settings


@dataclass
class RelevanceResult:
    is_relevant: bool
    similarity: float
    reason: str
    # Which text scored best against the reference -- the full complaint,
    # or one of its sub-issue clauses. Useful for debugging multi-issue
    # complaints where only one sub-issue is covered by the reference.
    best_match_text: str = ""


def verify_relevance(
    complaint: str,
    reference: str,
    min_similarity: float | None = None,
) -> RelevanceResult:
    """
    Cheap pre-check: does the reference text even plausibly address the
    complaint, before spending an extraction LLM call on it?

    Returns is_relevant=True automatically when reference is empty --
    that case is ALREADY handled downstream by extraction's own
    "no_match" fallback (empty reference = nothing to extract from), and
    this function's job is specifically catching a MISMATCHED reference,
    not a missing one. Conflating the two would produce a confusing
    "irrelevant" reason for what's actually just "no reference given".
    """
    threshold = settings.SIIS_RELEVANCE_MIN_SIMILARITY if min_similarity is None else min_similarity

    if not reference or not reference.strip():
        return RelevanceResult(is_relevant=True, similarity=1.0, reason="no_reference_provided")

    # Score the full complaint AND each sub-issue clause, keep the best.
    # Why: a multi-issue complaint ("battery dies fast AND swipe gestures
    # are reversed") embeds as an average of both topics. If the reference
    # only covers one of them, the whole-complaint score is diluted and can
    # fall below threshold -- wrongly rejecting a reference that genuinely
    # addresses half the complaint. Clause-level max fixes that; extraction
    # downstream still decides which sub-issues it can actually ground.
    # Real SIIS documents run 1-9k characters; all-MiniLM-L6-v2 truncates at
    # 256 tokens, so embedding the whole document only "saw" its intro.
    # Score against the whole text AND ~80-word chunks; keep the best.
    reference_vecs = [embed(r) for r in _reference_chunks(reference)]
    candidates = [complaint] + [c for c in _clauses(complaint) if c != complaint]
    best_text, similarity = complaint, -1.0
    for text in candidates:
        tv = embed(text)
        sim = max(cosine_sim(tv, rv) for rv in reference_vecs)
        if sim > similarity:
            best_text, similarity = text, sim

    if similarity < threshold:
        return RelevanceResult(
            is_relevant=False,
            similarity=similarity,
            reason=f"reference text embedding similarity ({similarity:.3f}) below "
                   f"threshold ({threshold:.3f}) -- likely addresses a different issue",
            best_match_text=best_text,
        )

    return RelevanceResult(
        is_relevant=True, similarity=similarity, reason="above_threshold",
        best_match_text=best_text,
    )
