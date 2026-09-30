# System Performance Metrics & Evaluation Report
**Model(s):** openrouter/nvidia/nemotron-3-super-120b-a12b
**Embeddings:** all-MiniLM-L6-v2
**Environment:** 16 vCPU / 16.4 GB RAM / Windows 11
**Data:** 59 cases; catalog app/data/deeplinks.json (578 entries)

---

## 1. Schema & Rule Compliance
Evaluated on 59 cases (60 generated goals).

| Metric | Target | Measured Value |
| :--- | :--- | :--- |
| Schema-valid output lines | >= 99% | 100.0% |
| Rule compliance (Goal / Title / Description syntax) | >= 95% | 100.0% |
| Absolute URL leaks | 0 | 0 |
| Deeplink catalog validity (exact URI match) | 100% | 100.0% |
| Auto actions carrying valid actionable deeplink | >= 90% | 100.0% |
| &nbsp;&nbsp;of which a real catalog screen (not the `dummy_positive` placeholder) | reported | 45.1% |
| Manual actions carrying a deeplink (should be 0) | 0 | 0 |
| Critical-before-safe ordering violations | 0 | 0 |
| Generated steps supported by the SIIS text (lexical grounding) | high | 96.1% |
| query_variations within 8-10 | 100% | 100.0% |

---

