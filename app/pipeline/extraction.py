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

MULTI-ISSUE HANDLING: "contexts" holds ONE entry per distinct PROBLEM THE \
USER REPORTED -- never one per possible cause or per fix. If the reference \
text lists several possible causes or fixes for a single reported problem \
(e.g. "clean the lens" AND "reset camera settings" for blurry photos), \
those are several ACTIONS inside ONE context. Use a second context only \
when the user reported two different problems (e.g. "screen flickers AND \
storage is full"), and only if the reference text covers both. At most 2 \
contexts. Over-splitting one problem is a worse failure than merging two.

Rules (violating any of these will cause the output to be rejected):
- goal: exact syntax "Follow these steps to perform this <Topic> Troubleshooting" \
  (or "...Configuration")
- title: sentence case, 2-3 words identifying the core issue
- score: float 0.0-1.0, your confidence this plan resolves the complaint
- actionName: Title Case, one physical screen/feature per action
- description: MUST be EXACTLY 5, 6, or 7 words (count carefully before \
  responding), MUST start with the exact text "It will", explains the \
  concrete benefit in plain language. Right: "It will identify any physical \
  damage" (7). Wrong: "It will identify damage" (4, too short). The part \
  AFTER "It will" must be 3 to 5 words
- Every action must contain its COMPLETE path of steps (e.g. "Open Settings.", \
  "Tap Display.", "Tap Navigation bar.", "Select Swipe gestures."). Never create \
  an action that only opens a menu -- navigation belongs inside the action \
  that uses it
- stepGroups[].steps: imperative UI steps, one physical interaction per step, \
  NO urls or links
- category (Samsung's definitions): "auto" = a standard Settings screen \
  reachable via deeplink; "manual" = a physical intervention (cleaning ports, \
  replacing hardware, visiting a service center); "critical" = a disruptive \
  or irreversible operation, e.g. factory reset, RESTART, firmware/software \
  update, SAFE MODE -- always ordered last
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
Remember: one context per reported problem; multiple causes/fixes of the \
same problem are multiple actions in that one context."""


SUB_ISSUES_HINT_TEMPLATE = """

ADDITIONAL CONTEXT: a separate analysis identified {n} distinct problems in \
this complaint: {issues}. Produce ONE context per listed problem, using only \
the parts of the reference text relevant to each. If the reference text does \
not cover one of them, omit that context rather than inventing steps."""


def _build_prompt(complaint: str, reference: str, sub_issues: list[str] | None = None) -> str:
    prompt = EXTRACTION_PROMPT.format(complaint=complaint, reference=reference)
    if sub_issues and len(sub_issues) >= 2:
        prompt += SUB_ISSUES_HINT_TEMPLATE.format(
            n=len(sub_issues), issues=", ".join(f'"{i}"' for i in sub_issues))
    return prompt


def _max_tokens(sub_issues) -> int:
    return 3200 if not sub_issues else 3200 + 1200 * max(0, len(sub_issues) - 2)


def extract_structure(complaint: str, reference: str = "",
                      sub_issues: list[str] | None = None) -> tuple[dict, TokenUsage]:
    return generate_json(_build_prompt(complaint, reference, sub_issues),
                         max_output_tokens=_max_tokens(sub_issues), required_keys=("contexts",))


async def extract_structure_async(complaint: str, reference: str = "",
                                  sub_issues: list[str] | None = None) -> tuple[dict, TokenUsage]:
    """Async variant. `sub_issues` is passed by the orchestrator's multi-issue
    follow-up; a version of this file without the parameter crashed that path
    with a TypeError the mocked unit tests could not see."""
    return await generate_json_async(_build_prompt(complaint, reference, sub_issues),
                                     max_output_tokens=_max_tokens(sub_issues), required_keys=("contexts",))
