# Smart Guided Troubleshooting Engine

Turns a vague device complaint into a validated, ordered, deeplinked fix plan,
grounded in Samsung's reference text. When the evidence is weak, it says so
instead of guessing.

**Samsung PRISM GenAI Hackathon 2026 (3rd Edition), Theme 02. Team Order 66.**

**Demo video:** [watch here](https://drive.google.com/file/d/10Exkw4bSvbSFb3ADYi13eaOImpLcP60E/view?usp=sharing) · **Deck:** [submission/Thapar_Order66_Submission.pptx](submission/Thapar_Order66_Submission.pptx)

## The problem

Support systems receive complaints like *"screen flickers and the battery dies
fast"*: informal, vague, and far from the technical language of the fix.
Today an agent reads internal SIIS knowledge-base articles, diagnoses the
issue, picks and orders the steps by hand, and the customer still has to
navigate nested Settings menus themselves. That's roughly **15 minutes per
case, across millions of interactions**.

## What this does

Given a complaint and, optionally, a SIIS reference document, the engine:

1. **Checks the semantic cache.** A reworded version of an already-answered
   complaint is served in ~10 ms without calling the LLM.
2. **Checks the reference actually addresses the complaint.** If not, it
   abstains (`siis_mismatch`) before spending an LLM call.
3. **Normalizes the complaint** into a canonical query and 8–10 paraphrases
   (enrichment), *concurrently* with:
4. **Extracting** a structured, schema-valid plan from the reference text.
   A complaint with two distinct problems gets two separate plans.
5. **Repairs and checks the plan.** Spec rules are enforced in code (word
   counts, title/goal syntax, categories per spec 4.1). Steps the reference
   doesn't support are removed, and every kept step is linked to its source
   sentence.
6. **Maps each action to a catalog deeplink** by hybrid keyword + semantic
   search, and **declines to guess** when no entry is confidently right.
7. **Orders actions** safest-first (settings → physical → critical), then
   validates and caches the result.

## Results on Samsung's data

Measured on Samsung's real files: 20 queries, 20 SIIS documents, and the
578-entry catalog. Model: `nvidia/nemotron-3-super-120b-a12b` via NVIDIA's API.

| Metric (spec target) | Measured |
|---|---|
| Schema-valid output lines (≥ 99%) | **100%** |
| Rule compliance: goal / title / description (≥ 95%) | **100%** |
| Absolute URL leaks (0) | **0** |
| Real queries answered with a grounded plan | **20 / 20** |
| Human-rated step accuracy, Appendix C §2 (0–3, 49 plans, 4 domains) | **2.78** (93.9% of plans ≥ 2) |
| Human-rated deeplink relevance, Appendix C §2 (0–2, 16 plans) | **1.28**: 4 wrong screens found and analysed |
| Deeplink mapping vs full-LLM baseline (Appendix C §5) | **0 wrong vs 13**, ~37× faster, 0 tokens |
| 500 cached requests, 50 concurrent users | **500/500 hits, 0 errors, 338 req/s**, client P95 318 ms incl. HTTP |
| Wrong deeplinks on labelled probes across all catalog domains | **0** (73 correct, 26 safe abstentions) |
| All 577 catalog entries through the pipeline | 406 correct · 166 safe abstentions · 5 wrong (0.9%) · **0 opposite toggles** |
| Auto actions linked to a real catalog screen (not the placeholder) | 45.1%: the price of 0 wrong links |
| Cache hit rate on independently written paraphrases (≥ 80%) | **87.5%** (typos included) |
| Cache hit rate on generated paraphrases held out of the cache | **84.8%** (112) |
| Plan served for a different SIIS document (real model, 340 requests) | **0** |
| Cache-hit latency P95 (≤ 300 ms) | **~13 ms** |
| Same query 5× (deterministic execution) | identical actions and categories 5/5; title wording varies ("Screen flicker" / "Screen flicker fix") |
| 39 synthetic scenarios: Battery, Camera, Performance, connectivity, multi-issue, mismatches, 4 languages | **100%** correct outcome |
| Non-English complaints (Hindi, Korean, Spanish, Hinglish) | **4 / 4** answered; 0 / 55 English queries mis-detected |
| Cold-path latency (≤ 8 s P95) | P50 **~4 s**; P95 **9–19 s** across runs, driven by provider response time (target not met) |

## Architecture

```
complaint (+ optional SIIS reference)
   │
   ├─ semantic cache ── hit ──────────────────────────▶ plan in ~10 ms
   │    (paraphrase-aware, reference-aware, pre-warmable, config-fingerprinted)
   ├─ no reference and no cache hit ──────────────────▶ no_siis_context   (no LLM call)
   ├─ SIIS relevance gate ── mismatch ────────────────▶ siis_mismatch     (no LLM call)
   │
   ├─ [0] enrichment ∥ [1] extraction   (concurrent LLM calls; reasoning off)
   │        multi-issue follow-up only when the two disagree
   │
   ├─ repair & safety: over-split merge · menu-only actions folded
   │     (one action = one screen) · two-pass description correction loop ·
   │     title/goal repair · spec-4.1 critical categories · contradicting-toggle removal
   ├─ step grounding: each step checked against the reference;
   │     unsupported actions removed ──── none left ──▶ insufficient_grounding
   ├─ [2] deeplink mapping: BM25 + dense (α 0.75) on description/message/Q&A text ·
   │     intent from the leading verb ↔ catalog originalType · on/off twin collapse ·
   │     confidence floor 0.6 · ambiguity margin 0.08 · no confident match →
   │     dummy_positive (Settings screen) or manual + null (anything else)
   ├─ validation deeplinks copied verbatim from the catalog
   └─ order auto → manual → critical · Pydantic validation · [3] cache write
[4] REST API: POST /v1/troubleshoot · GET /health · latency, cache hit, tokens, cost
```

Every early exit returns a named `fallback` with a plain-language
`fallback_reason`. There are no silent empty answers.

## Differentiators

**Abstention is designed in, and measured.** Samsung asked for no answer over
a wrong one. Every stage can decline:
- the relevance gate refuses mismatched references;
- deeplink matching abstains below a calibrated confidence floor, and on
  near-ties;
- grounding removes steps the reference doesn't support.

On labelled probes spanning every catalog domain: **0 wrong deeplinks**.

**Every step is traceable.** Responses include `step_sources`, the reference
sentence behind each step. The frontend shows it under each step and flags
unsupported ones. The plan `score` is evidence-based: the model's confidence
scaled by the share of grounded steps.

**Built on Samsung's catalog rules.**
- Intent is matched to `originalType` (on / off / update / open).
- On/off twin entries are resolved, not treated as ambiguous.
- Validation deeplinks are copied verbatim.
- `dummy_positive` vs manual/null follows the catalog's own instructions and
  the spec's Appendix B example.

**Calibrated on real data, not tuned by hand.**
- Thresholds come from sweeps over labelled probes.
- A reachability check covers all 577 catalog entries.
- Growing the probe set overturned earlier choices twice: 26 → 92 probes moved
  the ambiguity margin 0.02 → 0.05, and 92 → 101 probes moved it to 0.08.

**Semantic, reference-aware cache.**
- A query is scored against every phrasing already in a cluster, so exact
  repeats and paraphrases both hit.
- Failures are never cached.
- A plan is reused only for the same reference document, and only if it was
  produced under the current settings.

**Multilingual complaints.** A complaint in Hindi, Korean, Spanish or
romanized Hinglish is detected locally and translated once to English. The
normal pipeline then runs on the translation, because Samsung's documents and
catalog are English. The response keeps the customer's original words and
reports `detected_language` and `translated_query`. English complaints skip
this entirely. Without it, a non-English complaint would be wrongly refused as
a reference mismatch.

**Repeatable engineering.** 373 offline tests that pass in any order and with
or without a `.env`. Every setting has its calibrated default in code.

## Ablation study

Samsung's Appendix C compares deeplink-mapping architectures.
`python scripts/ablation.py --llm` runs all three on the same labelled probes
(hand-written + generated across every catalog type) and writes
`results/ablation_results.md`:

| Architecture variant | Deeplink accuracy (correct / **wrong** / abstain) | Latency P95 per action | Cost / query |
|---|---|---|---|
| Baseline: full-LLM deeplink mapping (Nemotron, whole catalog in prompt) | 83 / **13** / 3 | 351 ms | ~1,873 tokens |
| **Variant A: Hybrid BM25 + dense (ours; α 0.75, floor 0.6, margin 0.08)** | **73 / 0 / 26** | **9.5 ms** | **0 (local)** |
| Variant B: pure rules-based (keyword BM25), same thresholds | 60 / **7** / 32 | 1 ms | 0 (local) |
| Variant B, best keyword-only tuning | 30 / **2** / 67 | 1 ms | 0 (local) |

99 labelled probes: 92 must link to a named catalog entry, 7 must not link at
all. `results/ablation_results.md` has the full output.

**The LLM gets 10 more right, but links 13 wrong screens.** It has no
confidence signal, so it always picks something. The hybrid links **zero** wrong
screens, at **~37× lower latency** and **no
token cost**. Keyword rules alone can't reach zero wrong links on this catalog.

Keyword rules fail because "Font size" and "Bold font" share a word, and "Enable X" and
"Disable X" differ by one. Adding semantic similarity is what removes the wrong links.

Further ablations (from `scripts/calibrate_retrieval.py` and batch runs):

| Choice | Measured effect |
|---|---|
| Ambiguity margin 0.02 → 0.05 → **0.08** | each larger probe set exposed wrong links at the smaller margin; every top configuration on 101 probes uses 0.08 |
| Search text v1 vs v2 | v1 (description + message + Q&A) 73 correct vs v2 60, both 0 wrong: **v1 kept** |
| Intent from the leading verb | opposite-toggle errors across the catalog: 3 → **0** |
| Margin 0.02 → 0.05 → 0.08 across all 577 entries | wrong links 26 → 8 → **5** (0.9%); correct 85.1% → 74.2% → 70.4% (traded for abstentions) |
| Grounding enforcement off → **on (0.5)** | synthetic 100% → 96.8%; invented actions removed |
| LLM reasoning on → **off** | cold P95 76 s → 9–19 s; far fewer malformed outputs |
| Action ordering | rule-based auto → manual → critical: **0** safety violations in every run |

## Implementation roadmap

All four phases of Samsung's roadmap are complete:
- **Phase 1:** validation harness against Samsung's `schema.py` and sample output.
- **Phase 2:** dual BM25 + dense retrieval, screen resolution and safe-first ordering.
- **Phase 3:** semantic caching, persistent pre-warmed variations and latency benchmarks.
- **Phase 4:** REST API, graceful fallbacks and a concurrency stress test.

## Tech stack

- **API**: FastAPI (async), Pydantic
- **LLM**: NVIDIA API (`nemotron-3-super-120b-a12b`, reasoning off) or any
  OpenAI-compatible endpoint, or Gemini, switched in `.env`
- **Embeddings**: sentence-transformers `all-MiniLM-L6-v2` (local, CPU)
- **Keyword retrieval**: BM25 (rank-bm25) with coverage normalization
- **Tests**: pytest (373 offline tests) · **Container**: Docker

## Setup

```bash
python -m venv venv
venv\Scripts\activate            # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env           # macOS/Linux: cp .env.example .env
```

`.env` needs only the provider and key; everything else has calibrated defaults:

```dotenv
LLM_PROVIDER=openrouter
OPENROUTER_BASE_URL=https://integrate.api.nvidia.com/v1
OPENROUTER_API_KEY=nvapi-...
OPENROUTER_MODEL=nvidia/nemotron-3-super-120b-a12b
```

## Run

```bash
uvicorn app.main:app --port 8000
```

Or with Docker (reads `.env` at container creation; `app/data` is mounted):

```bash
docker compose -f docker/docker-compose.yml up --build --force-recreate
```

Check the provider from inside the server: `curl http://localhost:8000/health`

## Try it

```bash
curl -X POST http://localhost:8000/v1/troubleshoot -H "Content-Type: application/json" \
  -d '{"query": "screen flickers and battery dies fast",
       "siis_response": {"title": "Display flicker", "content": "Open Settings, then Display, then Motion smoothness, and set it to Standard."}}'
```

- `siis_response` may be Samsung's `{title, content}` object or plain text.
- A query with no reference and no cached match returns `no_siis_context`.
- A query with an unrelated reference returns `siis_mismatch`.

Both are designed abstentions, made without any LLM call.

Other endpoints: `GET /health` (exactly `{"status":"ok"}`; 503 while starting), `GET /v1/status`
(catalog size, warm-up stats), `GET /v1/cache/stats`, `GET /v1/config`, `GET /v1/examples`.
`GET /v1/provider-check` (one live LLM call) is off unless `ENABLE_DIAGNOSTICS=true`.

## Frontend

Open `frontend/index.html` (a single file, no build step). It shows:
- one plan card per detected issue, and the **source sentence** under every
  step (unsupported steps flagged);
- a verification check for auto actions;
- grounding %, latency, tokens and cache status;
- a **picker for Samsung's 20 real queries** (numbered 1–20; Samsung's own ids skip row_6 and row_18),
  loaded with their SIIS text;
