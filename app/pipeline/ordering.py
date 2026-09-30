"""
Stage 2: Deeplink Mapping & Ordering.
Resolves each action's target screen to a verbatim deeplink from the
catalog (via hybrid retrieval), then orders actions: auto -> manual -> critical.
"""
import re

from app.core.config import settings
from app.pipeline.deeplink_retrieval import DeeplinkIndex
from app.models.schema import ActionCategory
from app.pipeline.normalize import normalize_category

# Per the theme spec's data-inputs section: "bixby://dummy_positive: A
# reserved generic placeholder used exclusively when a step opens a valid
# Settings screen not currently indexed in the catalog." It's a real
# catalog entry (present in app/data/deeplinks.json), not a code constant
# we invented -- but left to compete in normal BM25/dense ranking its vague
# description ("Generic placeholder...") almost never wins, so without
# explicit handling it's effectively dead. It exists specifically for the
# floor-rejection case: an "auto" action (by definition meant to be safely
# reachable via deeplink) where retrieval found no catalog entry confident
# enough to attach. This is also what the spec's own automated gate --
# "Auto actions carrying valid actionable deeplink >= 90%" -- is almost
# certainly checking: consistently leaving auto actions deeplink-less
# under low catalog coverage (today's 5-entry placeholder) would fail that
# gate even though refusing to guess is otherwise the right call.
def _dummy_uri(index) -> str | None:
    """Find the reserved placeholder by suffix, not a hardcoded scheme --
    Samsung's real catalog uses voiceassist://, the placeholder used bixby://."""
    return next((u for u in index.catalog_by_uri if u.endswith("dummy_positive")), None)

# Samsung's catalog pairs most toggles: an onURL entry ("Enables X") and an
# offURL entry ("Disables X") sharing one validation key. Their descriptions
# differ by a single word, so they score almost identically, and the
# ambiguity margin used to abstain on them -- discarding a correct deeplink.
# The catalog readme says to match on originalType too: infer the intended
# direction from the action text and pick the matching twin.
_ON_RE = re.compile(r"\b(turn(?:ed|ing)?\s+on|switch(?:ed)?\s+on|enabl\w*|activat\w*|allow)\b", re.I)
_OFF_RE = re.compile(r"\b(turn(?:ed|ing)?\s+off|switch(?:ed)?\s+off|disabl\w*|deactivat\w*)\b", re.I)
_NAV_RE = re.compile(r"\b(?:tap|select|open|go to|navigate to|choose)\s+(?:on\s+)?(?:the\s+)?([A-Za-z][\w&' -]*)", re.I)


INTENT_BONUS = 0.05


_BARE_SETTINGS_STEP = re.compile(r"^\s*(?:open|launch|go to|navigate to(?: and open)?)\s+(?:the\s+)?settings(?:\s+app)?\.?\s*$", re.I)
_UPDATE_RE = re.compile(r"\b(adjust|change|increase|decrease|reduce|lower|raise|set)\b", re.I)
_VIEW_RE = re.compile(r"^\s*(view|open|check|see|review)\b", re.I)


def _intent(action: dict) -> str | None:
    text = " ".join([action.get("actionName", "")] +
                    [s for g in (action.get("stepGroups") or []) for s in (g.get("steps") or [])])
    # The action's LEADING verb decides. "Disable Allow apps to be pinned" and
    # "Disable Double tap to turn on screen" contain on-words later in the
    # name; scanning the whole text saw both on and off, gave up, and the
    # enable twin won -- opposite-toggle errors in the catalog check.
    lead = action.get("actionName", "").strip().lower()
    if re.match(r"(enable|turn on|switch on|activate)\b", lead):
        return "onURL"
    if re.match(r"(disable|turn off|switch off|deactivate|remove)\b", lead):
        return "offURL"
    on, off = bool(_ON_RE.search(text)), bool(_OFF_RE.search(text))
    if on != off:
        return "onURL" if on else "offURL"
    # Catalog originalType also distinguishes updateURL ("Adjust Timeout")
    # and onClickURL ("View Reset Options"). Judge those from the action name
    # only -- every step list says "Open Settings", which would make
    # everything look like a view action.
    name = action.get("actionName", "")
    if _UPDATE_RE.search(name):
        return "updateURL"
    if _VIEW_RE.search(name):
        return "onClickURL"
    return None


