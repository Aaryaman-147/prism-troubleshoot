"""
Stage 2: Deeplink Mapping & Ordering.
Resolves each action's target screen to a verbatim deeplink from the
catalog (via hybrid retrieval), then orders actions: auto -> manual -> critical.
"""
from app.core.config import settings
from app.pipeline.deeplink_retrieval import DeeplinkIndex
from app.models.schema import ActionCategory

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
        for group in action.get("stepGroups", [])
        for step in group.get("steps", [])
    ]
    name = action.get("actionName", "")
    return " ".join([name, name, *steps]).strip()


def resolve_deeplinks(actions: list[dict], index: DeeplinkIndex) -> list[dict]:
    min_confidence = settings.DEEPLINK_MIN_CONFIDENCE
    margin = settings.DEEPLINK_MARGIN

    for action in actions:
        category = action.get("category", "manual")
        if category != "auto":
            continue

        query_text = _match_text(action)
        if not query_text:
            continue

        # top_k=2 so the runner-up is available for the ambiguity check.
        results = index.search(query_text, top_k=2)
        if results:
            entry, score = results[0]
            if score < min_confidence:
                # Don't attach a low-confidence guess — a missing deeplink
                # is honest; a wrong one silently fails "screen resolution
                # accuracy" and could send a user to the wrong settings
                # screen entirely.
                continue
            if len(results) > 1 and (score - results[1][1]) < margin:
                # Two catalog entries score near-identically: the index has
                # no real basis for preferring one. Abstain rather than let
                # an arbitrary tiebreak decide which settings screen the user
                # gets sent to.
                continue
            catalog_item = index.catalog_by_uri[entry.deeplink]
            for step_group in action.get("stepGroups", []):
                step_group["actionableDeeplink"] = {
                    "deeplink": entry.deeplink,
                    "description": catalog_item.get("description", ""),
                    "message": catalog_item.get("message", ""),
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
