"""
Input/output normalization — the layer between Samsung's real data shapes
and the pipeline. Each function here exists because of a concrete mismatch
found in the audit, not speculatively.
"""
import re

_CATEGORIES = {"auto", "manual", "critical"}
MAX_VARIATIONS = 10


def clean_siis_content(title: str, content: str) -> str:
    """
    Samsung's siis_responses.json 'content' field is shaped like:
      "Smartphone,Others Mobile,Tablet Blank or black display on a smartphone
       or tablet ( Smartphone,Others Mobile,Tablet): <actual instructions>"
    i.e. a device-category tag list, then the title repeated, then the same
    tag list in parentheses, THEN the troubleshooting text. The tag lists are
    noise: they dilute the relevance embedding and hand extraction product
    taxonomy it could mistake for instructions. Strip them, keep the text.
    """
    text = (content or "").strip()
    title = (title or "").strip()
    if title:
        idx = text.find(title)
        # Only drop what precedes the title if it looks like a tag list
        # (short, no sentence punctuation) — never real instructions.
        if 0 <= idx < 250 and not re.search(r"[.!?]", text[:idx]):
            text = text[idx + len(title):]
    text = re.sub(r"^\s*\([^()]{0,300}\)\s*:?\s*", "", text)
    return text.strip()


def normalize_siis(siis) -> str:
    """
    siis_response arrives as either plain text or Samsung's object form
    {"title": ..., "content": ...} (per siis_responses.json, whose own
    _readme says this object IS the API payload). Returns one clean string.
    """
    if siis is None:
        return ""
    if isinstance(siis, str):
        return siis.strip()
    if hasattr(siis, "model_dump"):
        siis = siis.model_dump()
    if isinstance(siis, dict):
        title = str(siis.get("title") or "").strip()
        body = clean_siis_content(title, str(siis.get("content") or ""))
        return f"{title}. {body}".strip(". ").strip() if title else body
    return str(siis).strip()


def normalize_category(value) -> str:
    """LLMs emit 'Auto', ' critical ', 'safe'... Enum('Auto') raises, and
    ordering ran that Enum conversion OUTSIDE any try block — an unhandled
    500. Lowercase/strip; anything unrecognized becomes 'manual', the safe
    default (manual actions never get an automated deeplink)."""
    v = str(value or "").strip().lower()
    return v if v in _CATEGORIES else "manual"


def normalize_variations(variations, query: str) -> list[str]:
    """Spec requires 8-10 DISTINCT paraphrases. Dedupe case-insensitively,
    drop empties and exact repeats of the query, cap at 10. (We can't
    invent missing ones — under 8 is reported, not faked.)"""
    # A real enrichment response contained the literal string
    # "query_variations" as a paraphrase: never pass schema keys through.
    seen = {query.strip().lower(), "query_variations", "canonical_query", "sub_issues", "is_multi_issue"}
    out = []
    for v in variations or []:
        s = str(v).strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out[:MAX_VARIATIONS]


def merge_contexts(contexts: list[dict]) -> dict:
    """Collapse several contexts into one: first goal/title, highest score,
    actions concatenated (deduped by actionName). Used when extraction split
    ONE complaint into multiple plans -- seen in real runs as two contexts
    with the same title, or one context per possible cause."""
    base = dict(contexts[0])
    seen, actions = set(), []
    for c in contexts:
        for a in c.get("actions") or []:
            key = str(a.get("actionName", "")).strip().lower()
            if key not in seen:
                seen.add(key); actions.append(a)
    base["actions"] = actions
    base["score"] = max(float(c.get("score") or 0) for c in contexts)
    return base


def dedupe_contexts_by_title(contexts: list[dict]) -> list[dict]:
    """Two contexts with the same title are one issue, whatever else differs."""
    groups: dict[str, list[dict]] = {}
    order = []
    for c in contexts:
        k = str(c.get("title", "")).strip().lower()
        if k not in groups:
            groups[k] = []; order.append(k)
        groups[k].append(c)
    return [groups[k][0] if len(groups[k]) == 1 else merge_contexts(groups[k]) for k in order]


