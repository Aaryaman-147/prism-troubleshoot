"""
Cache-threshold calibration: how often would a DIFFERENT complaint be served
another complaint's cached plan at each threshold? Uses results/results.jsonl
(each case's query + its generated paraphrases = one cache cluster) and scores
every other case's query against each cluster with the cache's own
max-over-members similarity. Pairs whose SIIS documents share a title are not
counted (same document = same fix; the cache is reference-aware as well).
"""
import json
from pathlib import Path

import numpy as np

from app.core.embeddings import embed
from app.cache.semantic_cache import normalize_for_matching


def cache_false_hit_report(results_path, thresholds=(0.65, 0.68, 0.70, 0.72, 0.75, 0.78, 0.80, 0.85),
                           titles: dict | None = None) -> dict:
    rows = [json.loads(l) for l in Path(results_path).read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if r["response"].get("contexts") and not r["meta"].get("cache_hit")]
    clusters = [np.array([embed(normalize_for_matching(t)) for t in [r["query"], *(r.get("query_variations") or [])]])
                for r in rows]
    qv = [embed(normalize_for_matching(r["query"])) for r in rows]
    titles = titles or {}
    worst = []
    for i, r in enumerate(rows):
        for j, members in enumerate(clusters):
            if i == j:
                continue
            ti, tj = titles.get(str(r.get("id"))), titles.get(str(rows[j].get("id")))
            if ti and ti == tj:
                continue
            worst.append((float(np.max(members @ qv[i])), r["query"][:70], rows[j]["query"][:70]))
    worst.sort(reverse=True)
    sims = [w[0] for w in worst]
    return {"pairs": len(sims), "max": round(sims[0], 3) if sims else None,
            "false_hits_at": {t: sum(1 for x in sims if x >= t) for t in thresholds},
            "top": [(round(s, 3), a, b) for s, a, b in worst[:8]]}
