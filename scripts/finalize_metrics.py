"""
Assemble the complete Appendix C report (results/metrics.md) from:
  results/metrics.json          <- python scripts/batch_run.py --all
  results/manual_scores.csv     <- python scripts/review_sheet.py --all, then fill it in
  results/ablation_results.md   <- python scripts/ablation.py --llm

  python scripts/finalize_metrics.py
Any missing input is reported as pending rather than invented.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.eval.batch import render_metrics_md
from app.eval.review import load_scores

R = Path("results")


def main():
    mj = R / "metrics.json"
    if not mj.exists():
        sys.exit("No results/metrics.json: run python scripts/batch_run.py --all first.")
    m = json.loads(mj.read_text(encoding="utf-8"))
    h = m.pop("_header", {})
    review = load_scores(R / "manual_scores.csv") if (R / "manual_scores.csv").exists() else None
    if (R / "independent_paraphrase.json").exists():
        m["independent_paraphrase"] = json.loads((R / "independent_paraphrase.json").read_text(encoding="utf-8"))
    abl = None
    if (R / "ablation_results.md").exists():
        text = (R / "ablation_results.md").read_text(encoding="utf-8")
        abl = text[text.index("|"):] if "|" in text else text
    md = render_metrics_md(m, h.get("model", "?"), h.get("embeddings", "?"), h.get("environment", "?"),
                           h.get("data", "?"), review=review, ablation_md=abl)
    (R / "metrics.md").write_text(md, encoding="utf-8")
    print(md)
    print("\nWrote results/metrics.md" + ("" if review and review["n"] else "  (section 2 pending: fill results/manual_scores.csv)")
          + ("" if abl else "  (section 5 pending: run scripts/ablation.py --llm)"))


if __name__ == "__main__":
    main()
