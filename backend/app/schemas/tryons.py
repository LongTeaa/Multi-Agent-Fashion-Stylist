from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TryOnRequest(BaseModel):
    outfit_id: str = Field(min_length=36, max_length=36)


class TryOnResponseData(BaseModel):
    tryon_id: str = Field(min_length=36, max_length=36)
    outfit_id: str = Field(min_length=36, max_length=36)
    image_url: str
    render_kind: Literal["generated_lookbook", "moodboard"]
    fallback_used: bool
    duration_ms: int = Field(ge=0)
    status: Literal["ready"] = "ready"
