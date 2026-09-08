from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlmodel import Session

from app.models.entities import (
    IngestionBatch,
    IngestionStatus,
    InputKind,
    User,
    WardrobeCategory,
    utc_now,
)
from app.schemas.common import ProviderError
from app.services.classifier import classify_scene, update_batch_classification
from app.services.fakes.vision_fakes import FakeDetector, FakeVisionProvider
from app.services.providers import DetectorProtocol, VisionProviderProtocol


class TestProviderProtocolsAndFakes:
    def test_protocol_conformance(self) -> None:
        detector = FakeDetector()
        vision_provider = FakeVisionProvider()

        assert isinstance(detector, DetectorProtocol)
        assert isinstance(vision_provider, VisionProviderProtocol)

    def test_classify_all_four_input_kinds(self) -> None:
        dummy_bytes = b"fake_image_bytes"

        # 1. single_item
        det_single = FakeDetector(mode="single_item")
        res_single = classify_scene(det_single, dummy_bytes)
        assert res_single.input_kind == InputKind.SINGLE_ITEM
        assert len(res_single.boxes) == 1
        assert res_single.boxes[0].label == "top"
        assert res_single.boxes[0].confidence >= 0.90

        # 2. multi_item
        det_multi = FakeDetector(mode="multi_item")
        res_multi = classify_scene(det_multi, dummy_bytes)
        assert res_multi.input_kind == InputKind.MULTI_ITEM
        assert len(res_multi.boxes) == 2
        labels = [box.label for box in res_multi.boxes]
        assert "top" in labels
        assert "bottom" in labels

        # 3. worn_outfit
        det_worn = FakeDetector(mode="worn_outfit")
        res_worn = classify_scene(det_worn, dummy_bytes)
        assert res_worn.input_kind == InputKind.WORN_OUTFIT
        assert len(res_worn.boxes) >= 2

        # 4. cluttered
        det_cluttered = FakeDetector(mode="cluttered")
        res_cluttered = classify_scene(det_cluttered, dummy_bytes)
        assert res_cluttered.input_kind == InputKind.CLUTTERED
        assert len(res_cluttered.quality_warnings) > 0

    def test_declared_kind_fallback(self) -> None:
        dummy_bytes = b"fake_image_bytes"
        det_unknown = FakeDetector(mode="unknown")

        res_declared = classify_scene(
            det_unknown,
            dummy_bytes,
            declared_input_kind=InputKind.MULTI_ITEM,
        )
        assert res_declared.input_kind == InputKind.MULTI_ITEM

    def test_vision_attributes_normalization_and_enums(self) -> None:
        provider = FakeVisionProvider(scenario="golden_polo")
        result = provider.extract_attributes(b"crop_bytes")

        attrs = result.attributes
        # Check WardrobeCategory enum conformance
        assert WardrobeCategory(attrs["category"]) == WardrobeCategory.TOP
        assert attrs["sub_category"] == "polo"
        assert attrs["primary_color"] == "white"
        assert attrs["style"] == "smart_casual"
        assert 1 <= attrs["formality_level"] <= 5
        assert isinstance(attrs["season"], list)
        assert isinstance(attrs["weather_suitability"], list)

        # Check field confidence values are bounded in [0.0, 1.0]
        for field_name, conf in result.field_confidence.items():
            assert 0.0 <= conf <= 1.0

    def test_low_confidence_flagging(self) -> None:
        provider = FakeVisionProvider(scenario="low_confidence")
        result = provider.extract_attributes(b"crop_bytes")

        low_conf_fields = {
            field: conf
            for field, conf in result.field_confidence.items()
            if conf < 0.70
        }
        # Invariant: Fields with confidence < 0.70 must be detected and flagged
        assert len(low_conf_fields) > 0
        assert "material" in low_conf_fields
        assert "pattern" in low_conf_fields
        assert low_conf_fields["material"] < 0.70

    def test_error_modes_timeout_and_provider_failure(self) -> None:
        detector_timeout = FakeDetector(mode="timeout")
        with pytest.raises(TimeoutError):
            detector_timeout.detect(b"bytes")

        detector_error = FakeDetector(mode="provider_error")
        with pytest.raises(ProviderError) as exc_info:
            detector_error.detect(b"bytes")
        assert exc_info.value.code == "PROVIDER_ERROR"
        assert "Dịch vụ AI tạm thời không khả dụng" in exc_info.value.message

        vision_timeout = FakeVisionProvider(scenario="timeout")
        with pytest.raises(TimeoutError):
            vision_timeout.extract_attributes(b"bytes")

        vision_error = FakeVisionProvider(scenario="provider_error")
        with pytest.raises(ProviderError) as exc_info2:
            vision_error.extract_attributes(b"bytes")
        assert exc_info2.value.code == "PROVIDER_ERROR"


class TestDatabaseBatchClassificationUpdate:
    def test_update_batch_classification(
        self,
        migrated_database: tuple[object, object],
    ) -> None:
        _, engine = migrated_database
        user_id = str(uuid4())
        batch_id = str(uuid4())
        now = utc_now()

        with Session(engine) as session:
            session.add(User(id=user_id))
            session.flush()
            batch = IngestionBatch(
                id=batch_id,
                user_id=user_id,
                input_kind=InputKind.UNKNOWN,
                status=IngestionStatus.PROCESSING,
                quality_warnings=[],
                created_at=now,
                expires_at=now + timedelta(hours=24),
            )
            session.add(batch)
            session.commit()

            detector = FakeDetector(mode="multi_item")
            detection_result = classify_scene(detector, b"test_bytes")

            updated_batch = update_batch_classification(
                session=session,
                batch_id=batch_id,
                detection_result=detection_result,
            )

            assert updated_batch.input_kind == InputKind.MULTI_ITEM

            # Verify persistent read from fresh query
            refreshed = session.get(IngestionBatch, batch_id)
            assert refreshed is not None
            assert refreshed.input_kind == InputKind.MULTI_ITEM
