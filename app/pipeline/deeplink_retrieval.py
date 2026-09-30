import re
"""
Hybrid retrieval over deeplinks.json: BM25 (sparse/keyword) + dense embeddings,
matched against the DESCRIPTIVE metadata fields (description, message,
qna_description) — never against the masked URI string itself. This is
explicit in the spec's pitfalls: "Deeplink identifiers are obfuscated
tokens. Matching must be performed on descriptive metadata fields."

This module is also the natural home for your Day-8 ablation experiment:
hybrid vs. dense-only retrieval accuracy on a held-out set of queries.
Swap `alpha` to 1.0 for dense-only, 0.0 for BM25-only, to run that study.
"""
import json
from dataclasses import dataclass

import numpy as np
from rank_bm25 import BM25Okapi

from app.core.config import settings
from app.core.embeddings import embed, embed_batch, cosine_sim


@dataclass
class DeeplinkEntry:
    deeplink: str
    description: str
    message: str = ""
    searchable_text: str = ""


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_HYPHENATED_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)+")


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens. Previously str.lower().split(), which
    kept punctuation: "keys." never matched "keys", so the last word of
    every step sentence was invisible to BM25."""
    low = str(text).lower()
    # Also emit the joined form of hyphenated terms: "Wi-Fi" -> wi, fi, wifi.
    # The catalog says "Enable WiFi"; without this, "Turn On Wi-Fi" never
    # matched it lexically (a real calibration abstention).
    joined = [m.replace("-", "") for m in _HYPHENATED_RE.findall(low)]
    return _TOKEN_RE.findall(low) + joined


_BOILERPLATE_RE = re.compile(
    r"\s*(?:via|in|on the device via)\s+(?:device|TV)\s+Settings(?:\s+on the device)?\.?\s*$", re.I)


def catalog_search_text(item: dict, version: str = "v2") -> str:
    """
    v1: description + message + qna_description (original).
    v2: + validation.key, the precise setting name ("Adaptive brightness"),
        since messages are often generic; minus the "via device Settings on
        the device" tail shared by 543/578 descriptions, which pulls every
        embedding toward the same point.
    """
    desc = item.get("description", "") or ""
    parts = [desc, item.get("message", ""), item.get("qna_description", "")]
    if version == "v2":
        parts[0] = _BOILERPLATE_RE.sub("", desc)
        parts.append((item.get("validation") or {}).get("key", ""))
    return " ".join(p for p in parts if p)


class DeeplinkIndex:
    def __init__(
        self,
        catalog_path: str,
        alpha: float | None = None,
        bm25_saturation_k: float | None = None,
        text_version: str | None = None,
    ):
        """
        alpha: weight given to dense score in the hybrid fusion.
               alpha=1.0 -> dense only, alpha=0.0 -> BM25 only.
        bm25_saturation_k: see _normalize_bm25 below.
        """
        self.alpha = settings.DEEPLINK_ALPHA if alpha is None else alpha
        self.text_version = text_version or settings.RETRIEVAL_TEXT_VERSION
        self.bm25_saturation_k = (
            settings.BM25_SATURATION_K if bm25_saturation_k is None else bm25_saturation_k
        )
        self.entries: list[DeeplinkEntry] = []
        self._catalog_by_uri: dict[str, dict] = {}
        self._bm25: BM25Okapi | None = None
        self._dense_matrix: np.ndarray | None = None
        self._load(catalog_path)

    def _load(self, catalog_path: str) -> None:
        with open(catalog_path, "r") as f:
            raw = json.load(f)
        # Samsung's real deeplinks.json is {"_readme", "count", "deeplinks":
        # [...]}, not a bare list. Iterating that dict yields its KEYS, so
        # item["deeplink"] crashed the server at startup the moment the real
        # file was dropped in. Accept both shapes.
        if isinstance(raw, dict):
            raw = raw.get("deeplinks") or []

        if not raw:
            # An empty catalog previously crashed the whole app at startup
            # with a cryptic ZeroDivisionError (from BM25/dense score
            # normalization dividing by a max of an empty array) instead of
            # a clear message. Fail loudly and specifically instead — this
            # is a real scenario worth guarding against while waiting on
            # the real deeplinks.json (a truncated copy, a bad export, a
            # temporarily-empty file mid-upload would all trigger this).
            raise ValueError(
                f"Deeplink catalog at '{catalog_path}' is empty (loaded as "
                f"[] or equivalent). The engine cannot resolve any deeplinks "
                f"without at least one catalog entry — check the file wasn't "
                f"truncated or exported incorrectly."
            )

        for item in raw:
            searchable = catalog_search_text(item, self.text_version)
            entry = DeeplinkEntry(
                deeplink=item["deeplink"],
                description=item.get("description", ""),
                message=item.get("message", ""),
                searchable_text=searchable,
            )
            self.entries.append(entry)
            self._catalog_by_uri[entry.deeplink] = item

        tokenized = [tokenize(e.searchable_text) for e in self.entries]
        self._bm25 = BM25Okapi(tokenized)
        self._dense_matrix = embed_batch([e.searchable_text for e in self.entries])

    @property
    def catalog_by_uri(self) -> dict[str, dict]:
        return self._catalog_by_uri

    def _normalize_bm25(self, scores: np.ndarray, query_tokens: list[str]) -> np.ndarray:
        """
        Normalize raw BM25 into [0, 1] as QUERY COVERAGE: raw score divided
        by the IDF mass of the query's distinct informative terms, clipped.

        History: max-normalization forced top-1 to 1.0 on every query (the
        floor could never fire). The fix, s/(s+k), was tuned on a 5-entry
        placeholder catalog; on Samsung's 578-entry catalog raw scores are
        larger, so every candidate saturated to 0.86-0.92 -- the margin
        fired on nearly every action (correct matches discarded), while a
        repair-center action matched "Android personalization service" at
        0.87 on the single word "service" (confidently wrong).

        Coverage is scale-free across catalog size and query length: an
        entry matching most of the query's informative words scores high;
        one matching a single common word scores low.
        """
        idf = self._bm25.idf
        mass = sum(max(idf.get(t, 0.0), 0.0) for t in set(query_tokens))
        if mass <= 0:
            return np.zeros_like(scores)
        return np.clip(scores / mass, 0.0, 1.0)

    def search(
        self, query: str, top_k: int = 5, alpha: float | None = None
    ) -> list[tuple[DeeplinkEntry, float]]:
        """
        alpha: per-call override of the fusion weight. Cheap — BM25 and the
        dense matrix are already built at startup, so overriding alpha per
        request (e.g. from a live demo slider) needs no index rebuild.
        """
        fusion_alpha = self.alpha if alpha is None else alpha

        # Sparse scores
        # Unique tokens: BM25 sums per query token, so a word repeated in the
        # match text (actionName is included twice) was counted 2-3x in the
        # score but once in the coverage denominator -- inflating coverage
        # (a repair action hit 0.86 on "service" alone).
        q_tokens = list(dict.fromkeys(tokenize(query)))
        bm25_scores = self._normalize_bm25(np.array(self._bm25.get_scores(q_tokens)), q_tokens)

        # Dense scores
        q_vec = embed(query)
        dense_scores = self._dense_matrix @ q_vec  # cosine, since normalized

        fused = fusion_alpha * dense_scores + (1 - fusion_alpha) * bm25_scores

        top_idx = np.argsort(-fused)[:top_k]
        return [(self.entries[i], float(fused[i])) for i in top_idx]