def reference_fingerprint(siis_text: str) -> str | None:
    """Stable id for a (normalized) SIIS reference; None when absent."""
    import hashlib
    t = " ".join((siis_text or "").split()).lower()
    return hashlib.sha1(t.encode("utf-8")).hexdigest()[:16] if t else None


import re as _re

# Samsung spec 4.1: critical = "Disruptive or irreversible operations (e.g.,
# factory reset, restart, firmware update, safe mode)". Enforced on the action
# name, not left to the LLM. Narrowed after an external audit:
#   - "restart" means restarting the DEVICE ("Restart Device", "Force Restart",
#     "Restart Phone In Safe Mode") -- not "Restart Bluetooth", "Restart Camera
#     App" or "Charge Device After Restart";
#   - resets of all/network settings ARE critical (a "settings" exemption used
#     to cancel them);
#   - checking for an update is not performing one.
_DEVICE_RESTART_RE = _re.compile(
    r"^\s*(?:force\s+)?(?:restart|reboot|power[- ]cycle)"
    r"(?:\s+(?:the\s+|your\s+)?(?:device|phone|tablet|smartphone|handset))?"
    r"(?:\s+(?:in|into|to)\b.*)?\s*$", _re.I)
_CRITICAL_RE = _re.compile(
    r"\b(safe mode|factory (?:data )?reset|reset (?:all|network) settings|reset (?:the )?(?:device|phone|tablet)|"
    r"wipe|recovery mode|firmware|(?:install|download|apply|perform)\b.*\b(?:software|system) updates?|"
    r"update (?:the )?(?:software|firmware|os))\b", _re.I)
_CRITICAL_EXEMPT_RE = _re.compile(r"^\s*(view|open|check|see)\b|\b(schedul\w*|automatic|auto[- ]restart)\b", _re.I)


def is_critical_action(action_name: str) -> bool:
    name = str(action_name or "")
    if _CRITICAL_EXEMPT_RE.search(name):
        return False
    return bool(_DEVICE_RESTART_RE.search(name) or _CRITICAL_RE.search(name))


_STEP_VERBS = r"(?:tap|select|enter|open|press|turn|swipe|go|choose|scroll|toggle|touch|clear|confirm|remove|add|check|connect|disconnect|wait|set|find|search|navigate|return|restart|sign|type)"
_THEN_SPLIT = _re.compile(r"\s*(?:,\s*|;\s*|\s+and\s+)then\s+(?=" + _STEP_VERBS + r"\b)|,\s*then\s+(?=" + _STEP_VERBS + r"\b)", _re.I)
_AND_SPLIT = _re.compile(r"\s+and\s+(?=(?:tap|select|open|enter|choose|toggle|turn)\b)", _re.I)


def split_compound_steps(steps: list[str]) -> list[str]:
    """Spec 4.1: "One physical interaction per step." Split steps like
    "Tap Storage and then tap Clear cache" into two. "Press and hold" and
    "Touch and hold" are ONE interaction and are never split."""
    out = []
    for step in steps or []:
        parts = [p for chunk in _THEN_SPLIT.split(step) for p in _AND_SPLIT.split(chunk)]
        parts = [p.strip().rstrip(",;") for p in parts if p and p.strip()]
        out += [p[:1].upper() + p[1:] for p in parts] if len(parts) > 1 else [step]
    return out


_FILLER_WORDS = {"the", "a", "an", "my", "is", "it", "and", "or", "to", "of", "in", "on", "when", "i", "me",
                 "this", "that", "so", "very", "really", "just", "keeps", "while", "with"}


