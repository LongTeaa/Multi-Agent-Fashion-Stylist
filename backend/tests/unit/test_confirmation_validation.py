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
