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
from dataclasses import dataclass

from app.core.embeddings import embed, cosine_sim
from app.core.config import settings


@dataclass
class RelevanceResult:
    is_relevant: bool
    similarity: float
    reason: str


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

    complaint_vec = embed(complaint)
    reference_vec = embed(reference)
    similarity = cosine_sim(complaint_vec, reference_vec)

    if similarity < threshold:
        return RelevanceResult(
            is_relevant=False,
            similarity=similarity,
            reason=f"reference text embedding similarity ({similarity:.3f}) below "
                   f"threshold ({threshold:.3f}) -- likely addresses a different issue",
        )

    return RelevanceResult(is_relevant=True, similarity=similarity, reason="above_threshold")
