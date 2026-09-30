"""
Manual review helper. After a batch run:
  python scripts\\review_sheet.py              # 5 plans from results/results.jsonl
  python scripts\\review_sheet.py --all
Writes results/review.md: each plan beside its SIIS reference, with the source
sentence under every step and blanks to score. No LLM calls.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.config import settings
from app.eval.review import build_sheet, load_references


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--all", action="store_true"); a = ap.parse_args()
    refs = load_references(settings.SIIS_RESPONSES_PATH, Path(__file__).parent / "synthetic_scenarios.json")
    out = Path("results/review.md")
    out.write_text(build_sheet("results/results.jsonl", refs, None if a.all else 5), encoding="utf-8")
    from app.eval.review import scores_template
    scores = Path("results/manual_scores.csv")
    if scores.exists():
        print(f"Kept existing {scores} (delete it to regenerate the blank template).")
    else:
        scores.write_text(scores_template("results/results.jsonl", None if a.all else 5), encoding="utf-8")
        print(f"Wrote {scores}: fill steps_0_3 and deeplink_0_2_or_na (use n/a for plans with no auto action).")
    print(f"Wrote {out}. Open it, score each plan, copy totals into TESTING.md.")


if __name__ == "__main__":
    main()
