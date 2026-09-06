from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.models import IngestionDetection, User, UserPreference, WardrobeItem


def test_entity_ids_and_timestamps_use_normative_formats() -> None:
    user = User()

    assert str(UUID(user.id)) == user.id
    assert user.created_at.tzinfo is not None
    assert user.created_at.utcoffset() == timezone.utc.utcoffset(user.created_at)


def test_json_defaults_are_not_shared_between_models() -> None:
    first = UserPreference(user_id="user-1")
    second = UserPreference(user_id="user-2")

    first.styles.append("minimalist")
    first.learned_feature_weights["version"] = 2

    assert second.styles == []
    assert second.learned_feature_weights == {"version": 1, "weights": {}}


@pytest.mark.parametrize(
    "formality_level",
    [0, 6],
)
def test_wardrobe_formality_bounds_are_validated(formality_level: int) -> None:
    with pytest.raises(ValidationError):
        WardrobeItem.model_validate(
            {
                "user_id": "user-1",
                "category": "top",
                "sub_category": "polo",
                "primary_color": "white",
                "pattern": "solid",
                "material": "cotton",
                "style": "smart_casual",
                "fit": "regular",
                "formality_level": formality_level,
            }
        )


def test_detection_bounding_box_and_confidence_are_bounded() -> None:
    with pytest.raises(ValidationError):
        IngestionDetection.model_validate(
            {
                "user_id": "user-1",
                "ingestion_batch_id": "batch-1",
                "bounding_box": [0.0, 0.0, 1.1, 1.0],
                "proposed_attributes": {},
                "field_confidence": {"category": 1.2},
            }
        )
