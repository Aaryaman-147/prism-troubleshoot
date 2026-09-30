"""
Stage 0: Query Enrichment.
Normalizes a colloquial complaint into a canonical technical query,
generates paraphrases for cache-key robustness, and detects whether the
complaint actually describes MULTIPLE distinct issues (e.g. "screen
flickers and battery dies fast" — two separate problems in one sentence).

Multi-issue detection folds into this stage rather than a separate one
because it's a cheap, single classification decision that can piggyback
on a call already being made concurrently with extraction — adding a
whole new sequential LLM call just for this would cost real latency for
comparatively little work.
"""
from app.core.config import settings
from app.core.llm_client import generate_json, generate_json_async, TokenUsage

ENRICHMENT_PROMPT_TEMPLATE = """You normalize vague customer device complaints into \
a canonical technical query, generate paraphrases, and detect whether the
complaint actually describes multiple DISTINCT issues rather than one.

Complaint: "{complaint}"

A complaint is multi-issue only if it names two or more problems with
DIFFERENT root causes that need DIFFERENT fixes (e.g. "screen flickers
AND storage is full" — a display fault and a storage problem). Symptoms
that commonly share one cause are ONE issue: "screen flickers and the
battery dies fast" is usually a single display/refresh-rate problem. Do
NOT split a single issue described with extra detail (e.g. "screen
flickers when I open the camera app" is ONE issue, not two).
When genuinely unsure, prefer is_multi_issue: false — over-splitting a
simple complaint into fake sub-issues is worse than treating a
borderline case as one.

Return ONLY valid JSON, no markdown fences, no preamble:
{{
  "canonical_query": "<normalized technical description, 3-8 words>",
  "query_variations": ["<paraphrase 1>", "<paraphrase 2>", ... {count} total,
                        varying register: formal, casual, keyword-only, \
                        frustrated, typo-inclusive],
  "is_multi_issue": <true or false>,
  "sub_issues": [<list of 2+ short issue descriptions ONLY if is_multi_issue
                  is true, e.g. ["screen flickering", "battery draining fast"]
                  — otherwise an empty list>]
}}"""


def _build_prompt(complaint: str, count: int) -> str:
    return ENRICHMENT_PROMPT_TEMPLATE.format(complaint=complaint, count=count)


def enrich_query(complaint: str, paraphrase_count: int | None = None) -> tuple[dict, TokenUsage]:
    count = settings.ENRICHMENT_PARAPHRASE_COUNT if paraphrase_count is None else paraphrase_count
    return generate_json(_build_prompt(complaint, count), max_output_tokens=1300, required_keys=("canonical_query",))


async def enrich_query_async(complaint: str, paraphrase_count: int | None = None) -> tuple[dict, TokenUsage]:
    """Async variant — identical prompt and contract to enrich_query()."""
    count = settings.ENRICHMENT_PARAPHRASE_COUNT if paraphrase_count is None else paraphrase_count
    return await generate_json_async(_build_prompt(complaint, count), max_output_tokens=1300, required_keys=("canonical_query",))