- a **Hindi example** showing the multilingual path, with a translation badge;
- a **raw JSON view**, the exact spec-format response;
- live sliders for α / confidence floor / margin, which start at the
  backend's calibrated defaults.

## Testing

```bash
pytest tests/ -v            # 373 tests: offline, no API key, any order, with or without .env
```

Coverage includes:
- schema and spec rules; URL / hallucination guards; action ordering and
  spec-4.1 categories;
- semantic cache: paraphrases, thread safety, reference-awareness, warm-up
  staleness;
- deeplink matching: intent, twins, floor and margin, coverage normalization;
- relevance gate, grounding and provenance, the description correction loop,
  multi-issue handling;
- provider error handling, the HTTP contract, and tests against Samsung's
  real files and official `schema.py`.

## Evaluation toolkit

```bash
python scripts/batch_run.py --all                  # Samsung's 20 + 39 synthetic → results.jsonl + metrics.md
python scripts/ablation.py --llm                   # Appendix C §5: full-LLM vs hybrid vs rules-based
python scripts/calibrate_retrieval.py --probes all --detail   # threshold sweep, labelled probes
python scripts/calibrate_retrieval.py --catalog    # all 577 catalog entries through the pipeline
python scripts/calibrate_retrieval.py --relevance  # SIIS relevance threshold
python scripts/measure_determinism_and_cache.py    # determinism + independent paraphrase hit rate
python scripts/stress_test.py --n 500 --concurrency 50   # concurrent load on a running server
python scripts/review_sheet.py --all               # review sheet + results/manual_scores.csv to fill in
python scripts/finalize_metrics.py                 # complete Appendix C metrics.md (scores + ablation + edge cases)
```

