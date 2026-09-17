"""
Tests for the Pydantic schema contract (app/models/schema.py).
These codify the exact rules from the spec's Section 4.1 (Schema
Specifications) — run with: pytest tests/test_schema.py -v
"""
import pytest
from pydantic import ValidationError

from app.models.schema import Goal, Action, StepGroup, ContextDeeplinkResponse, ActionCategory


def make_valid_action(**overrides):
    defaults = dict(
        actionName="Configure Display Settings",
        description="It will fix screen flicker issue",
        category=ActionCategory.auto,
        stepGroups=[StepGroup(steps=["Open Settings", "Tap Display"])],
    )
    defaults.update(overrides)
    return Action(**defaults)


class TestActionValidation:
    def test_valid_action_passes(self):
        action = make_valid_action()
        assert action.actionName == "Configure Display Settings"

    def test_description_too_long_rejected(self):
        with pytest.raises(ValidationError):
            make_valid_action(description="This is way too many words to pass the five to seven word validator")

    def test_description_too_short_rejected(self):
        with pytest.raises(ValidationError):
            make_valid_action(description="It will fix")

    def test_description_missing_it_will_prefix_rejected(self):
        with pytest.raises(ValidationError):
            make_valid_action(description="This will not validate at all")

    def test_action_name_not_title_case_rejected(self):
        with pytest.raises(ValidationError):
            make_valid_action(actionName="configure display settings")

    def test_five_word_description_at_lower_bound_passes(self):
        action = make_valid_action(description="It will fix the issue")
        assert action.description == "It will fix the issue"

    def test_seven_word_description_at_upper_bound_passes(self):
        action = make_valid_action(description="It will fix the screen flicker issue")
        assert action.description == "It will fix the screen flicker issue"


class TestGoalValidation:
    def test_valid_goal_passes(self):
        goal = Goal(
            goal="Follow these steps to perform this Display Troubleshooting",
            title="Display flickering",
            score=0.9,
            actions=[make_valid_action()],
        )
        assert goal.score == 0.9

    def test_goal_wrong_syntax_rejected(self):
        with pytest.raises(ValidationError):
            Goal(
                goal="Here is how to fix your display",  # wrong exact syntax
                title="Display flickering",
                score=0.9,
                actions=[make_valid_action()],
            )

    def test_title_too_many_words_rejected(self):
        with pytest.raises(ValidationError):
            Goal(
                goal="Follow these steps to perform this Display Troubleshooting",
                title="Display flickering and battery draining issue",  # 6 words
                score=0.9,
                actions=[make_valid_action()],
            )

    def test_score_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            Goal(
                goal="Follow these steps to perform this Display Troubleshooting",
                title="Display flickering",
                score=1.5,  # out of 0.0-1.0 range
                actions=[make_valid_action()],
            )


class TestContextDeeplinkResponse:
    def test_empty_contexts_with_fallback_valid(self):
        resp = ContextDeeplinkResponse(contexts=[], fallback="no_match")
        assert resp.contexts == []
        assert resp.fallback == "no_match"

    def test_default_contexts_is_empty_list(self):
        resp = ContextDeeplinkResponse()
        assert resp.contexts == []
        assert resp.fallback is None
