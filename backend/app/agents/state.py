from __future__ import annotations

from datetime import datetime
from typing import Literal, TypedDict
from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.entities import OutfitSlotRole, WardrobeCategory


class GarmentConstraint(BaseModel):
    """Structured garment constraint capturing the binding between item, category, color, and material."""

    category: WardrobeCategory | None = Field(
        default=None,
        description="Target wardrobe category if known (e.g. top, bottom, outerwear)",
    )
    sub_category: str | None = Field(
        default=None,
        description="Canonical sub-category (e.g. polo, blazer, jacket, dress, chinos, sneakers)",
    )
    color: str | None = Field(
        default=None,
        description="Canonical English color (e.g. white, black, navy)",
    )
    material: str | None = Field(
        default=None,
        description="Canonical English material if specified (e.g. leather, denim, cotton)",
    )
    raw_text: str = Field(
        default="",
        description="Original phrase from user query",
    )
    is_category_only: bool = Field(
        default=False,
        description="True if the constraint only mentions a generic category term like 'áo', 'quần', 'giày'",
    )


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
    structured_must_have: list[GarmentConstraint] = Field(
        default_factory=list,
        description="Structured inclusion constraints linking garment, color, and material",
    )
    structured_must_avoid: list[GarmentConstraint] = Field(
        default_factory=list,
        description="Structured exclusion constraints linking garment, color, and material",
    )
    weather_source: Literal["user", "api", "default"] = Field(
        default="default",
        description="Source of weather data",
    )
    weight_profile: Literal["formal", "comfort", "active", "balanced"] = Field(
        default="balanced",
        description="Dynamic weighting profile: formal, comfort, active, balanced",
    )
    target_functional_tags: list[str] = Field(
        default_factory=list,
        description="Target functional requirement tags, e.g. ['outdoor', 'sun', 'movement', 'water_resistant']",
    )
    client_session_id: str | None = Field(
        default=None,
        description="Client session identifier for feedback cadence suppression",
    )
    needs_clarification: bool = Field(
        default=False,
        description="Flag indicating if the query requires clarification",
    )
    clarification_question: str | None = Field(
        default=None,
        description="Concise Vietnamese clarification question when ambiguous",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Extraction confidence score",
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
    """Garment item allocated into an outfit slot with full metadata for scoring."""

    item_id: str
    slot_role: OutfitSlotRole
    name: str
    sub_category: str = ""
    primary_color: str
    secondary_color: str | None = None
    style: str
    category: WardrobeCategory
    formality_level: int = Field(default=3, ge=1, le=5)
    comfort_level: int = Field(default=3, ge=1, le=5)
    # None means "not recorded": scoring infers it. A stored value is always trusted.
    silhouette_level: int | None = Field(default=None, ge=1, le=5)
    length: str | None = None
    weather_suitability: list[str] = Field(default_factory=list)
    pattern: str = Field(default="solid")
    material: str = Field(default="cotton")
    fit: str = Field(default="regular")
    functional_flags: list[str] = Field(default_factory=list)
    image_url: str | None = None
    times_worn: int = Field(default=0, ge=0)
    last_worn_at: str | None = None

    @model_validator(mode="after")
    def validate_slot_role_matches_category(self) -> OutfitItemSlot:
        if self.slot_role.value != self.category.value:
            raise ValueError(f"slot_role '{self.slot_role}' must match category '{self.category}'")
        return self


class EvaluatedOutfit(BaseModel):
    """Outfit combination with deterministic fashion scoring."""

    items: list[OutfitItemSlot] = Field(min_length=1)
    fashion_score: float = Field(ge=0.0, le=1.0)
    component_scores: dict[str, float | str] = Field(default_factory=dict)
    combination_id: str


class RankedOutfit(BaseModel):
    """Final ranked outfit recommendation."""

    outfit_id: str | None = None
    rank: int = Field(ge=1, le=3)
    composite_score: float = Field(ge=0.0, le=1.0)
    fashion_score: float | None = None
    personalization_score: float | None = None
    items: list[OutfitItemSlot] = Field(min_length=1)
    explanation_vi: str = ""
    applied_preferences: list[str] = Field(default_factory=list)


SlotName = Literal["tops", "bottoms", "dresses", "footwear", "outerwear", "accessories"]

RelaxAction = Literal[
    "color_family",
    "material_relax",
    "subcategory_equivalent",
]

MAX_RELAXATION_ROUNDS = 2

_RELAX_TOKEN_ALIASES: dict[str, str] = {
    "jean": "jeans",
    "sneaker": "sneakers",
    "sandal": "sandals",
}


def normalize_relax_token(value: str) -> str:
    """Canonical normalization shared by bottleneck diagnosis, constraint matching, and relaxation application."""
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    return _RELAX_TOKEN_ALIASES.get(normalized, normalized)


class ConstraintRelaxationPlan(BaseModel):
    """Per-constraint relaxation actions so one constraint's action never leaks to another."""

    slot: SlotName
    constraint: GarmentConstraint
    allowed_actions: list[RelaxAction] = Field(min_length=1)


class RelaxationRequest(BaseModel):
    """Feedback message from Fashion Agent back to Wardrobe Agent (Loop 1)."""

    issue_code: Literal["MISSING_SLOT", "CONSTRAINT_UNSATISFIED"]
    bottleneck_slots: list[SlotName] = Field(min_length=1)
    blocked_constraints: list[GarmentConstraint] = Field(default_factory=list)
    allowed_actions: list[RelaxAction] = Field(min_length=1)
    constraint_plans: list[ConstraintRelaxationPlan] = Field(default_factory=list)
    reason_vi: str


class RelaxationStep(BaseModel):
    """Audit record of one executed relaxation step for downstream validation and explanation."""

    round: int = Field(ge=1)
    slot: SlotName
    action: RelaxAction
    category: WardrobeCategory
    original_value: str
    relaxed_values: list[str] = Field(default_factory=list)
    reason_vi: str


class CritiqueSignal(BaseModel):
    """Critique feedback signal from Coordinator back to Fashion Agent (Loop 2)."""

    issue_code: Literal["ALL_RECENTLY_WORN", "LOW_DIVERSITY", "CONTEXT_GAP"]
    soft_avoid_item_ids: list[str] = Field(default_factory=list)
    require_functional_tags: list[str] = Field(default_factory=list)
    diversify: bool = False
    reason_vi: str


class ConflictNote(BaseModel):
    """Structured multi-objective conflict record for Coordinator arbitration and explanation."""

    conflict_type: Literal[
        "PROFILE_AVOID_VS_REQUEST",
        "RECENT_WEAR_VS_BEST_FIT",
        "RELAXED_CONSTRAINT",
        "CRITIC_KEPT_ORIGINAL",
    ]
    description_vi: str
    resolution_vi: str


class AgentTraceEvent(BaseModel):
    """Inter-agent communication trace event for debugging, testing, and observability."""

    round: int = Field(ge=0)
    sender: Literal["context", "wardrobe", "fashion", "personalization", "coordinator"]
    receiver: Literal["wardrobe", "fashion", "personalization", "coordinator", "end"]
    event_type: str
    summary_vi: str


class StylistGraphState(TypedDict, total=False):
    """Shared state flowing through the LangGraph recommendation workflow.

    Owners:
    - request_id, user_id, user_query, location, client_session_id: API entry
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
    location: str | None
    client_session_id: str | None
    reference_time: datetime | None
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

    # Multi-agent feedback loop coordination fields
    enable_agent_loops: bool
    enable_relaxation_loop: bool | None
    enable_critique_loop: bool | None
    disable_personalization: bool
    relaxation_round: int
    relaxation_request: RelaxationRequest | None
    active_relaxations: list[RelaxationStep]
    critique_round: int
    critique: CritiqueSignal | None
    previous_ranked_outfits: list[RankedOutfit]
    coordinator_decision: Literal["approve", "reroute_fashion", "fail"] | None
    conflict_notes: list[ConflictNote]
    agent_trace: list[AgentTraceEvent]


def is_relaxation_loop_enabled(state: StylistGraphState) -> bool:
    """Return whether bounded Loop 1 (Fashion <-> Wardrobe) is active."""
    override = state.get("enable_relaxation_loop")
    if override is not None:
        return bool(override)
    return bool(state.get("enable_agent_loops", False))


def is_critique_loop_enabled(state: StylistGraphState) -> bool:
    """Return whether bounded Loop 2 (Coordinator Critic -> Fashion) is active."""
    override = state.get("enable_critique_loop")
    if override is not None:
        return bool(override)
    return bool(state.get("enable_agent_loops", False))
