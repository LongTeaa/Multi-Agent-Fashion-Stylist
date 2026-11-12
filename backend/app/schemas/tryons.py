from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TryOnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outfit_id: str | None = Field(default=None, max_length=36)
    avatar_id: str | None = Field(default=None, max_length=36)
    item_ids: list[str] | None = None


class TryOnResponseData(BaseModel):
    tryon_id: str = Field(min_length=36, max_length=36)
    outfit_id: str | None = None
    image_url: str | None = None
    render_kind: Literal["virtual_tryon", "generated_lookbook", "moodboard"] | None = None
    fallback_used: bool = False
    duration_ms: int = Field(default=0, ge=0)
    status: Literal["processing", "ready", "failed"] = "ready"
    error_code: str | None = None


class TryOnAvatarResponse(BaseModel):
    id: str
    name: str
    is_preset: bool
    preset_gender: str | None = None
    is_default: bool = False
    image_url: str
    created_at: datetime
