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
from app.core.llm_client import generate_json, generate_json_async, TokenUsage

EXTRACTION_PROMPT = """You are extracting a structured troubleshooting plan \
from reference support text. Follow the schema EXACTLY.

Complaint: "{complaint}"
Reference text: "{reference}"

MULTI-ISSUE HANDLING: "contexts" is a list and MAY contain more than one \
entry, but only for genuinely DISTINCT issues with different root causes \
and different fixes in the reference text — not for one issue that happens \
to produce multiple symptoms. Test: if fixing the first context's actions \
would ALSO resolve the second symptom, it's one issue, not two. Example: \
"screen flickers and the battery dies fast" is normally ONE context — a \
single display/refresh-rate setting commonly causes both symptoms together \
(check whether the reference text describes them as one root cause before \
splitting). Only split when the reference text itself describes separate, \
independent causes (e.g. a display bug AND an unrelated storage-full \
warning in the same complaint). Return AT MOST 2 contexts even if you \
perceive more than 2 distinct issues — merge the least distinct pair \
rather than fragmenting further; over-splitting one issue into several is \
a worse failure than under-splitting two into one.

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
- Do NOT invent deeplinks here - leave actionableDeeplink/validationDeeplink \
  absent, they are resolved in a later stage
- OPTIONAL: for an "auto" action with an obvious, checkable resulting state \
  (a toggle, a mode, a numeric setting), include "expectedOutcome": \
  {{"key": "<short snake_case name of the setting>", \
    "resultType": "boolean"|"integer"|"str"|"float", \
    "condition": "equal"|"greater"|"less", "value": "<expected value as a string>"}}. \
  This describes what SUCCESS looks like after the action, for later \
  verification — omit it entirely if there's no clear checkable outcome \
  (most "manual"/"critical" actions won't have one).
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
          "stepGroups": [{{"steps": ["...", "..."]}}],
          "expectedOutcome": {{"key": "...", "resultType": "str", "condition": "equal", "value": "..."}}
        }}
      ]
    }}
  ]
}}
Remember: "contexts" holds ONE entry per DISTINCT issue per the test above \
-- add a second object to the array, same shape, only when genuinely \
warranted. Do not add a second entry for a single issue with multiple \
symptoms."""


def extract_structure(complaint: str, reference: str = "") -> tuple[dict, TokenUsage]:
    prompt = EXTRACTION_PROMPT.format(complaint=complaint, reference=reference)
    # 3200, up from 2200: a genuine 2-issue response is roughly double the
    # size of a 1-issue one (full second goal/actions/stepGroups block).
    # This is the same lesson as an earlier truncation bug this session --
    # adding output-size-increasing prompt content without raising the
    # token budget to match produces truncated, unparseable JSON.
    return generate_json(prompt, max_output_tokens=3200)


async def extract_structure_async(complaint: str, reference: str = "") -> tuple[dict, TokenUsage]:
    """Async variant — identical prompt and contract to extract_structure()."""
    prompt = EXTRACTION_PROMPT.format(complaint=complaint, reference=reference)
    return await generate_json_async(prompt, max_output_tokens=3200)
