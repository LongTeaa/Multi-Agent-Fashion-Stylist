from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.entities import WardrobeCategory
from app.schemas.ingestion import (
    CustomAttributesUpdate,
    DetectionConfirmationItem,
    IngestionConfirmRequest,
)


class TestConfirmationSchemaValidation:
    """Unit tests for IngestionConfirmRequest schema constraints."""

    def test_missing_confirmations_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            IngestionConfirmRequest.model_validate({})
        errors = exc_info.value.errors()
        assert any(err["loc"] == ("confirmations",) and err["type"] == "missing" for err in errors)

    def test_empty_confirmations_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            IngestionConfirmRequest.model_validate({"confirmations": []})
        errors = exc_info.value.errors()
        assert any(
            err["loc"] == ("confirmations",) and "too_short" in err["type"]
            for err in errors
        )

    def test_all_rejected_confirmations_raises_validation_error(self) -> None:
        payload = {
            "confirmations": [
                {"detection_id": "det-1", "accepted": False},
                {"detection_id": "det-2", "accepted": False},
            ]
        }
        with pytest.raises(ValidationError) as exc_info:
            IngestionConfirmRequest.model_validate(payload)
        assert "At least one detection must be accepted" in str(exc_info.value)

    def test_duplicate_detection_ids_raises_validation_error(self) -> None:
        payload = {
            "confirmations": [
                {"detection_id": "det-duplicate", "accepted": True},
                {"detection_id": "det-duplicate", "accepted": False},
            ]
        }
        with pytest.raises(ValidationError) as exc_info:
            IngestionConfirmRequest.model_validate(payload)
        assert "Duplicate detection_id found" in str(exc_info.value)

    def test_invalid_custom_category_raises_validation_error(self) -> None:
        payload = {
            "confirmations": [
                {
                    "detection_id": "det-1",
                    "accepted": True,
                    "custom_attributes": {"category": "not_a_valid_category"},
                }
            ]
        }
        with pytest.raises(ValidationError) as exc_info:
            IngestionConfirmRequest.model_validate(payload)
        errors = exc_info.value.errors()
        assert any("category" in str(err["loc"]) for err in errors)

    def test_formality_level_boundary_zero_raises_validation_error(self) -> None:
        payload = {
            "confirmations": [
                {
                    "detection_id": "det-1",
                    "accepted": True,
                    "custom_attributes": {"formality_level": 0},
                }
            ]
        }
        with pytest.raises(ValidationError) as exc_info:
            IngestionConfirmRequest.model_validate(payload)
        errors = exc_info.value.errors()
        assert any("formality_level" in str(err["loc"]) for err in errors)

    def test_formality_level_boundary_six_raises_validation_error(self) -> None:
        payload = {
            "confirmations": [
                {
                    "detection_id": "det-1",
                    "accepted": True,
                    "custom_attributes": {"formality_level": 6},
                }
            ]
        }
        with pytest.raises(ValidationError) as exc_info:
            IngestionConfirmRequest.model_validate(payload)
        errors = exc_info.value.errors()
        assert any("formality_level" in str(err["loc"]) for err in errors)

    def test_valid_confirmation_succeeds(self) -> None:
        payload = {
            "idempotency_token": "token-123",
            "confirmations": [
                {
                    "detection_id": "det-1",
                    "accepted": True,
                    "custom_attributes": {
                        "category": "top",
                        "formality_level": 3,
                        "primary_color": "navy",
                    },
                },
                {"detection_id": "det-2", "accepted": False},
            ],
        }
        req = IngestionConfirmRequest.model_validate(payload)
        assert len(req.confirmations) == 2
        assert req.confirmations[0].accepted is True
        assert req.confirmations[0].custom_attributes.category == WardrobeCategory.TOP
        assert req.confirmations[1].accepted is False

    def test_submitting_shoes_category_raises_validation_error(self) -> None:
        payload = {
            "confirmations": [
                {
                    "detection_id": "det-1",
                    "accepted": True,
                    "custom_attributes": {"category": "shoes"},
                }
            ]
        }
        with pytest.raises(ValidationError) as exc_info:
            IngestionConfirmRequest.model_validate(payload)
        errors = exc_info.value.errors()
        assert any("category" in str(err["loc"]) for err in errors)

    def test_submitting_footwear_category_succeeds(self) -> None:
        payload = {
            "confirmations": [
                {
                    "detection_id": "det-1",
                    "accepted": True,
                    "custom_attributes": {"category": "footwear"},
                }
            ]
        }
        req = IngestionConfirmRequest.model_validate(payload)
        assert req.confirmations[0].custom_attributes.category == WardrobeCategory.FOOTWEAR