- `results.jsonl` follows the spec's Appendix B, and `metrics.md` its
  Appendix C template, with exact-match and paraphrase cache hits reported
  separately.
- To pre-warm the cache, copy a fresh `results.jsonl` to
  `app/data/cache_warm.jsonl`.

## Known limitations

- **Cold-path latency depends on the provider.** P50 is ~4 s, but P95 varies
  9–19 s across runs on NVIDIA's free endpoint, above the 8 s target. A 30 s
  per-call timeout now cuts off degenerate responses (one took 104 s). A repair time budget skips optional LLM
  calls once a request passes 6 s.
- **Plans are written in English.** Non-English complaints are understood
  and answered, but the plan text follows Samsung's English documents and the
  spec's English rules.
- **Latin-script language detection is heuristic.** It looks for common
  English words, so a very short non-English complaint may be treated as
  English.
- **Samsung's sample output breaks its own 5–7 word rule** (9- and 12-word
  descriptions). We follow the spec text (4.1, Appendix C) and enforce 5–7.
- **Placeholder links are common.** Of auto actions, the share with a *real*
  catalog screen (not `dummy_positive`) is reported separately in metrics §1:
  the confidence floor trades links for zero wrong screens.
- **Samsung's 20 queries are all display issues.** Battery, Camera and
  Performance coverage comes from the synthetic scenarios and generated
  probes.
- **Step grounding is lexical.** A correct step worded differently from the
  reference can be flagged; short references can cause abstention.
- **Human review still finds what automation misses.** On 49 reviewed plans:
  3 invented actions (lexical grounding fully caught 1) and 4 wrong deeplink
  screens (one, an enable/disable reversal, is now fixed in code).
- **Output carries two extra fields.** `fallback` / `fallback_reason` sit
  inside `response`; Samsung's official `schema.py` ignores extra fields, and
  output validates against it.

## Status

Complete: the full pipeline on Samsung's real data, all spec constraints
enforced in code, calibration and ablation on real data, evaluation toolkit,
frontend, Docker, multilingual input, a concurrency stress test, and 373 tests. Done: human review of 49 plans.

## Submission

The judged version is the commit tagged **`PRISM_GENAI_HACKATHON_Y2026`**.

## License

MIT
