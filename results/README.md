# results/

Evaluation artifacts for the PRISM 2026 Theme-2 submission.

| File | What | Source |
|---|---|---|
| `ablation_results.md` | Appendix C §5: full-LLM vs hybrid vs keyword rules | `scripts/ablation.py --llm` |
| `calibration.md` | deeplink threshold sweep, 99 probes | `scripts/calibrate_retrieval.py --probes all` |
| `catalog_check.md` | all 577 catalog entries through the pipeline | `scripts/calibrate_retrieval.py --catalog` |
| `cache_calibration.md` | cache false-hit risk by threshold | `scripts/calibrate_retrieval.py --cache` |
| `independent_paraphrase.json` | 8 independently written paraphrases: 7 hit | `scripts/measure_determinism_and_cache.py` |
| `determinism.md` | same query 5x | same script |
| `manual_scores.csv`, `review.md` | human review of 49 plans (Appendix C §2) | `scripts/review_sheet.py` + team scoring |

| `metrics.md` | Appendix C report, all six sections (final run) | `scripts/finalize_metrics.py` |
| `verify_report.txt` | real-model cache check: 0 wrong-document plans in 340 requests, own-document 20/20 | `scripts/verify_cache_real_model.py` |

Also copy in `results.jsonl` and `metrics.json` from your final run (not included here).
