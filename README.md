# Smart Guided Troubleshooting Engine

Transforms vague, natural-language device complaints into validated,
deeplinked, one-tap troubleshooting plans — with a semantic cache that
serves paraphrased repeat queries in under 300ms.

Built for the **Samsung PRISM GenAI Hackathon 2026 (3rd Edition)** — Theme 02.

## The problem

Support systems receive complaints like *"screen flickers and the battery
dies fast"* — vague, informal, and far from the technical language needed
to look up a fix. Today, a human agent reads internal documentation,
diagnoses the issue, and manually writes out ordered steps — roughly
15 minutes per case, across millions of interactions.

## What this does

Given a complaint (and optionally a reference document), the engine:
1. Checks the semantic cache — a paraphrase of an already-answered
   complaint is served without touching the LLM
2. Normalizes the complaint into a canonical technical query and generates
   paraphrases (enrichment) *concurrently* with:
3. Extracting a structured, schema-validated troubleshooting plan via LLM
   (extraction)
4. Maps each step to a real in-app deeplink using hybrid (BM25 + dense
   embedding) retrieval — and **declines to guess** when no catalog entry is
   confidently correct, rather than attaching a plausible-looking wrong one
5. Orders actions safest-first, destructive/critical actions last
6. Caches the result — semantically, not by exact string match — so future
   paraphrases of the same issue are served instantly instead of re-running
   the full pipeline

## Architecture

```
Complaint ──▶ [Cache Check] ──HIT──▶ return in <300ms
                    │ MISS
                    ▼
             Query Enrichment (normalize + paraphrase)
                    ▼
             Structure Extraction (LLM → Goal/Action/StepGroup)
                    ▼
             Deeplink Mapping (hybrid BM25 + dense retrieval)
                    ▼
             Action Ordering (auto → manual → critical)
                    ▼
             Validation (Pydantic schema + URL-leak scrubbing)
                    ▼
             Cache Write (semantic cluster) + Response
```

## Differentiator: semantic cache clustering

Most naive caching relies on exact-string keys, which miss on paraphrased
repeat queries and either tank the hit rate or fragment into near-duplicate
entries. This cache instead clusters queries by embedding similarity, with
each cluster's centroid updated as a running mean as new paraphrases are
absorbed — avoiding fragmentation while keeping every cache hit
semantically grounded.

## Tech stack

- **API**: FastAPI
- **Validation**: Pydantic
- **Embeddings**: sentence-transformers
- **Sparse retrieval**: BM25 (rank-bm25)
- **LLM**: configurable — Gemini or any OpenAI-compatible endpoint (e.g. OpenRouter)

## Setup

```bash
python3 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # fill in your API key(s)
```

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

Or via Docker:
```bash
docker compose -f docker/docker-compose.yml up --build
```

## Try it

```bash
curl -X POST http://localhost:8000/v1/troubleshoot \
  -H "Content-Type: application/json" \
  -d '{"query": "screen flickers and battery dies fast", "siis_response": "<reference text>"}'
```

## Status

🚧 Actively in development for the hackathon submission.
Core pipeline, schema validation, hybrid retrieval, and semantic caching
are implemented and tested. Real competition dataset integration, ablation
study, and frontend are in progress.

## License

MIT
