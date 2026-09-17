"""
Stage 0: Query Enrichment.
Normalizes a colloquial complaint into a canonical technical query, and
generates paraphrases for cache-key robustness and query_variations output.
"""
from app.core.llm_client import generate_json

ENRICHMENT_PROMPT = """You normalize vague customer device complaints into \
a canonical technical query, and generate paraphrases.

Complaint: "{complaint}"

Return ONLY valid JSON, no markdown fences, no preamble:
{{
  "canonical_query": "<normalized technical description, 3-8 words>",
  "query_variations": ["<paraphrase 1>", "<paraphrase 2>", ... 5 total,
                        varying register: formal, casual, keyword-only, \
                        frustrated, typo-inclusive]
}}"""


def enrich_query(complaint: str) -> dict:
    return generate_json(ENRICHMENT_PROMPT.format(complaint=complaint), max_output_tokens=800)
