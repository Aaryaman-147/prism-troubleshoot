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

from app.core.embeddings import embed, embed_batch, cosine_sim


@dataclass
class DeeplinkEntry:
    deeplink: str
    description: str
    message: str = ""
    searchable_text: str = ""


class DeeplinkIndex:
    def __init__(self, catalog_path: str, alpha: float = 0.5):
        """
        alpha: weight given to dense score in the hybrid fusion.
               alpha=1.0 -> dense only, alpha=0.0 -> BM25 only.
        """
        self.alpha = alpha
        self.entries: list[DeeplinkEntry] = []
        self._catalog_by_uri: dict[str, dict] = {}
        self._bm25: BM25Okapi | None = None
        self._dense_matrix: np.ndarray | None = None
        self._load(catalog_path)

    def _load(self, catalog_path: str) -> None:
        with open(catalog_path, "r") as f:
            raw = json.load(f)

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

    def search(self, query: str, top_k: int = 5) -> list[tuple[DeeplinkEntry, float]]:
        # Sparse scores
        bm25_scores = np.array(self._bm25.get_scores(query.lower().split()))
        if bm25_scores.max() > 0:
            bm25_scores = bm25_scores / bm25_scores.max()

        # Dense scores
        q_vec = embed(query)
        dense_scores = self._dense_matrix @ q_vec  # cosine, since normalized

        fused = self.alpha * dense_scores + (1 - self.alpha) * bm25_scores

        top_idx = np.argsort(-fused)[:top_k]
        return [(self.entries[i], float(fused[i])) for i in top_idx]