def top_up_variations(variations: list[str], query: str, canonical: str, minimum: int = 8) -> list[str]:
    """Spec: 8 to 10 distinct paraphrases across registers (formal, casual,
    keyword-only, frustrated, typo-inclusive). The model sometimes returns
    fewer after de-duplication (95.5% compliance measured), so deterministic
    variants in those registers fill the gap. Never exceeds 10."""
    out = list(variations)
    seen = {v.lower() for v in out} | {query.strip().lower()}
    words = _re.findall(r"[A-Za-z0-9']+", query)
    keywords = " ".join(w for w in words if w.lower() not in _FILLER_WORDS)
    longest = max(words, key=len) if words else ""
    typo = query.replace(longest, longest[:2] + longest[3] + longest[2] + longest[4:], 1) if len(longest) > 4 else ""
    q = query.rstrip(".?!")
    kw = keywords.lower() or q.lower()
    # More templates than needed: for short complaints several collapse into
    # the same text (keyword-only == lowercase), which left 7 < 8.
    candidates = [canonical, kw, f"How do I fix this: {q}?", f"{q}, please help",
                  f"Help!! {q} and nothing works", typo, " ".join(w.lower() for w in words),
                  f"Issue: {kw}", f"{kw} fix", f"The device is experiencing {kw}", f"What causes {kw}?",
                  f"ugh, {kw} again", f"Troubleshooting {kw} on my phone", f"Having trouble with {kw}"]
    for c in candidates:
        c = (c or "").strip()
        if len(out) >= minimum:
            break
        if c and c.lower() not in seen:
            seen.add(c.lower()); out.append(c)
    return out[:10]


def sanitize_plan(raw) -> dict:
    """
    Coerce the LLM's plan into the SHAPE the pipeline expects before any code
    touches it. JSON parsing was guarded; structure was not: a real batch
    crashed with "'str' object has no attribute 'get'" when an action or
    step group arrived as a plain string. Rules:
      - contexts / actions that aren't objects are dropped
      - stepGroups given as strings (or a bare list of strings) become one
        step group; non-string steps are dropped
      - actionableDeeplink / validationDeeplink that aren't objects become None
    """
    if not isinstance(raw, dict):
        return {"contexts": [], "fallback": "extraction_error"}
    out = dict(raw)
    contexts = raw.get("contexts")
    clean_contexts = []
    for c in contexts if isinstance(contexts, list) else []:
        if not isinstance(c, dict):
            continue
        c = dict(c)
        acts = c.get("actions")
        clean_actions = []
        for a in acts if isinstance(acts, list) else []:
            if not isinstance(a, dict):
                continue
            a = dict(a)
            groups = a.get("stepGroups")
            if isinstance(groups, str):
                groups = [groups]
            clean_groups, loose = [], []
            for g in groups if isinstance(groups, list) else []:
                if isinstance(g, str):
                    loose.append(g)
                    continue
                if not isinstance(g, dict):
                    continue
                g = dict(g)
                steps = g.get("steps")
                if isinstance(steps, str):
                    steps = [steps]
                g["steps"] = [s for s in (steps if isinstance(steps, list) else []) if isinstance(s, str) and s.strip()]
                for k in ("actionableDeeplink", "validationDeeplink"):
                    if k in g and not isinstance(g[k], dict):
                        g[k] = None
                clean_groups.append(g)
            if loose:
                clean_groups.insert(0, {"steps": loose})
            a["stepGroups"] = [g for g in clean_groups if g["steps"]]
            if a["stepGroups"]:
                clean_actions.append(a)
        c["actions"] = clean_actions
        clean_contexts.append(c)
    out["contexts"] = clean_contexts
    return out


_NUMBERED_ITEM = _re.compile(r'\s*(?:^|\s)\d+[.)]\s*"?([^"]+?)"?(?=\s+\d+[.)]\s|\s*$)', _re.S)


def clean_complaint(query: str) -> str:
    """Normalize complaint text arriving at the API: strip wrapping quotes and
    leading list numbering, and turn a merged numbered list ('1. "a" 2. "b"')
    into sentences. Samsung's own input.txt line 17 has that shape."""
    q = " ".join(str(query or "").split())
    items = [m.group(1).strip() for m in _NUMBERED_ITEM.finditer(q)] if _re.match(r"^\s*1[.)]", q) else []
    if len(items) >= 2:
        return " ".join(i if i.endswith((".", "!", "?")) else i + "." for i in items)
    q = _re.sub(r"^\s*\d+[.)]\s*", "", q).strip()
    if len(q) >= 2 and q[0] in "\"'“" and q[-1] in "\"'”":
        q = q[1:-1].strip()
    return q