## 2. Accuracy Benchmarks
Evaluated against reference ground truth across Battery, Display, Camera, and Performance (Samsung's 20 queries + labelled synthetic scenarios); step and deeplink scores are human-rated with REVIEW_GUIDE.md.

| Evaluation Metric | Scale / Anchor | Score |
| :--- | :--- | :--- |
| Outcome matches expected (plan / multi / abstain) | % of labelled cases | 100.0% (35 judged; 0 provider/quota failures excluded) |
| Step accuracy (completeness, correctness, ordering) | 0.0 - 3.0 | **2.78** (n = 49 plans) |
| Deeplink relevance (exact target screen vs. parent menu) | 0.0 - 2.0 | **1.28** (n = 16 scored actions) |
| &nbsp;&nbsp;Step accuracy: Battery | 0.0 - 3.0 | 2.71 (n = 7) |
| &nbsp;&nbsp;Step accuracy: Camera | 0.0 - 3.0 | 3.00 (n = 2) |
| &nbsp;&nbsp;Step accuracy: Display | 0.0 - 3.0 | 2.67 (n = 21) |
| &nbsp;&nbsp;Step accuracy: Other | 0.0 - 3.0 | 3.00 (n = 14) |
| &nbsp;&nbsp;Step accuracy: Performance | 0.0 - 3.0 | 2.60 (n = 5) |

Reviewer notes on plans below full marks:

* **1** (Display): steps 2/3, deeplink n/a. Reference mismatch (complaint is Gmail blank screen, reference is email server). Plan follows the supplied reference; a few navigation steps are only loosely sourced.
* **3** (Display): steps 1/3, deeplink n/a. Invented recovery actions: Enter Google Account and Access Recovery Menu are not supported by the reference; core charge/USB/force-restart steps are useful.
* **5** (Display): steps 2/3, deeplink n/a. Mostly grounded Data Transfer flow; device-positioning detail is only partially supported.
* **8** (Display): steps 2/3, deeplink n/a. Core USB/HDMI/service guidance is grounded; backup procedure adds a small unsupported detail.
* **9** (Display): steps 2/3, deeplink n/a. Reference mismatch (camera flicker article vs fold-screen complaint). Plan follows reference; lighting/settings navigation includes minor unsupported details. Placeholder deeplink is n/a.
* **18** (Display): steps 2/3, deeplink 1. Reference mismatch (distorted-screen complaint paired with rotation article). Plan follows reference; one software-update substep is unsupported. Orientation deeplink is related but not the exact Auto rotate control.
* **19** (Performance): steps 1/3, deeplink 0. Touch Sensitivity action contradicts its cited reference: the reference says disable it, while the plan enables it. Deeplink performs the same opposite toggle; remaining steps are useful.
* **S1-03** (Other): steps 3/3, deeplink 1. Fingerprint flow is grounded. Deeplink opens Fingerprint unlock area, but removal still requires navigation/action within that screen.
* **S1-05** (Other): steps 3/3, deeplink 0. Steps correctly follow keyboard language settings, but the auto deeplink says View Magnification Settings, which is the wrong screen.
* **S1-06** (Battery): steps 1/3, deeplink n/a. Reset-camera steps are grounded, but Clean Lens is an invented action: its only step has no matching reference sentence.
* **S2-18** (Other): steps 3/3, deeplink 0. Steps correctly use SIM manager and reseat SIM, but deeplink Enable SIM manager does not correspond to turning on both individual SIM cards.
* **S2-19** (Other): steps 3/3, deeplink 1.5. NFC/payment-app steps are grounded. NFC deeplink enables NFC rather than merely opening the requested screen (partial); Default wallet app deeplink is exact.
* **S3-21** (Camera): steps 3/3, deeplink 0. Both issue plans are grounded. Bluetooth link is placeholder; Camera access deeplink is the wrong screen for the Apps > Camera > Storage/cache path.
* **S3-24** (Other): steps 3/3, deeplink 1. Both Wi-Fi and fingerprint plans are grounded. Wi-Fi link is placeholder; Fingerprint unlock is the right area but not the exact re-register action.

Fallback distribution: {'siis_mismatch': 3}

---

## 3. Latency Benchmarks (spec asks N >= 30 per path; use `batch_run.py --all` for enough cold queries)

| Execution Path | Target (P95) | P50 (ms) | P95 (ms) | N |
| :--- | :--- | :--- | :--- | :--- |
| Cache hit - exact query match | <= 300 ms | 0.1 | 0.3 | 56 |
| Cache hit - unseen semantic paraphrase (held out of cache) | <= 300 ms | 10.9 | 15.2 | 95 |
| Cold query - full pipeline | <= 8000 ms | 4673.5 | 11460.1 | 55 |
| Early abstention (no LLM call) | - | 21.8 | - | 3 |

---

## 4. Operational Cost & Cache Efficacy

| Metric Item | Target | Measured Value |
| :--- | :--- | :--- |
| Cold query average tokens (prompt + completion) | Tracked | 2116.7 |
| Cold query average inference cost | Tracked | $0.000000 (rate from LLM_PRICE_PER_MTOK_*; 0 = free tier) |
| Cache hit inference cost | $0.00 | $0.00 |
| Semantic cache hit rate - held-out generated paraphrases (never stored) | >= 80% | 84.8% (112 paraphrases) |
| Semantic cache hit rate - independently written paraphrases | >= 80% | **87.5%** (7/8) |
| Cost derivation method | - | (prompt tokens + completion tokens) x rate |

Note: held-out paraphrases are model-generated rewordings that were deliberately
NOT stored in the cache, so every hit is a genuine semantic match. The
independently written paraphrase test (scripts/measure_determinism_and_cache.py)
is the stricter measure: human-style wording, typos included.

---

## 5. Architectural Ablation Analysis
| Architecture Variant | Step Accuracy | Deeplink accuracy (correct / wrong / abstain) | Latency (P95) | Cost / Query | Key Observations |
|---|---|---|---|---|---|
| Baseline: Full LLM Deeplink Mapping (nvidia/nemotron-3-super-120b-a12b) | same for all variants (see section 2) | 83 / 13 / 3 | 351.2 ms | ~1873 tokens | whole catalog in the prompt; no confidence signal, so it cannot abstain on weak matches |
| Variant A: Hybrid BM25 + Dense (alpha 0.75, floor 0.6, margin 0.08) — ours | same for all variants (see section 2) | 73 / 0 / 26 | 9.48 ms | 0 (local) | calibrated to 0 wrong; abstains when unsure |
| Variant B: Pure Rules-Based (BM25 keywords only, same thresholds) | same for all variants (see section 2) | 60 / 7 / 32 | 0.98 ms | 0 (local) | literal word overlap; confuses e.g. 'Font size' with 'Bold font' |
| Variant B tuned (best keyword-only config: floor 0.8, margin 0.08) | same for all variants (see section 2) | 30 / 2 / 67 | 0.93 ms | 0 (local) | its best achievable trade-off |


---

## 6. Known Edge Cases & System Limitations
* **Multi-intent:** at most 2 plans per complaint. A third distinct issue in one message (e.g. Samsung row 17's three numbered complaints) is merged into the closest plan; over-split single issues are merged back automatically.
* **Domain gaps:** Samsung's 20 real queries are all Display. Battery, Camera and Performance coverage comes from the synthetic scenarios and generated probes, not from Samsung ground truth.
* **Reference/complaint mismatch in the data:** e.g. a Gmail blank-screen complaint paired with an 'Email server not responding' document. Plans follow the supplied reference.
* **Settings hierarchy variations:** screens absent from the catalog get `dummy_positive`; catalog duplicates and parent/child pages (e.g. 'View Security Settings' vs 'View More security settings') account for the remaining whole-catalog mismatches (8/577, 0 opposite toggles).
* **Category boundaries:** 'restart', 'safe mode', 'factory reset' and 'firmware update' are forced to critical; configuring a restart *schedule* stays auto.
* **Grounding is lexical:** a correct step worded differently from the reference can be flagged; a very short reference can yield `insufficient_grounding`.
* **Non-English complaints:** translated to English first; plans are returned in English.
* **Cold-path latency:** dominated by provider response time (P95 11460.1 ms this run); a 6 s repair budget skips optional LLM repair calls.
* **Fallbacks this run:** {'siis_mismatch': 3}.
