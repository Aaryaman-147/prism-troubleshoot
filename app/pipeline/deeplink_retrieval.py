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


class DeeplinkIndex:
    def __init__(
        self,
        catalog_path: str,
        alpha: float | None = None,
        bm25_saturation_k: float | None = None,
    ):
        """
        alpha: weight given to dense score in the hybrid fusion.
               alpha=1.0 -> dense only, alpha=0.0 -> BM25 only.
        bm25_saturation_k: see _normalize_bm25 below.
        """
        self.alpha = settings.DEEPLINK_ALPHA if alpha is None else alpha
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
            searchable = " ".join(
                filter(None, [
                    item.get("description", ""),
                    item.get("message", ""),
                    item.get("qna_description", ""),
                ])
            )
            entry = DeeplinkEntry(
                deeplink=item["deeplink"],
                description=item.get("description", ""),
                message=item.get("message", ""),
                searchable_text=searchable,
            )
            self.entries.append(entry)
            self._catalog_by_uri[entry.deeplink] = item

        tokenized = [e.searchable_text.lower().split() for e in self.entries]
        self._bm25 = BM25Okapi(tokenized)
        self._dense_matrix = embed_batch([e.searchable_text for e in self.entries])

    @property
    def catalog_by_uri(self) -> dict[str, dict]:
        return self._catalog_by_uri

    def _normalize_bm25(self, scores: np.ndarray) -> np.ndarray:
        """
        Map raw BM25 scores into [0, 1) with a saturating transform
        s / (s + k), NOT by dividing by the max.

        Why this changed: max-normalization forces the best-scoring entry to
        exactly 1.0 on every query, no matter how weak the match actually is.
        With alpha=0.5 that alone contributed 0.5 to the fused score, which
        already clears the 0.35 confidence floor — so the floor could never
        fire on the sparse side, and "reject low-similarity matches" was
        silently a no-op. That is why a display fix was still getting a
        battery-settings deeplink attached in the demo.

        A saturating transform is monotonic (ranking is unchanged) but keeps
        the score ABSOLUTE, so a weak top-1 stays a low number and the floor
        can actually reject it. k sets how fast it saturates.
        """
        k = self.bm25_saturation_k
        return scores / (scores + k)

    def search(self, query: str, top_k: int = 5) -> list[tuple[DeeplinkEntry, float]]:
        # Sparse scores
        bm25_scores = self._normalize_bm25(
            np.array(self._bm25.get_scores(query.lower().split()))
        )

        # Dense scores
        q_vec = embed(query)
        dense_scores = self._dense_matrix @ q_vec  # cosine, since normalized

        fused = self.alpha * dense_scores + (1 - self.alpha) * bm25_scores

        top_idx = np.argsort(-fused)[:top_k]
        return [(self.entries[i], float(fused[i])) for i in top_idx]
