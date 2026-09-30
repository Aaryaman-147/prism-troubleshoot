"""
Generate labelled retrieval probes from the real catalog. For a stratified
sample of catalog entries, the LLM writes the kind of troubleshooting
ACTION (name + steps) that would need that exact setting, in natural
support-agent wording -- NOT the catalog's own message. The label is the
source entry, so every probe comes with a known correct answer.

This widens the 26 hand-written probes (mostly display) to every domain in
the catalog, without anyone hand-labelling hundreds of cases.
"""
import json
import random
from collections import defaultdict

PROMPT = """You are writing test cases for a device-settings retrieval system.
For EACH setting below, write ONE troubleshooting action that a support agent
would give a customer and that requires exactly this setting.

Rules:
- actionName: 3-6 words, Title Case, natural agent wording. Do NOT copy the
  setting's message verbatim; use the words a customer or agent would use.
- steps: 2-4 short imperative steps a user would follow (e.g. "Open Settings.",
  "Tap Accessibility.", "Turn off Mouse keys.").
- Respect the setting's direction: onURL = turn something ON, offURL = turn
  something OFF, updateURL = change a value, onClickURL = open a page.

Settings:
{items}

Return ONLY JSON: {{"probes": [{{"id": "<id>", "actionName": "...", "steps": ["...", "..."]}}]}}"""


def sample_entries(catalog: list[dict], n: int, seed: int = 7) -> list[dict]:
    """Stratified by originalType so every kind of entry is represented."""
    rng = random.Random(seed)
    buckets = defaultdict(list)
    for e in catalog:
        if e.get("deeplink", "").endswith("dummy_positive") or not e.get("message"):
            continue
        from app.eval.calibrate import is_degenerate_label
        if is_degenerate_label(e["message"]):
            continue
        buckets[e.get("originalType") or "none"].append(e)
    per = max(1, n // max(1, len(buckets)))
    out = []
    for kind in sorted(buckets):
        items = buckets[kind][:]
        rng.shuffle(items)
        out += items[:per]
    rng.shuffle(out)
    return out[:n]


def build_prompt(entries: list[dict]) -> str:
    lines = [f'- id={e["id"]} | type={e.get("originalType")} | message="{e["message"]}" | '
             f'description="{e.get("description", "")}"' for e in entries]
    return PROMPT.format(items="\n".join(lines))


def parse_probes(data: dict, entries: list[dict]) -> list[dict]:
    """Keep only well-formed probes whose id maps to a requested entry, and
    drop any that copied the catalog message verbatim (they'd test nothing)."""
    by_id = {e["id"]: e for e in entries}
    out = []
    for p in (data or {}).get("probes") or []:
        e = by_id.get(str(p.get("id")))
        name, steps = str(p.get("actionName") or "").strip(), [str(s).strip() for s in p.get("steps") or [] if str(s).strip()]
        if not e or not name or not steps:
            continue
        if name.lower() == e["message"].lower():
            continue
        out.append({"actionName": name, "steps": steps, "expected_message": e["message"],
                    "source_id": e["id"], "originalType": e.get("originalType"), "generated": True})
    return out
