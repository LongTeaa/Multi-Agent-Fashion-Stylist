from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _validate_uuid_v4(val: str, field_name: str) -> str:
    trimmed = val.strip()
    try:
        parsed = uuid.UUID(trimmed)
        if parsed.version != 4:
            raise ValueError(f"{field_name} must be a valid UUID v4.")
    except Exception:
        raise ValueError(f"{field_name} must be a valid UUID v4.")
    return str(parsed)


class DismissPromptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_session_id: str | None = Field(
        default=None,
        max_length=64,
        description="Optional opaque client session UUID v4 for session-scoped prompt suppression.",
    )

    @field_validator("client_session_id")
    @classmethod
    def validate_client_session_id(cls, v: str | None) -> str | None:
        if v is None:
            return None
        trimmed = v.strip()
        if not trimmed:
            return None
        return _validate_uuid_v4(trimmed, "client_session_id")


class DismissPromptResponseData(BaseModel):
    cooldown_remaining: int = Field(
        ge=0,
        description="Number of eligible outfits that must be viewed before next prompt is shown.",
    )
    dismissed: bool = True
