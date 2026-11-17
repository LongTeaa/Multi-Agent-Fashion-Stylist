"""Normalize legacy garment profiles created before the Tier-1 taxonomy.

- functional_flags: map known aliases onto the canonical taxonomy; move any
  unrecognized flag into free_text_tags so no information is lost and the item
  remains editable (PATCH validates flags against the taxonomy).
- silhouette_level: rows still on the 0008 default (3) whose fit/sub_category
  text clearly states another silhouette get that value.
- length: bottoms and dresses only distinguish short vs. full length, so the
  0008 default ``hip`` (or ``waist``) is replaced by the type-derived value.

Retrieval documents of changed items are rebuilt with the same rules as
app/services/retrieval_document_service.py. The rules below are a frozen copy of
app/agents/garment_profile.py so this revision never changes behaviour later.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CANONICAL_FLAGS = frozenset({
    "movement", "outdoor", "rain", "sun", "work", "sport",
    "protection", "water_resistant", "heavy", "light",
})
FLAG_ALIASES = {
    "waterproof": "water_resistant", "water-resistant": "water_resistant",
    "water resistant": "water_resistant", "rainproof": "water_resistant",
    "breathable": "light", "lightweight": "light", "stretch": "movement",
    "stretchy": "movement", "athletic": "sport", "activewear": "sport",
    "office": "work", "formal_work": "work", "uv": "sun", "uv_protection": "sun",
    "sun_protection": "sun", "insulated": "heavy", "warm": "heavy",
    "windproof": "protection",
}
SILHOUETTE_KEYWORDS = (
    (5, ("oversized", "oversize", "baggy")),
    (4, ("relaxed", "loose", "wide", "boxy", "hoodie", "ống rộng", "dáng rộng")),
    (1, ("skinny", "tight", "bodycon", "bó sát")),
    (2, ("slim", "fitted", "ôm")),
)
SHORT_KEYWORDS = ("short", "mini", "skort", "bermuda", "capri", "cropped",
                  "quần đùi", "quần short", "váy ngắn")
MAX_TAGS = 20


def _loads(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return [str(entry) for entry in value] if isinstance(value, list) else []


def _text(*parts: Any) -> str:
    return " ".join(str(part).lower().strip() for part in parts if part)


def _normalize_flags(flags: list[str], tags: list[str]) -> tuple[list[str], list[str]]:
    canonical: list[str] = []
    new_tags = list(tags)
    for raw in flags:
        value = raw.strip().lower()
        if not value:
            continue
        value = FLAG_ALIASES.get(value, value)
        if value in CANONICAL_FLAGS:
            if value not in canonical:
                canonical.append(value)
        elif value not in new_tags and len(new_tags) < MAX_TAGS:
            new_tags.append(value)
    return canonical, new_tags


def _infer_silhouette(fit: Any, sub_category: Any) -> int:
    text = _text(fit, sub_category)
    for level, keywords in SILHOUETTE_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return level
    return 3


def _norm_token(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).strip().lower().split())


def _searchable_text(meta: dict[str, Any]) -> str:
    tokens: list[str] = []
    for field in ("category", "sub_category", "primary_color", "secondary_color",
                  "pattern", "material", "style", "fit", "length"):
        if meta.get(field):
            tokens.append(_norm_token(meta[field]))
    for field in ("season", "weather_suitability", "functional_flags", "free_text_tags"):
        tokens.extend(_norm_token(value) for value in meta.get(field) or [])
    tokens.append(f"formality_{meta.get('formality_level', 3)}")
    tokens.append(f"comfort_{meta.get('comfort_level', 3)}")
    tokens.append(f"silhouette_{meta.get('silhouette_level', 3)}")
    tokens.append(f"length_{meta.get('length', 'hip')}")
    return " ".join(dict.fromkeys(token for token in tokens if token))


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text(
        "SELECT id, category, sub_category, fit, silhouette_level, length, "
        "functional_flags, free_text_tags FROM wardrobe_items"
    )).mappings().all()

    for row in rows:
        flags = _loads(row["functional_flags"])
        tags = _loads(row["free_text_tags"])
        new_flags, new_tags = _normalize_flags(flags, tags)

        silhouette = row["silhouette_level"]
        if silhouette == 3:
            silhouette = _infer_silhouette(row["fit"], row["sub_category"])

        length = row["length"]
        if row["category"] in {"bottom", "dress"} and length not in {"cropped", "long"}:
            text = _text(row["sub_category"])
            length = "cropped" if any(keyword in text for keyword in SHORT_KEYWORDS) else "long"

        changed = {}
        if new_flags != flags:
            changed["functional_flags"] = new_flags
        if new_tags != tags:
            changed["free_text_tags"] = new_tags
        if silhouette != row["silhouette_level"]:
            changed["silhouette_level"] = silhouette
        if length != row["length"]:
            changed["length"] = length
        if not changed:
            continue

        params: dict[str, Any] = {"id": row["id"]}
        assignments = []
        for column, value in changed.items():
            assignments.append(f"{column} = :{column}")
            params[column] = json.dumps(value) if isinstance(value, list) else value
        connection.execute(
            sa.text(f"UPDATE wardrobe_items SET {', '.join(assignments)} WHERE id = :id"), params
        )

        document = connection.execute(
            sa.text("SELECT metadata_snapshot FROM wardrobe_retrieval_documents WHERE wardrobe_item_id = :id"),
            {"id": row["id"]},
        ).first()
        if document is None:
            continue
        snapshot = document[0]
        meta = json.loads(snapshot) if isinstance(snapshot, str) else dict(snapshot or {})
        meta.update(changed)
        connection.execute(
            sa.text(
                "UPDATE wardrobe_retrieval_documents SET metadata_snapshot = :meta, "
                "searchable_text = :text WHERE wardrobe_item_id = :id"
            ),
            {"id": row["id"], "meta": json.dumps(meta), "text": _searchable_text(meta)},
        )


def downgrade() -> None:
    # Data normalization only; the previous values were defaults or free-form
    # flags that the current schema rejects, so there is nothing to restore.
    pass
