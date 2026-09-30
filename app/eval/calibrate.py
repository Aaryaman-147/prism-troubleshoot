"""
Retrieval calibration against Samsung's real catalog (replaces the stale
placeholder ablation). For each (alpha, floor, margin) config, run the REAL
resolve_deeplinks logic on labelled probes and count:
  correct - positive probe linked to the expected entry (judged by message:
            the catalog holds duplicate entries under different URIs)
  wrong   - linked to any other real entry, or a negative probe linked at all
  abstain - positive probe fell back to dummy_positive / manual
Samsung: a confidently wrong deeplink is worse than none, so configs are
ranked by fewest WRONG first, then most correct.
"""
import copy
import json
from itertools import product

from app.pipeline.ordering import resolve_deeplinks

DUMMY_SUFFIX = "dummy_positive"


_DEGENERATE = {"onurl", "offurl", "updateurl", "onclickurl"}


def is_degenerate_label(message) -> bool:
    """Catalog entries with junk messages ("Onurl", "Brightness") can't be
    fair probe targets: nothing distinguishes them from their neighbours."""
    m = (message or "").strip().lower()
    return m in _DEGENERATE or len(m.split()) < 2


def load_probes(path):
    probes = json.load(open(path, encoding="utf-8"))["probes"]
    return [p for p in probes if p.get("expected_message") is None or not is_degenerate_label(p["expected_message"])]


def classify(probe, action, catalog) -> str:
    link = (action["stepGroups"][0].get("actionableDeeplink") or {}).get("deeplink")
    real = link and not link.endswith(DUMMY_SUFFIX)
    exp = probe["expected_message"]
    if exp is None:
        return "wrong" if real else "correct"
    if not real:
        return "abstain"
    return "correct" if (catalog.get(link) or {}).get("message") == exp else "wrong"


def evaluate(index, probes, alpha, floor, margin):
    counts = {"correct": 0, "wrong": 0, "abstain": 0}
    detail = []
    for p in probes:
        action = {"actionName": p["actionName"], "description": "It will fix the reported issue",
                  "category": "auto", "stepGroups": [{"steps": list(p["steps"])}]}
        acts, _, _ = resolve_deeplinks([copy.deepcopy(action)], index,
                                       min_confidence=floor, margin=margin, alpha=alpha)
        verdict = classify(p, acts[0], index.catalog_by_uri)
        counts[verdict] += 1
        link = (acts[0]["stepGroups"][0].get("actionableDeeplink") or {})
        got = link.get("deeplink")
        shown = ("dummy_positive: " + link.get("message", "")) if got and got.endswith(DUMMY_SUFFIX) else \
            ((index.catalog_by_uri.get(got) or {}).get("message") or got)
        detail.append((p["actionName"], p["expected_message"], verdict, shown))
    return counts, detail


def _memoized_embeddings():
    """Each probe's text is identical across the ~220 configs, so embed it
    once. Without this the sweep re-ran the model ~11,000 times on CPU and
    looked stuck."""
    import functools
    from unittest.mock import patch
    import app.pipeline.deeplink_retrieval as dr
    cached = functools.lru_cache(maxsize=4096)(dr.embed)
    return patch.object(dr, "embed", cached)


def sweep(index, probes, alphas=(0.0, 0.25, 0.5, 0.75, 1.0),
          floors=tuple(round(0.3 + 0.05 * i, 2) for i in range(11)), margins=(0.0, 0.02, 0.05, 0.08)):
    rows = []
    configs = list(product(alphas, floors, margins))
    with _memoized_embeddings():
        for n, (a, f, m) in enumerate(configs, 1):
            c, _ = evaluate(index, probes, a, f, m)
            rows.append({"alpha": a, "floor": f, "margin": m, **c})
            if n % 44 == 0:
                print(f"  ...{n}/{len(configs)} configs", flush=True)
    rows.sort(key=lambda r: (r["wrong"], -r["correct"], r["floor"]))
    return rows



