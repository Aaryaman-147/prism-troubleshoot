"""
Data contract for the Smart Guided Troubleshooting Engine.
Mirrors Appendix A (schema.py) from the theme spec — do not deviate
from field names/types, since evaluation checks schema conformance directly.
"""
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class BaseDeeplink(BaseModel):
    deeplink: str


class Deeplink(BaseDeeplink):
    description: str
    message: Optional[str] = ""
    classes: Optional[Dict[str, str]] = None
    originalType: Optional[str] = None


class Condition(str, Enum):
    greater = "greater"
    equal = "equal"
    less = "less"


class ResultTypes(str, Enum):
    boolean = "boolean"
    intNum = "integer"
    string = "str"
    floatNum = "float"


class ActionCategory(str, Enum):
    auto = "auto"
    manual = "manual"
    critical = "critical"


class ValidationDeepLink(BaseDeeplink):
    key: str
    resultType: Optional[ResultTypes] = None
    condition: Optional[Condition] = None
    value: Optional[str] = None


class StepGroup(BaseModel):
    steps: List[str]
    validationDeeplink: Optional[ValidationDeepLink] = None
    actionableDeeplink: Optional[Deeplink] = None


class Action(BaseModel):
    actionName: str
    description: str
    stepGroups: List[StepGroup]
    category: Optional[ActionCategory] = ActionCategory.manual

    @field_validator("description")
    @classmethod
    def description_word_count(cls, v: str) -> str:
        words = v.strip().split()
        if not (5 <= len(words) <= 7):
            raise ValueError(
                f"description must be 5-7 words, got {len(words)}: '{v}'"
            )
        if not v.strip().startswith("It will"):
            raise ValueError(f"description must start with 'It will', got: '{v}'")
        return v

    @field_validator("actionName")
    @classmethod
    def action_name_title_case(cls, v: str) -> str:
        if v != v.title():
            raise ValueError(f"actionName must be Title Case, got: '{v}'")
        return v


class Goal(BaseModel):
    goal: str
    title: str
    actions: List[Action]
    score: float = Field(ge=0.0, le=1.0)

    @field_validator("title")
    @classmethod
    def title_word_count(cls, v: str) -> str:
        words = v.strip().split()
        if not (2 <= len(words) <= 3):
            raise ValueError(f"title must be 2-3 words, got {len(words)}: '{v}'")
        return v

    @field_validator("goal")
    @classmethod
    def goal_syntax(cls, v: str) -> str:
        if not v.startswith("Follow these steps to perform this"):
            raise ValueError(
                f"goal must follow exact syntax 'Follow these steps to perform "
                f"this <Topic> Troubleshooting/Configuration', got: '{v}'"
            )
        return v


class ContextDeeplinkResponse(BaseModel):
    """RAG response containing a list of Goal objects."""
    contexts: List[Goal] = []
    fallback: Optional[str] = None


class TroubleshootRequest(BaseModel):
    query: str
    siis_response: Optional[str] = None


class ResponseMeta(BaseModel):
    latency_ms: float
    cache_hit: bool
    model: str
    cost_usd: float = 0.0
    cache_similarity: Optional[float] = None


class TroubleshootResponse(BaseModel):
    query: str
    query_variations: List[str] = []
    response: ContextDeeplinkResponse
    meta: ResponseMeta
