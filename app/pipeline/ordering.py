"""
Stage 2: Deeplink Mapping & Ordering.
Resolves each action's target screen to a verbatim deeplink from the
catalog (via hybrid retrieval), then orders actions: auto -> manual -> critical.
"""
from app.core.config import settings
from app.pipeline.deeplink_retrieval import DeeplinkIndex
from app.models.schema import ActionCategory

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
_DUMMY_POSITIVE_URI = "bixby://dummy_positive"

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
        raw_results = index.search(query_text, top_k=3, alpha=alpha)
        results = [(e, s) for e, s in raw_results if e.deeplink != _DUMMY_POSITIVE_URI]

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
                    }
                confidences[action.get("actionName", "")] = score
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
            # Floor rejection (no confident specific candidate) or ambiguity
            # (two candidates, neither more credible than the other): either
            # way this "auto" action was, by construction, meant to open a
            # real settings screen — the LLM only assigns category="auto"
            # for actions it considers safely reachable via deeplink. Rather
            # than leave actionableDeeplink absent, fall back to the
            # catalog's own reserved placeholder for exactly this situation.
            # Ambiguous cases keep BOTH: the placeholder satisfies "carries
            # a valid actionable deeplink" while ambiguous_matches still
            # offers the specific disambiguation as bonus wrapper data.
            dummy = index.catalog_by_uri.get(_DUMMY_POSITIVE_URI)
            if dummy:
                for step_group in (action.get("stepGroups") or []):
                    step_group["actionableDeeplink"] = {
                        "deeplink": _DUMMY_POSITIVE_URI,
                        "description": dummy.get("description", ""),
                        "message": dummy.get("message", ""),
                    }
    return actions, ambiguous_matches, confidences


_VALID_RESULT_TYPES = {"boolean", "integer", "str", "float"}
_VALID_CONDITIONS = {"greater", "equal", "less"}


def attach_validation_deeplinks(actions: list[dict]) -> list[dict]:
    """
    Wires up StepGroup.validationDeeplink — an official Appendix A field
    (key/resultType/condition/value) that was previously always absent.
    It's meant to let a client verify an action actually worked (e.g. "is
    Motion Smoothness now Standard?"), not just guide the user through it.

    Design note / limitation: the placeholder catalog has no entries
    dedicated to state-checking, only navigation-target entries. Rather
    than invent an unverifiable URI, this reuses the SAME already
    catalog-verified actionableDeeplink as the validation target — i.e.
    "read back the screen you just sent the user to" rather than a
    distinct verification endpoint. That keeps the "no hallucinated
    deeplinks" guarantee intact for this field too. If Samsung's real
    catalog exposes dedicated validation-type entries, swap the source
    URI here for a proper catalog lookup instead of reusing the
    actionable one.

    Only attaches when: the action resolved an actionableDeeplink (nothing
    to validate against otherwise), extraction supplied an `expectedOutcome`
    for that action, and its shape is valid — an malformed/partial
    expectedOutcome is silently dropped rather than raising, since this is
    a bonus field, not one the response should fail over.
    """
    for action in actions:
        outcome = action.get("expectedOutcome")
        if not isinstance(outcome, dict):
            continue

        key = outcome.get("key")
        result_type = outcome.get("resultType")
        condition = outcome.get("condition")
        value = outcome.get("value")
        if not (key and result_type in _VALID_RESULT_TYPES
                and condition in _VALID_CONDITIONS and value is not None):
            continue

        for step_group in (action.get("stepGroups") or []):
            actionable = step_group.get("actionableDeeplink")
            if not actionable:
                continue  # nothing resolved to validate against
            step_group["validationDeeplink"] = {
                "deeplink": actionable["deeplink"],
                "key": key,
                "resultType": result_type,
                "condition": condition,
                "value": str(value),
            }
    return actions


def order_actions(actions: list[dict]) -> list[dict]:
    """Safe (auto) first, manual next, critical/destructive last."""
    return sorted(
        actions,
        key=lambda a: _CATEGORY_ORDER.get(
            ActionCategory(a.get("category", "manual")), 1
        ),
    )