def _twin_key(uri: str, catalog: dict) -> str:
    item = catalog.get(uri) or {}
    return (item.get("validation") or {}).get("key") or uri


def _collapse_twins(results, catalog: dict, intent: str | None):
    """Keep one candidate per setting (twins share a validation key): the
    one whose originalType matches the intent, at the group's best score.
    Twins are the SAME setting, so they must not count as ambiguity."""
    groups: dict[str, list] = {}
    for e, sc in results:
        groups.setdefault(_twin_key(e.deeplink, catalog), []).append((e, sc))
    out = []
    for members in groups.values():
        best = max(sc for _, sc in members)
        # With no explicit "off" wording, a fix enables the thing it names
        # (sample_output: "Back Up Phone Data" -> the onURL "Enable Back up
        # data" entry), so twins default to onURL.
        want = intent or "onURL"
        pick = next(((e, best) for e, _ in members
                     if (catalog.get(e.deeplink) or {}).get("originalType") == want), None)
        e, sc = pick or max(members, key=lambda m: m[1])
        # Explicit on/off wording that matches the entry's originalType is
        # strong evidence (catalog readme: match on originalType too).
        if intent and (catalog.get(e.deeplink) or {}).get("originalType") == intent:
            sc += INTENT_BONUS
        out.append((e, sc))
    return sorted(out, key=lambda m: -m[1])


_ACTION_STEP_RE = re.compile(r"^\s*(select|choose|toggle|turn|switch|swipe|confirm|enter|type|drag|press)\b", re.I)
_ACTION_WORDS = {"install", "download", "reset", "delete", "restart", "confirm", "apply", "save", "ok", "done", "update"}
_DETERMINERS = {"your", "the", "my", "a", "an", "this", "that"}
_GENERIC_UI = {"icon", "button", "option", "options", "gear", "toggle", "switch", "list", "tab", "field", "item",
               "menu", "more", "three-dot", "dot", "arrow", "back", "ok", "done"}
_LABEL_STOP = {"and", "or", "the", "a", "an", "to", "of", "for", "on", "in"}


def _screen_label(action: dict) -> str:
    """
    Name the concrete screen from the steps (for dummy_positive's
    description/message, which the catalog says we must write). The FINAL
    step is often an action, not a screen -- "Select Buttons", "Tap Download
    and install" produced "Buttons" / "Download and" in a real run -- so it
    is only used when it reads like navigation.
    """
    steps = [s for g in (action.get("stepGroups") or []) for s in (g.get("steps") or [])]
    targets = []
    for k, step in enumerate(steps):
        last = k == len(steps) - 1
        if last and _ACTION_STEP_RE.match(step):
            continue
        for m in _NAV_RE.finditer(step):
            cand = re.sub(r"[^\w&' -]", "", m.group(1)).strip()
            if not cand or cand.lower() in ("settings", "the settings", "settings app"):
                continue
            if last and _ACTION_WORDS & set(cand.lower().split()):
                continue
            # "your email" -> "email"; skip UI widgets ("icon", "gear icon")
            words = [w for w in cand.split() if w.lower() not in _DETERMINERS]
            if not words or all(w.lower() in _GENERIC_UI for w in words):
                continue
            targets.append(" ".join(words))
    words = (targets[-1] if targets else action.get("actionName", "") or "relevant").split()
    words = [w for w in words if w.lower() not in ("settings", "setting", "menu", "screen", "page")][:2]
    while words and words[-1].lower() in _LABEL_STOP:
        words.pop()
    return " ".join(words) or "relevant"


_NOT_SETTINGS_APP = ("quick settings", "quick panel", "notification panel")