class TestConfirmIngestionBatchServiceValidation:
    """Service-level validation tests for confirm_ingestion_batch."""

    def test_confirm_batch_rejects_missing_or_unknown_category(
        self,
        migrated_database: tuple[object, object],
    ) -> None:
        from datetime import timedelta
        from uuid import uuid4
        from sqlmodel import Session
        from app.models.entities import (
            IngestionBatch,
            IngestionDetection,
            IngestionStatus,
            DetectionStatus,
            User,
            utc_now,
        )
        from app.services.ingestion_service import confirm_ingestion_batch
        from app.schemas.common import ValidationError as AppValidationError

        _, engine = migrated_database
        user_id = str(uuid4())
        batch_id = str(uuid4())
        det_id = str(uuid4())

        with Session(engine) as session:
            user = User(id=user_id, email=f"{user_id}@example.com", name="Test User")
            session.add(user)
            session.flush()

            batch = IngestionBatch(
                id=batch_id,
                user_id=user_id,
                status=IngestionStatus.NEEDS_REVIEW,
                expires_at=utc_now() + timedelta(hours=24),
            )
            session.add(batch)
            session.flush()

            detection = IngestionDetection(
                id=det_id,
                user_id=user_id,
                ingestion_batch_id=batch_id,
                bounding_box=(0.0, 0.0, 1.0, 1.0),
                proposed_attributes={"category": "unknown"},
                field_confidence={"category": 0.3},
                status=DetectionStatus.PROPOSED,
            )
            session.add(detection)
            session.commit()

            conf = DetectionConfirmationItem(
                detection_id=det_id,
                accepted=True,
                custom_attributes=None,
            )

            with pytest.raises(AppValidationError) as exc_info:
                confirm_ingestion_batch(
                    session=session,
                    batch_id=batch_id,
                    user_id=user_id,
                    confirmations=[conf],
                )
            assert "Danh mục trang phục là bắt buộc" in exc_info.value.message

    def test_confirm_batch_sub_category_defaults_to_category_instead_of_clothing(
        self,
        migrated_database: tuple[object, object],
    ) -> None:
        from datetime import timedelta
        from uuid import uuid4
        from sqlmodel import Session
        from app.models.entities import (
            IngestionBatch,
            IngestionDetection,
            IngestionStatus,
            DetectionStatus,
            User,
            WardrobeCategory,
            WardrobeItem,
            utc_now,
        )
        from app.services.ingestion_service import confirm_ingestion_batch

        _, engine = migrated_database
        user_id = str(uuid4())
        batch_id = str(uuid4())
        det_id = str(uuid4())

        with Session(engine) as session:
            user = User(id=user_id, email=f"{user_id}@example.com", name="Test User")
            session.add(user)
            session.flush()

            batch = IngestionBatch(
                id=batch_id,
                user_id=user_id,
                status=IngestionStatus.NEEDS_REVIEW,
                expires_at=utc_now() + timedelta(hours=24),
            )
            session.add(batch)
            session.flush()

            detection = IngestionDetection(
                id=det_id,
                user_id=user_id,
                ingestion_batch_id=batch_id,
                bounding_box=(0.0, 0.0, 1.0, 1.0),
                proposed_attributes={"category": "bottom", "sub_category": "clothing"},
                field_confidence={"category": 0.9},
                status=DetectionStatus.PROPOSED,
            )
            session.add(detection)
            session.commit()

            conf = DetectionConfirmationItem(
                detection_id=det_id,
                accepted=True,
                custom_attributes=None,
            )

            item_ids = confirm_ingestion_batch(
                session=session,
                batch_id=batch_id,
                user_id=user_id,
                confirmations=[conf],
            )
            assert len(item_ids) == 1
            item = session.get(WardrobeItem, item_ids[0])
            assert item is not None
            assert item.category == WardrobeCategory.BOTTOM
            # Should default to category 'bottom', NOT 'clothing'
            assert item.sub_category == "bottom"
