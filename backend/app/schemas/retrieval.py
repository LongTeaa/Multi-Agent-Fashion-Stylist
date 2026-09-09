from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.models.entities import WardrobeCategory


class WardrobeRetrievalQuery(BaseModel):
    categories: list[WardrobeCategory] = Field(min_length=1)
    color_hints: list[str] = Field(default_factory=list, max_length=10)
    style_hints: list[str] = Field(default_factory=list, max_length=10)
    weather_condition: str | None = Field(default=None, min_length=1, max_length=50)
    formality_min: int | None = Field(default=None, ge=1, le=5)
    formality_max: int | None = Field(default=None, ge=1, le=5)
    must_have: list[str] = Field(default_factory=list, max_length=10)
    must_avoid: list[str] = Field(default_factory=list, max_length=10)
    text_query: str | None = Field(default=None, min_length=1, max_length=500)
    enable_full_text: bool = False
    limit_per_category: int = Field(default=15, ge=1, le=15)

    @model_validator(mode="after")
    def validate_query(self) -> WardrobeRetrievalQuery:
        if len(self.categories) != len(set(self.categories)):
            raise ValueError("Categories must be unique.")
        if (
            self.formality_min is not None
            and self.formality_max is not None
            and self.formality_min > self.formality_max
        ):
            raise ValueError("formality_min cannot exceed formality_max.")
        for values in (
            self.color_hints,
            self.style_hints,
            self.must_have,
            self.must_avoid,
        ):
            if len(values) != len(set(values)) or any(not value.strip() for value in values):
                raise ValueError("Retrieval values must be non-empty and unique.")
        return self