def _navigates_settings(action: dict) -> bool:
    """True if a step opens the Settings app. The Quick settings PANEL
    (swipe down) is not a Settings screen, so it doesn't qualify for the
    dummy_positive placeholder -- a real run linked "Verify Internet
    Connection" to "Open the Quick settings page"."""
    for g in (action.get("stepGroups") or []):
        for s in (g.get("steps") or []):
            low = s.lower()
            for phrase in _NOT_SETTINGS_APP:
                low = low.replace(phrase, "")
            if "settings" in low:
                return True
    return False


_CATEGORY_ORDER = {
    ActionCategory.auto: 0,
    ActionCategory.manual: 1,
    ActionCategory.critical: 2,
}

def _match_text(action: dict) -> str:
    """
    Build the text used to find this action's target SCREEN.

    Deliberately excludes `description`. The description states the user
    BENEFIT ("It will stop flicker and save battery"), not the destination,
    and its vocabulary actively misleads retrieval: that example put the word
    "battery" into a display-settings lookup and pulled back
    battery_optimization for a Motion Smoothness fix.

    actionName plus the literal UI steps ("Open Settings", "Tap Display")
    describe where the user is actually going, which is what the catalog's
    descriptive metadata also describes. actionName is repeated once to
    weight it above the step text.
    """
    steps = [
        step
        for group in (action.get("stepGroups") or [])
        for step in (group.get("steps") or [])
    ]
    name = action.get("actionName", "")
    if settings.RETRIEVAL_TEXT_VERSION == "v2":
        # "Open Settings." is step 1 of almost every action and matches every
        # catalog entry equally; it carries no information about the target.
        steps = [s for s in steps if not _BARE_SETTINGS_STEP.match(s)]
    return " ".join([name, name, *steps]).strip()


def resolve_deeplinks(
    actions: list[dict],
    index: DeeplinkIndex,
    min_confidence: float | None = None,
    margin: float | None = None,
    alpha: float | None = None,
) -> tuple[list[dict], list[dict], dict[str, float]]:
    """
    Returns (actions, ambiguous_matches, confidences).

    ambiguous_matches: one entry per action where the ambiguity margin
    abstained — {"actionName": ..., "candidates": [{deeplink, description,
    score}, ...]}. Previously this information was computed (top-2 results)
    and then thrown away the instant the margin check failed; surfacing it
    turns a silent gap into a real "did you mean X or Y?" the caller can
    act on, instead of nothing at all.

    confidences: {actionName: score} for every auto action that WAS
    resolved — explainability data for why a given deeplink was attached,
    not just that it was.

    min_confidence/margin/alpha: per-call overrides of the .env defaults,
    for a live-tunable demo (see RetrievalOverrides in schema.py). None
    means "use the configured default", same as before this parameter
    existed — existing callers are unaffected.
    """
    min_confidence = settings.DEEPLINK_MIN_CONFIDENCE if min_confidence is None else min_confidence
    margin = settings.DEEPLINK_MARGIN if margin is None else margin

    ambiguous_matches: list[dict] = []
    confidences: dict[str, float] = {}

    for action in actions:
        category = action.get("category", "manual")
        if category != "auto":
            continue

        query_text = _match_text(action)
        if not query_text:
            continue

        # top_k=3, not 2: fetch one extra slot of headroom in case the
        # dummy_positive placeholder itself ranks in the top few on a weak
        # query (its own qna_description is generic filler text, "placeholder
        # fallback generic", which can occasionally out-rank a genuinely
        # weak real candidate). It's filtered out below before floor/margin
        # logic runs, so it never wins a "real" match or gets offered as an
        # ambiguous candidate next to legitimate options.
        raw_results = index.search(query_text, top_k=6, alpha=alpha)
        dummy_uri = _dummy_uri(index)
        results = [(e, s) for e, s in raw_results if e.deeplink != dummy_uri]
        results = _collapse_twins(results, index.catalog_by_uri, _intent(action))

        resolved = False
        if results:
            entry, score = results[0]
            floor_ok = score >= min_confidence
            unambiguous = len(results) < 2 or (score - results[1][1]) >= margin

            if floor_ok and unambiguous:
                catalog_item = index.catalog_by_uri[entry.deeplink]
                for step_group in (action.get("stepGroups") or []):
                    step_group["actionableDeeplink"] = {
                        "deeplink": entry.deeplink,
                        "description": catalog_item.get("description", ""),
                        "message": catalog_item.get("message", ""),
                        # Spec's sample output carries originalType; it was dropped.
                        "originalType": catalog_item.get("originalType"),
                    }
                confidences[action.get("actionName", "")] = min(1.0, score)
                resolved = True
            elif floor_ok and not unambiguous:
                # Two catalog entries score near-identically: the index has
                # no real basis for preferring one. Surface both rather than
                # silently discarding the runner-up — the caller (or a human
                # in the loop) can disambiguate instead of getting nothing.
                ambiguous_matches.append({
                    "actionName": action.get("actionName", ""),
                    "candidates": [
                        {
                            "deeplink": e.deeplink,
                            "description": index.catalog_by_uri[e.deeplink].get("description", ""),
                            "score": s,
                        }
                        for e, s in results[:2]
                    ],
                })

        if not resolved:
            # hybrid (default): a step that opens a Settings screen with no
            # confident catalog match -> the catalog's own dummy_positive
            # placeholder, with description/message written from the steps
            # (as the catalog entry instructs). Anything else (service
            # center, physical action) -> manual + null, as in Samsung's
            # sample_output.json.
            dummy_uri = _dummy_uri(index)
            policy = settings.UNMATCHED_AUTO_POLICY
            use_dummy = dummy_uri and (policy == "dummy_positive" or
                                       (policy == "hybrid" and _navigates_settings(action)))
            if use_dummy:
                dummy = index.catalog_by_uri[dummy_uri]
                screen = _screen_label(action)
                for step_group in (action.get("stepGroups") or []):
                    step_group["actionableDeeplink"] = {
                        "deeplink": dummy_uri,
                        "description": f"Opens the {screen} screen in Settings",
                        "message": f"Open the {screen} settings page",
                        "originalType": dummy.get("originalType"),
                    }
            else:
                action["category"] = "manual"
                for step_group in (action.get("stepGroups") or []):
                    step_group["actionableDeeplink"] = None
                    step_group["validationDeeplink"] = None
    return actions, ambiguous_matches, confidences


