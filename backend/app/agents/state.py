from __future__ import annotations

from typing import Literal, TypedDict
from pydantic import BaseModel, Field, field_validator

from app.models.entities import OutfitSlotRole, WardrobeCategory


class StylistContext(BaseModel):
    """Normalized situational context produced by the Context Agent."""

    occasion: str = Field(
        ...,
        description="Normalized occasion, e.g. cafe, daily_work, interview, wedding, party, date, casual",
    )
    time_of_day: str = Field(
        ...,
        description="Time of day: morning, afternoon, evening, night",
    )
    event_date: str | None = Field(
        default=None,
        description="Inferred ISO date YYYY-MM-DD in the user's timezone",
    )
    location_text: str | None = Field(
        default=None,
        description="User location if specified",
    )
    environment: str | None = Field(
        default=None,
        description="Environment: indoor, outdoor, mixed",
    )
    weather_condition: str = Field(
        ...,
        description="Weather condition: hot, warm, cool, cold, rainy",
    )
    temperature_celsius: float | None = Field(
        default=None,
        description="Temperature in Celsius if known",
    )
    target_formality_range: list[int] = Field(
        default_factory=lambda: [2, 3],
        description="[min, max] target formality level on a 1-5 scale",
    )
    style_hints: list[str] = Field(
        default_factory=list,
        description="Target style hints e.g. smart_casual, minimalist",
    )
    vibe_keywords: list[str] = Field(
        default_factory=list,
        description="Atmosphere/vibe keywords e.g. lịch sự nhẹ, thoải mái",
    )
    must_have: list[str] = Field(
        default_factory=list,
        description="Mandatory items or attributes",
    )
    must_avoid: list[str] = Field(
        default_factory=list,
        description="Excluded colors, items, or attributes",
    )
    weather_source: Literal["user", "api", "default"] = Field(
        default="default",
        description="Source of weather data",
    )
    needs_clarification: bool = Field(
        default=False,
        description="Flag indicating if the query requires clarification",
    )
    clarification_question: str | None = Field(
        default=None,
        description="Concise Vietnamese clarification question when ambiguous",
    )

    @field_validator("target_formality_range")
    @classmethod
    def validate_formality_range(cls, v: list[int]) -> list[int]:
        if len(v) != 2:
            raise ValueError("target_formality_range must contain exactly [min, max]")
        if not (1 <= v[0] <= 5 and 1 <= v[1] <= 5):
            raise ValueError("Formality level must be between 1 and 5")
        if v[0] > v[1]:
            raise ValueError("Formality minimum cannot exceed maximum")
        return v


class OutfitItemSlot(BaseModel):
    """Garment item allocated into an outfit slot."""

    item_id: str
    slot_role: OutfitSlotRole
    name: str
    primary_color: str
    style: str
    category: WardrobeCategory
    image_url: str | None = None


class EvaluatedOutfit(BaseModel):
    """Outfit combination with deterministic fashion scoring."""

    items: list[OutfitItemSlot]
    fashion_score: float = Field(ge=0.0, le=1.0)
    component_scores: dict[str, float] = Field(default_factory=dict)
    combination_id: str


class RankedOutfit(BaseModel):
    """Final ranked outfit recommendation."""

    outfit_id: str | None = None
    rank: int = Field(ge=1, le=3)
    composite_score: float = Field(ge=0.0, le=1.0)
    items: list[OutfitItemSlot]
    explanation_vi: str
    applied_preferences: list[str] = Field(default_factory=list)


class StylistGraphState(TypedDict, total=False):
    """Shared state flowing through the LangGraph recommendation workflow.

    Owners:
    - request_id, user_id, user_query: API entry
    - context: Context Agent
    - candidate_pool: Wardrobe Agent
    - evaluated_outfits: Fashion Agent
    - ranked_outfits: Personalization Agent
    - recommendation_ids, grounding_validated, feedback_prompt_eligible, feedback_target_outfit_id: Coordinator
    - errors, warnings: Producing nodes
    """

    request_id: str
    user_id: str
    user_query: str
    context: StylistContext | None
    candidate_pool: dict[str, list[OutfitItemSlot]]
    evaluated_outfits: list[EvaluatedOutfit]
    ranked_outfits: list[RankedOutfit]
    recommendation_ids: list[str]
    grounding_validated: bool
    feedback_prompt_eligible: bool
    feedback_target_outfit_id: str | None
    errors: list[str]
    warnings: list[str]
