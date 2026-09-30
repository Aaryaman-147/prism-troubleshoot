# Architectural Ablation Analysis (Samsung Appendix C, section 5)

Real catalog, 99 labelled probes (92 must link to a named entry, 7 must not link). Same probes and verdicts for every variant.
Deeplink accuracy = correct / **WRONG** / abstain. Latency = P95 per action. Step accuracy is identical across variants (only deeplink mapping changes); it comes from the manual review.

| Architecture Variant | Step Accuracy | Deeplink accuracy (correct / wrong / abstain) | Latency (P95) | Cost / Query | Key Observations |
|---|---|---|---|---|---|
| Baseline: Full LLM Deeplink Mapping (nvidia/nemotron-3-super-120b-a12b) | same for all variants (see section 2) | 83 / 13 / 3 | 351.2 ms | ~1873 tokens | whole catalog in the prompt; no confidence signal, so it cannot abstain on weak matches |
| Variant A: Hybrid BM25 + Dense (alpha 0.75, floor 0.6, margin 0.08) — ours | same for all variants (see section 2) | 73 / 0 / 26 | 9.48 ms | 0 (local) | calibrated to 0 wrong; abstains when unsure |
| Variant B: Pure Rules-Based (BM25 keywords only, same thresholds) | same for all variants (see section 2) | 60 / 7 / 32 | 0.98 ms | 0 (local) | literal word overlap; confuses e.g. 'Font size' with 'Bold font' |
| Variant B tuned (best keyword-only config: floor 0.8, margin 0.08) | same for all variants (see section 2) | 30 / 2 / 67 | 0.93 ms | 0 (local) | its best achievable trade-off |
