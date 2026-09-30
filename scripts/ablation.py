"""
Architectural ablation on Samsung's real catalog, in the spec's Appendix C
section 5 format (replaces the placeholder-era script).

  python scripts/ablation.py          # Variant A (hybrid) vs Variant B (rules-based): offline, no LLM calls
  python scripts/ablation.py --llm    # + Baseline: full-LLM deeplink mapping (~10 LLM calls)

Writes results/ablation_results.md. Needs the real embedding model (run on your machine).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.config import settings
from app.core.llm_client import generate_json
from app.eval.ablation import llm_mapping, render, timed_retrieval
from app.eval.calibrate import load_probes, sweep
from app.pipeline.deeplink_retrieval import DeeplinkIndex


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--llm", action="store_true"); a = ap.parse_args()
    probes = load_probes("app/data/retrieval_eval_real.json")
    gen = Path("app/data/retrieval_eval_generated.json")
    if gen.exists():
        probes += load_probes(gen)
    n_pos = sum(p["expected_message"] is not None for p in probes)
    index = DeeplinkIndex(settings.DEEPLINKS_PATH)
    cfg = (settings.DEEPLINK_ALPHA, settings.DEEPLINK_MIN_CONFIDENCE, settings.DEEPLINK_MARGIN)
    print("Variant A (hybrid)...")
    va = timed_retrieval(index, probes, *cfg)
    print("Variant B (keyword-only)...")
    vb = timed_retrieval(index, probes, 0.0, cfg[1], cfg[2])
    best = sweep(index, probes, alphas=(0.0,))[0]
    vb_best = timed_retrieval(index, probes, 0.0, best["floor"], best["margin"])
    vb_best.update(floor=best["floor"], margin=best["margin"])
    base = None
    if a.llm:
        print("Baseline (full-LLM mapping)...")
        catalog = json.loads(Path(settings.DEEPLINKS_PATH).read_text(encoding="utf-8"))["deeplinks"]
        base = llm_mapping(probes, catalog, generate_json)
    model = settings.OPENROUTER_MODEL if settings.LLM_PROVIDER == "openrouter" else settings.LLM_MODEL
    md = render(len(probes), n_pos, va, vb, vb_best, base, cfg, model)
    Path("results").mkdir(exist_ok=True)
    Path("results/ablation_results.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
