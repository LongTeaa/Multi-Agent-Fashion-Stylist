import uuid

from pydantic import BaseModel, Field, field_validator

from app.models.entities import OutfitSlotRole


class StylistChatRequest(BaseModel):
    """Public request payload for POST /api/v1/stylist/chat."""

    query: str = Field(..., min_length=1, max_length=1000, description="Vietnamese styling query from the user.")
    location: str | None = Field(default=None, max_length=200, description="Optional user location.")
    client_session_id: str | None = Field(
        default=None,
        max_length=64,
        description="Optional client session UUID v4 for session-scoped feedback cadence suppression.",
    )
    idempotency_key: str | None = Field(
        default=None,
        max_length=64,
        description="Optional client-provided idempotency key for safely retrying recommendation requests.",
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Query must not be empty or whitespace only.")
        if len(trimmed) > 1000:
            raise ValueError("Query must not exceed 1000 characters.")
        return trimmed

    @field_validator("location")
    @classmethod
    def validate_location(cls, v: str | None) -> str | None:
        if v is None:
            return None
        trimmed = v.strip()
        if not trimmed:
            return None
        if len(trimmed) > 200:
            raise ValueError("Location must not exceed 200 characters.")
        return trimmed

    @field_validator("client_session_id")
    @classmethod
    def validate_client_session_id(cls, v: str | None) -> str | None:
        if v is None:
            return None
        trimmed = v.strip()
        if not trimmed:
            return None
        try:
            parsed = uuid.UUID(trimmed)
            if parsed.version != 4:
                raise ValueError("client_session_id must be a valid UUID v4.")
        except Exception:
            raise ValueError("client_session_id must be a valid UUID v4.")
        return str(parsed)

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(cls, v: str | None) -> str | None:
        if v is None:
            return None
        trimmed = v.strip()
        return trimmed if trimmed else None


class StylistContextResponse(BaseModel):
    """Public allowlist snapshot of extracted styling context."""

    occasion: str | None = None
    time_of_day: str | None = None
    event_date: str | None = None
    location_text: str | None = None
    environment: str | None = None
    weather_condition: str | None = None
    temperature_celsius: float | None = None
    target_formality_range: list[int] = Field(default_factory=list)
    style_hints: list[str] = Field(default_factory=list)
    vibe_keywords: list[str] = Field(default_factory=list)
    must_have: list[str] = Field(default_factory=list)
    must_avoid: list[str] = Field(default_factory=list)
    weather_source: str = "default"


class StylistRecommendationItemResponse(BaseModel):
    """Public representation of an item included in an outfit recommendation."""

    slot: OutfitSlotRole
    item_id: str
    name: str
    image_url: str | None = None

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not v.startswith("/api/v1/media/"):
            raise ValueError(f"image_url must be a relative /api/v1/media/ path or None, got: {v}")
        return v


class StylistRecommendationResponse(BaseModel):
    """Public representation of a complete grounded outfit recommendation."""

    outfit_id: str
    rank: int = Field(ge=1, le=3, description="Outfit rank order (1..3).")
    composite_score: float = Field(ge=0.0, le=1.0, description="Overall matching composite score (0.0..1.0).")
    items: list[StylistRecommendationItemResponse]
    explanation_vi: str
    applied_preferences: list[str] = Field(default_factory=list)


class StylistChatResponseData(BaseModel):
    """Response data envelope for POST /api/v1/stylist/chat."""

    request_id: str
    needs_clarification: bool
    clarification_question: str | None = None
    context: StylistContextResponse
    recommendations: list[StylistRecommendationResponse] = Field(default_factory=list)
    feedback_prompt_eligible: bool = False
    feedback_target_outfit_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
