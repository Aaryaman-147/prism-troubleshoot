"""
Calibrate against Samsung's REAL data. No LLM calls; needs the real embedding
model, so run on your machine.

  python scripts\\calibrate_retrieval.py              # deeplink sweep: text v1 vs v2
  python scripts\\calibrate_retrieval.py --detail     # + per-probe verdicts for the best config
  python scripts\\calibrate_retrieval.py --relevance  # SIIS relevance threshold from the 20 real pairs

Writes results/calibration.md.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.config import settings
from app.eval.calibrate import evaluate, load_probes, relevance_report, sweep
from app.pipeline.deeplink_retrieval import DeeplinkIndex

PROBES = Path("app/data/retrieval_eval_real.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--relevance", action="store_true")
    ap.add_argument("--catalog", action="store_true", help="self-retrieval check over every catalog entry")
    ap.add_argument("--cache", action="store_true", help="cache-threshold false-hit risk from results/results.jsonl")
    ap.add_argument("--probes", choices=["hand", "generated", "all"], default="hand",
                    help="hand = the 26 labelled probes; generated = scripts/generate_probes.py output; all = both")
    a = ap.parse_args()
    lines = []

    if a.cache:
        import json as _json
        from app.eval.cache_calibration import cache_false_hit_report
        titles = {}
        sp = Path(settings.SIIS_RESPONSES_PATH)
        if sp.exists():
            for r in _json.loads(sp.read_text(encoding="utf-8"))["responses"]:
                titles[str(r.get("id", "")).replace("row_", "")] = (r.get("siis_response") or {}).get("title")
        r = cache_false_hit_report("results/results.jsonl", titles=titles)
        lines += [f"# Cache false-hit risk: {r['pairs']} (complaint, other complaint's cluster) pairs", "",
                  f"Highest cross-complaint similarity: {r['max']} (current CACHE_HIT_THRESHOLD {settings.CACHE_HIT_THRESHOLD})",
                  "", "| threshold | complaint pairs that would be served ANOTHER complaint's plan |", "|---|---|"]
        lines += [f"| {t} | {n} |" for t, n in r["false_hits_at"].items()]
        lines += ["", "Closest cross-complaint pairs:", ""] + [f"- {s}: '{q}' ~ '{o}'" for s, q, o in r["top"]]
        lines += ["", "Lower CACHE_HIT_THRESHOLD only to a value with 0 here; each step down catches more paraphrases."]
    elif a.catalog:
        from app.eval.calibrate import catalog_self_retrieval, _memoized_embeddings
        index = DeeplinkIndex(settings.DEEPLINKS_PATH)
        with _memoized_embeddings():
            r = catalog_self_retrieval(index)
        lines += [f"# Catalog reachability: all {r['entries']} entries, each queried by its own message",
                  "through the real pipeline (intent, twin collapse, floor, margin)", "",
                  f"- correct: {r['correct']} ({r['correct_pct']}%)",
                  f"- abstain (dummy/manual, safe): {r['abstain']}",
                  f"- WRONG entry linked: {r['wrong']} ({r['wrong_pct']}%)",
                  f"    - equivalent (same setting + type, different duplicate entry): {r['equivalent']}",
                  f"    - OPPOSITE toggle (serious): {r['opposite_toggle']}",
                  f"    - different entry (near-duplicate or wrong screen; judge by hand): {r['different_entry']}",
                  "", "Wrong examples (query -> linked [kind]):", ""]
        lines += [f"- '{m}' -> '{g}' [{k}]" for m, g, k in r["wrong_examples"]]
    elif a.relevance:
        r = relevance_report(settings.SIIS_RESPONSES_PATH)
        lines += ["# SIIS relevance calibration (20 real pairs vs mismatched pairs)", "",
                  f"Genuine pairs:    min {r['true_min']}, median {r['true_median']}",
                  f"Mismatched pairs: max {r['false_max']}, median {r['false_median']}",
                  f"Threshold keeping every genuine pair: {r['recommended_threshold']} "
                  f"(rejects {r['false_pairs_rejected_at_threshold']}/{r['false_pairs']} mismatched pairs)",
                  "", "```", f"SIIS_RELEVANCE_MIN_SIMILARITY={r['recommended_threshold']}", "```"]
    else:
        gen = Path("app/data/retrieval_eval_generated.json")
        probes = []
        if a.probes in ("hand", "all"):
            probes += load_probes(PROBES)
        if a.probes in ("generated", "all"):
            if not gen.exists():
                sys.exit("No generated probes yet: python scripts\\generate_probes.py --n 100")
            probes += load_probes(gen)
        pos = sum(p["expected_message"] is not None for p in probes)
        lines += [f"# Retrieval calibration — {len(probes)} probes ({pos} should link, {len(probes) - pos} must not)", "",
                  "Ranked by fewest WRONG deeplinks, then most correct. Compared across search-text versions.", ""]
        best_overall = None
        for version in ("v1", "v2"):
            index = DeeplinkIndex(settings.DEEPLINKS_PATH, text_version=version)
            rows = sweep(index, probes)
            best = rows[0]
            lines += [f"## Search text {version}", "", "| alpha | floor | margin | correct | wrong | abstain |",
                      "|---|---|---|---|---|---|"]
            lines += [f"| {r['alpha']} | {r['floor']} | {r['margin']} | {r['correct']} | {r['wrong']} | {r['abstain']} |" for r in rows[:8]]
            lines.append("")
            key = (best["wrong"], -best["correct"])
            if best_overall is None or key < best_overall[0]:
                best_overall = (key, version, best, index)
        _, version, best, index = best_overall
        lines += ["## Recommended .env", "```", f"RETRIEVAL_TEXT_VERSION={version}", f"DEEPLINK_ALPHA={best['alpha']}",
                  f"DEEPLINK_MIN_CONFIDENCE={best['floor']}", f"DEEPLINK_MARGIN={max(best['margin'], 0.02) if best['margin'] == 0 else best['margin']}",
                  "```", "(A margin of 0 disables the ambiguity check; 0.02 is used unless it measurably hurts.)"]
        if a.detail:
            _, detail = evaluate(index, probes, best["alpha"], best["floor"], best["margin"])
            lines += ["", f"## Per-probe ({version})", "", "| action | expected | verdict | got |", "|---|---|---|---|"]
            lines += [f"| {n} | {e} | {v} | {g} |" for n, e, v, g in detail]
    Path("results").mkdir(exist_ok=True)
    out = Path("results/calibration.md")
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
