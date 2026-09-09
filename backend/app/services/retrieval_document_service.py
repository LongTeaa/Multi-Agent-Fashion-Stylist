from __future__ import annotations

import unicodedata

from sqlmodel import Session

from app.models.entities import WardrobeItem, WardrobeRetrievalDocument, utc_now

_LIST_FIELDS = (
    "season",
    "weather_suitability",
    "functional_flags",
    "free_text_tags",
)
_SCALAR_FIELDS = (
    "category",
    "sub_category",
    "primary_color",
    "secondary_color",
    "pattern",
    "material",
    "style",
    "fit",
)


def _normalize_text(value: object) -> str:
    raw = value.value if hasattr(value, "value") else value
    return " ".join(
        unicodedata.normalize("NFKC", str(raw or "")).strip().lower().split()
    )


def build_retrieval_document(item: WardrobeItem) -> tuple[str, dict[str, object]]:
    """Build the deterministic metadata document used by retrieval implementations."""
    metadata: dict[str, object] = {
        field: (getattr(item, field).value if hasattr(getattr(item, field), "value") else getattr(item, field))
        for field in _SCALAR_FIELDS
    }
    metadata.update({field: list(getattr(item, field)) for field in _LIST_FIELDS})
    metadata["formality_level"] = item.formality_level

    tokens: list[str] = []
    for field in _SCALAR_FIELDS:
        value = metadata[field]
        if value:
            tokens.append(_normalize_text(value))
    for field in _LIST_FIELDS:
        tokens.extend(_normalize_text(value) for value in metadata[field])
    tokens.append(f"formality_{item.formality_level}")
    return " ".join(dict.fromkeys(token for token in tokens if token)), metadata


def refresh_retrieval_document(session: Session, item: WardrobeItem) -> None:
    """Upsert or remove one document without committing the caller's transaction."""
    existing = session.get(WardrobeRetrievalDocument, item.id)
    if not item.is_active or not item.is_user_confirmed or item.deleted_at is not None:
        if existing is not None:
            session.delete(existing)
        return

    searchable_text, metadata = build_retrieval_document(item)
    if existing is None:
        existing = WardrobeRetrievalDocument(
            wardrobe_item_id=item.id,
            user_id=item.user_id,
            searchable_text=searchable_text,
            metadata_snapshot=metadata,
        )
    else:
        existing.searchable_text = searchable_text
        existing.metadata_snapshot = metadata
        existing.updated_at = utc_now()
    session.add(existing)
