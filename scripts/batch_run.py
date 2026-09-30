"""
Batch evaluation CLI. Writes results/results.jsonl (Appendix B, one record per
line) and results/metrics.md (Appendix C). Makes real LLM calls.

  python scripts/batch_run.py --check                  # reality-check Samsung files, no LLM calls
  python scripts/batch_run.py --synthetic              # our 35 synthetic scenarios
  python scripts/batch_run.py                          # Samsung data (queries.json + siis_responses.json)
  python scripts/batch_run.py --synthetic --limit 5    # quick smoke run
Options: --delay SECONDS between cold calls (default 4), --no-paraphrase-pass, --out DIR

Restart nothing: this runs the pipeline in-process with a fresh cache.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.eval.batch import load_cases, run_batch, shape_check

SCENARIOS = Path(__file__).resolve().parent / "synthetic_scenarios.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--all", action="store_true", help="Samsung's 20 + the 35 synthetic scenarios in one run (cold N >= 30)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--delay", type=float, default=4.0)
    ap.add_argument("--no-paraphrase-pass", action="store_true")
    ap.add_argument("--out", default="results")
    a = ap.parse_args()

    if a.check:
        for line in shape_check(settings.DEEPLINKS_PATH, settings.QUERIES_PATH, settings.SIIS_RESPONSES_PATH):
            print(line)
        return

    samsung = load_cases(queries_path=settings.QUERIES_PATH, siis_path=settings.SIIS_RESPONSES_PATH)
    synthetic = load_cases(scenarios_path=SCENARIOS)
    cases = synthetic if a.synthetic else (samsung + synthetic if a.all else samsung)
    missing = [c["id"] for c in samsung if not c.get("siis_response")]
    if missing and not a.synthetic:
        print(f"WARNING: {len(missing)} Samsung queries have no SIIS reference attached: {missing}")
    if not cases:
        sys.exit("No cases found. For Samsung data, place queries.json / siis_responses.json in app/data/.")
    # Preflight: one tiny request. A rejected key used to run every case into
    # extraction_error and still write "100% schema-valid" metrics.
    from app.core.llm_client import generate_json
    try:
        generate_json('Return ONLY {"ok": true}', max_output_tokens=50, max_retries=0)
    except Exception as e:
        sys.exit(f"Provider preflight failed ({type(e).__name__}: {str(e)[:200]}).\n"
                 f"Run: python scripts\\check_provider.py")
    m = asyncio.run(run_batch(cases, a.out, delay_s=a.delay,
                              paraphrase_pass=not a.no_paraphrase_pass, limit=a.limit))
    print(f"\nWrote {a.out}/results.jsonl and {a.out}/metrics.md")
    for k in ("schema_valid_pct", "rule_compliance_pct", "url_leaks", "auto_with_deeplink_pct", "auto_with_real_deeplink_pct",
              "expected_correct_pct", "paraphrase_hit_rate_pct", "cold_p95", "hit_p95"):
        print(f"  {k}: {m[k]}")


if __name__ == "__main__":
    main()
