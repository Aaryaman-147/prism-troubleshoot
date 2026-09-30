"""
Step grounding: does each generated step have support in the SIIS text?

Samsung's siis_responses.json readme: "Derive actions and steps from it; do
not invent steps that are not in the text." Schema validation cannot check
that. This does, deterministically and locally (no LLM call): a step counts
as supported when most of its content words appear in the reference.
UI verbs and filler ("tap", "open", "the") carry no evidence either way and
are ignored; a step made only of them is treated as supported.

Measured by default. Enforcement (dropping poorly grounded actions) is off
until the rate has been checked on real outputs: GROUNDING_MIN_ACTION_SUPPORT.
"""
import re

_TOKEN = re.compile(r"[a-z0-9]+")
_IGNORE = {
    "tap", "open", "select", "press", "hold", "swipe", "toggle", "turn", "go", "navigate", "choose",
    "then", "and", "or", "the", "a", "an", "to", "of", "for", "on", "off", "in", "into", "your", "you",
    "it", "is", "if", "at", "by", "with", "from", "this", "that", "until", "again", "any", "all",
    "button", "screen", "device", "phone", "app", "menu", "option", "settings", "setting", "confirm",
}


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _content(text: str) -> set[str]:
    return {_stem(w) for w in _TOKEN.findall(text.lower()) if len(w) > 2 and w not in _IGNORE}


def _reference_vocab(text: str) -> set[str]:
    """Content words plus joined adjacent pairs, so a step's "backup" matches
    the reference's "back up" (and "wifi" matches "Wi-Fi"). Without this, a
    correct step was counted as unsupported."""
    raw = _TOKEN.findall((text or "").lower())
    joined = {_stem(a + b) for a, b in zip(raw, raw[1:])}
    return _content(text) | joined


def step_support(step: str, reference_tokens: set[str]) -> float:
    raw = _TOKEN.findall(step.lower())
    words = {_stem(w) for w in raw if len(w) > 2 and w not in _IGNORE}
    if not words:
        return 1.0
    joined = {_stem(a + b) for a, b in zip(raw, raw[1:])}
    # A step's split word ("back up") is supported if its joined form is.
    supported = {w for w in words if w in reference_tokens}
    for a, b in zip(raw, raw[1:]):
        if _stem(a + b) in reference_tokens:
            supported |= {_stem(a), _stem(b)} & words
    return len(supported) / len(words)


def grounding_report(contexts: list[dict], reference: str, min_step_support: float = 0.5) -> dict:
    """Per-action fraction of supported steps, plus the overall step rate."""
    ref = _reference_vocab(reference or "")
    per_action, supported, total = {}, 0, 0
    for c in contexts or []:
        for a in c.get("actions") or []:
            steps = [s for g in a.get("stepGroups") or [] for s in g.get("steps") or []]
            ok = sum(1 for s in steps if step_support(s, ref) >= min_step_support)
            per_action[a.get("actionName", "")] = round(ok / len(steps), 3) if steps else 1.0
            supported += ok; total += len(steps)
    return {"step_support_pct": round(100.0 * supported / total, 1) if total else None, "per_action": per_action}


_INSTRUCTION_WORDS = {"open", "tap", "select", "settings", "then", "turn", "swipe", "press", "hold",
                      "enable", "disable", "set", "go", "navigate", "choose"}
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def reference_sentences(reference: str) -> list[str]:
    out = []
    for s in _SENT_SPLIT.split(reference or ""):
        s = re.sub(r"^[#*\-\s\d.)]+", "", s).strip()
        if len(s.split()) >= 3:
            out.append(s)
    return out


def step_sources(contexts: list[dict], reference: str, min_step_support: float = 0.5) -> dict[str, list]:
    """
    Provenance: for every step, the SIIS sentence that best supports it
    (None if no sentence covers enough of the step's content words). Makes
    "no hallucinated steps" visible: a judge can read the source line under
    each step, and an unsupported step stands out.
    """
    sents = [(s, _reference_vocab(s)) for s in reference_sentences(reference)]
    out: dict[str, list] = {}
    for c in contexts or []:
        for a in c.get("actions") or []:
            srcs = []
            # The action's own topic words (name + all its steps): when several
            # sentences equally support a generic step like "Open Settings.",
            # prefer the one about THIS action (Battery, not Display).
            action_text = " ".join([a.get("actionName", "")] + [x for g in a.get("stepGroups") or [] for x in g.get("steps") or []])
            action_words = {w for w in _TOKEN.findall(action_text.lower()) if len(w) > 2 and w not in _IGNORE}
            for g in a.get("stepGroups") or []:
                for step in g.get("steps") or []:
                    raw_step = set(_TOKEN.findall(step.lower()))
                    has_content = bool({_stem(w) for w in raw_step if len(w) > 2 and w not in _IGNORE})
                    best, best_key = None, (0.0, 0, 0)
                    for s, toks in sents:
                        # Pure navigation ("Open Settings.") has no content
                        # words, so every sentence tied and the FIRST won --
                        # the demo showed "Open Settings." sourced from a
                        # diagnosis sentence. Use raw-token overlap for those,
                        # and on any tie prefer the instruction-like sentence.
                        s_raw = set(_TOKEN.findall(s.lower()))
                        cov = step_support(step, toks) if has_content else \
                            (len(raw_step & s_raw) / len(raw_step) if raw_step else 0.0)
                        key = (round(cov, 6), len(action_words & s_raw), len(_INSTRUCTION_WORDS & s_raw))
                        if key > best_key:
                            best, best_key = s, key
                    srcs.append(best[:220] if best and best_key[0] >= min_step_support else None)
            out[a.get("actionName", "")] = srcs
    return out