_VALID_RESULT_TYPES = {"boolean", "integer", "str", "float"}
_VALID_CONDITIONS = {"greater", "equal", "less"}


def attach_validation_deeplinks(actions: list[dict], catalog_by_uri: dict | None = None) -> list[dict]:
    """
    validationDeeplink is copied VERBATIM from the matched catalog entry's
    own `validation` block -- deeplink, key, and (where the catalog has them)
    resultType/condition/value. Samsung's sample_output.json does exactly
    this (DL-0542 -> key "Back up data (TechCorp Cloud)", boolean/equal/True).

    Previously the key/resultType/value came from an LLM-proposed
    expectedOutcome, and when the catalog had no validation entry the
    actionable URI was reused as the validation target. Both were invented
    data; with the real catalog (validation on 570/578 entries) neither is
    needed. No catalog validation -> no validationDeeplink.
    """
    catalog_by_uri = catalog_by_uri or {}
    for action in actions:
        action.pop("expectedOutcome", None)
        for step_group in (action.get("stepGroups") or []):
            actionable = step_group.get("actionableDeeplink")
            val = (catalog_by_uri.get(actionable["deeplink"]) or {}).get("validation") if actionable else None
            if isinstance(val, dict) and val.get("deeplink") and val.get("key"):
                step_group["validationDeeplink"] = {
                    k: (str(val[k]) if k == "value" else val[k])
                    for k in ("deeplink", "key", "resultType", "condition", "value")
                    if val.get(k) is not None
                }
            elif actionable is not None:
                step_group.pop("validationDeeplink", None)
    return actions


def order_actions(actions: list[dict]) -> list[dict]:
    """Safe (auto) first, manual next, critical/destructive last."""
    return sorted(
        actions,
        key=lambda a: _CATEGORY_ORDER.get(
            ActionCategory(normalize_category(a.get("category"))), 1
        ),
    )
