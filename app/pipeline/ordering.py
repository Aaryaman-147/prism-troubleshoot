"""
Stage 2: Deeplink Mapping & Ordering.
Resolves each action's target screen to a verbatim deeplink from the
catalog (via hybrid retrieval), then orders actions: auto -> manual -> critical.
"""
from app.pipeline.deeplink_retrieval import DeeplinkIndex
from app.models.schema import ActionCategory

_CATEGORY_ORDER = {
    ActionCategory.auto: 0,
    ActionCategory.manual: 1,
    ActionCategory.critical: 2,
}

_MIN_DEEPLINK_CONFIDENCE = 0.35  # tune once you have real deeplinks.json
def resolve_deeplinks(actions: list[dict], index: DeeplinkIndex) -> list[dict]:
    for action in actions:
        category = action.get("category", "manual")
        if category != "auto":
            continue

        query_text = f"{action['actionName']} {action['description']}"
        results = index.search(query_text, top_k=1)
        if results:
            entry, score = results[0]
            if score < _MIN_DEEPLINK_CONFIDENCE:
                # Don't attach a low-confidence guess — a missing deeplink
                # is honest; a wrong one silently fails "screen resolution
                # accuracy" and could send a user to the wrong settings
                # screen entirely.
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
