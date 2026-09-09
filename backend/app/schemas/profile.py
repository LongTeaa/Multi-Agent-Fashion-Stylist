from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class PreferenceSelections(BaseModel):
    styles: list[str] = Field(default_factory=list, max_length=3)
    color_palettes: list[str] = Field(default_factory=list, max_length=3)
    priorities: list[str] = Field(default_factory=list, max_length=3)
    avoid_colors: list[str] = Field(default_factory=list, max_length=20)
    avoid_styles: list[str] = Field(default_factory=list, max_length=20)
    fit_preferences: list[str] = Field(default_factory=list, max_length=1)

    @field_validator("styles", "color_palettes", "priorities", "avoid_styles", "fit_preferences")
    @classmethod
    def validate_unique_options(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("Preference selections must be unique.")
        return values

    @field_validator("avoid_colors")
    @classmethod
    def validate_avoid_colors(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("Preference selections must be unique.")
        if any(
            not value
            or len(value) > 50
            or not value[0].isalpha()
            or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_" for character in value)
            for value in values
        ):
            raise ValueError("Avoided colors must use canonical lowercase identifiers.")
        return values


class ProfileResponseData(BaseModel):
    user_id: str
    email: str | None
    full_name: str | None
    preferences: PreferenceSelections
    feature_weights: dict[str, object]
    ratings_count: int


class PreferenceOptionGroup(BaseModel):
    values: list[str]
    selection_limit: int


class PreferenceOptionsResponseData(BaseModel):
    version: int
    styles: PreferenceOptionGroup
    color_palettes: PreferenceOptionGroup
    priorities: PreferenceOptionGroup
    fit_preferences: PreferenceOptionGroup
    avoid_colors: PreferenceOptionGroup
    avoid_styles: PreferenceOptionGroup
