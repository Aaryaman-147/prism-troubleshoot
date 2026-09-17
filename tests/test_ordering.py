"""
Tests for action ordering (app/pipeline/ordering.py) — the spec's
"least disruptive first, critical last" rule.
Run with: pytest tests/test_ordering.py -v
"""
from app.pipeline.ordering import order_actions


class TestActionOrdering:
    def test_critical_sorts_last(self):
        actions = [
            {"actionName": "Factory Reset", "category": "critical"},
            {"actionName": "Toggle Setting", "category": "auto"},
        ]
        result = order_actions(actions)
        assert result[-1]["actionName"] == "Factory Reset"

    def test_auto_sorts_before_manual_and_critical(self):
        actions = [
            {"actionName": "Factory Reset", "category": "critical"},
            {"actionName": "Clean Port", "category": "manual"},
            {"actionName": "Toggle Setting", "category": "auto"},
        ]
        result = order_actions(actions)
        names = [a["actionName"] for a in result]
        assert names == ["Toggle Setting", "Clean Port", "Factory Reset"]

    def test_multiple_auto_actions_preserve_relative_order(self):
        actions = [
            {"actionName": "First Auto", "category": "auto"},
            {"actionName": "Second Auto", "category": "auto"},
        ]
        result = order_actions(actions)
        names = [a["actionName"] for a in result]
        assert names == ["First Auto", "Second Auto"]  # stable sort

    def test_missing_category_defaults_to_manual_ordering(self):
        actions = [
            {"actionName": "No Category", "category": "manual"},
            {"actionName": "Has Auto", "category": "auto"},
        ]
        result = order_actions(actions)
        assert result[0]["actionName"] == "Has Auto"
