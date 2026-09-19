"""
Stage 1: Structure Extraction.
Parses the complaint + optional siis_response reference text into a
structured Goal object via LLM, following the exact schema contract.
Output is NOT trusted as-is — main.py runs it through Pydantic validation
and the programmatic checks in utils/validators.py before it ever reaches
the cache or the response.

IMPORTANT: this stage needs REFERENCE TEXT to extract from (siis_response).
Without it, there's no source material for a grounded troubleshooting plan,
and per the spec's own "No Hallucinated Steps" rule, the correct behavior
IS to return no_match rather than invent steps from the LLM's own
pretraining. If you're testing with only `query` and no `siis_response`,
you WILL get no_match — that's correct behavior, not a bug. Once you have
the real siis_responses.json (post-registration), pass the matching entry
in as siis_response.
"""
from app.core.llm_client import generate_json, generate_json_async

EXTRACTION_PROMPT = """You are extracting a structured troubleshooting plan \
from reference support text. Follow the schema EXACTLY.

Complaint: "{complaint}"
Reference text: "{reference}"

Rules (violating any of these will cause the output to be rejected):
- goal: exact syntax "Follow these steps to perform this <Topic> Troubleshooting" \
  (or "...Configuration")
- title: sentence case, 2-3 words identifying the core issue
- score: float 0.0-1.0, your confidence this plan resolves the complaint
- actionName: Title Case, one physical screen/feature per action
- description: MUST be EXACTLY 5, 6, or 7 words (count carefully before \
  responding), MUST start with the exact text "It will", explains the \
  concrete benefit in plain language
- stepGroups[].steps: imperative UI steps, one physical interaction per step, \
  NO urls or links
- category: "auto" (safe, reachable via deeplink), "manual" (physical action, \
  no deeplink), or "critical" (destructive/irreversible - order these last)
- Do NOT invent deeplinks here - leave actionableDeeplink absent, it is \
  resolved in a later stage
- If the reference text is EMPTY or has no viable solution, return \
  {{"contexts": [], "fallback": "no_match"}} — do NOT invent a plan from \
  general knowledge when no reference text is given

Return ONLY valid JSON matching this shape, no markdown fences, no preamble:
{{
  "contexts": [
    {{
      "goal": "...",
      "title": "...",
      "score": 0.0,
      "actions": [
        {{
          "actionName": "...",
          "description": "It will ...",
          "category": "auto",
          "stepGroups": [{{"steps": ["...", "..."]}}]
        }}
      ]
    }}
  ]
}}"""


def extract_structure(complaint: str, reference: str = "") -> dict:
    prompt = EXTRACTION_PROMPT.format(complaint=complaint, reference=reference)
    return generate_json(prompt, max_output_tokens=2500)


async def extract_structure_async(complaint: str, reference: str = "") -> dict:
    """Async variant — identical prompt and contract to extract_structure()."""
    prompt = EXTRACTION_PROMPT.format(complaint=complaint, reference=reference)
    return await generate_json_async(prompt, max_output_tokens=2500)