def relevance_pairs(siis_path):
    """True pairs: Samsung's 20 (query, its own SIIS). False pairs: each query
    paired with a SIIS document whose TITLE differs (several rows share a
    document, so same-title pairs aren't genuine mismatches)."""
    from app.eval.batch import _clean_query
    rows = json.load(open(siis_path, encoding="utf-8"))["responses"]
    true, false = [], []
    for i, r in enumerate(rows):
        true.append((_clean_query(r["original_query"]), r["siis_response"]))
        for k in range(1, len(rows)):
            other = rows[(i + k) % len(rows)]
            if other["siis_response"]["title"] != r["siis_response"]["title"]:
                false.append((_clean_query(r["original_query"]), other["siis_response"]))
                break
    return true, false


def relevance_report(siis_path):
    from app.pipeline.normalize import normalize_siis
    from app.pipeline.relevance import verify_relevance
    true, false = relevance_pairs(siis_path)
    ts = sorted(verify_relevance(q, normalize_siis(s), min_similarity=-1).similarity for q, s in true)
    fs = sorted(verify_relevance(q, normalize_siis(s), min_similarity=-1).similarity for q, s in false)
    # Keep every genuine reference (a false rejection loses the answer
    # outright); the LLM's no_match is a second line of defence for mismatches.
    thr = round(ts[0] - 0.02, 2)
    return {"true_min": round(ts[0], 3), "true_median": round(ts[len(ts) // 2], 3),
            "false_max": round(fs[-1], 3), "false_median": round(fs[len(fs) // 2], 3),
            "recommended_threshold": thr,
            "false_pairs_rejected_at_threshold": sum(1 for x in fs if x < thr), "false_pairs": len(fs)}



def catalog_self_retrieval(index) -> dict:
    """
    All catalog entries, each queried by its OWN message ("Disable Touch
    sensitivity") through the REAL resolution path (intent -> twin collapse
    -> floor -> margin). The 26 probes test realistic actions; this tests
    that every one of the ~578 entries is reachable, and -- the number
    Samsung cares about -- how often the pipeline links a DIFFERENT entry.
    Duplicate entries share messages, so a same-message link counts correct.
    """
    counts = {"correct": 0, "wrong": 0, "abstain": 0, "equivalent": 0, "opposite_toggle": 0, "different_entry": 0}
    wrong_examples = []
    for uri, item in index.catalog_by_uri.items():
        msg = (item.get("message") or "").strip()
        if not msg or uri.endswith(DUMMY_SUFFIX):
            continue
        action = {"actionName": msg, "description": "It will open this setting", "category": "auto",
                  "stepGroups": [{"steps": [f"Open Settings.", f"{msg}."]}]}
        acts, _, _ = resolve_deeplinks([copy.deepcopy(action)], index)
        link = (acts[0]["stepGroups"][0].get("actionableDeeplink") or {}).get("deeplink")
        if not link or link.endswith(DUMMY_SUFFIX):
            counts["abstain"] += 1
        elif (index.catalog_by_uri.get(link) or {}).get("message") == msg:
            counts["correct"] += 1
        else:
            got = index.catalog_by_uri.get(link) or {}
            same_key = (got.get("validation") or {}).get("key") and \
                (got.get("validation") or {}).get("key") == (item.get("validation") or {}).get("key")
            kind = ("equivalent" if same_key and got.get("originalType") == item.get("originalType") else
                    "opposite_toggle" if same_key else "different_entry")
            counts["wrong"] += 1
            counts[kind] = counts.get(kind, 0) + 1
            wrong_examples.append((msg, got.get("message"), kind))
    total = counts["correct"] + counts["wrong"] + counts["abstain"]
    return {"entries": total, **counts,
            "correct_pct": round(100.0 * counts["correct"] / total, 1) if total else None,
            "wrong_pct": round(100.0 * counts["wrong"] / total, 1) if total else None,
            "wrong_examples": wrong_examples[:20]}
