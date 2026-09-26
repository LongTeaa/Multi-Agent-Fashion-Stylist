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


class TestLiveGeminiVisionProviderNormalization:
    """Test normalization and error handling on the live GeminiVisionProvider implementation."""

    def test_gemini_vision_normalizes_markdown_json_and_clamps_confidences(self) -> None:
        import httpx
        from pydantic import SecretStr
        from app.services.gemini_provider import GeminiVisionProvider

        gemini_response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '```json\n{\n'
                                    '  "attributes": {\n'
                                    '    "category": "top",\n'
                                    '    "sub_category": "t-shirt",\n'
                                    '    "primary_color": "white",\n'
                                    '    "pattern": "solid",\n'
                                    '    "material": "cotton",\n'
                                    '    "style": "casual",\n'
                                    '    "fit": "regular",\n'
                                    '    "formality_level": 2,\n'
                                    '    "season": ["summer"],\n'
                                    '    "weather_suitability": ["warm"],\n'
                                    '    "functional_flags": [],\n'
                                    '    "free_text_tags": ["basic"]\n'
                                    '  },\n'
                                    '  "field_confidence": {\n'
                                    '    "category": 1.5,\n'
                                    '    "sub_category": 0.85,\n'
                                    '    "material": -0.3\n'
                                    '  },\n'
                                    '  "quality_warnings": []\n'
                                    '}\n```'
                                )
                            }
                        ]
                    }
                }
            ]
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=gemini_response)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        provider = GeminiVisionProvider(
            api_key=SecretStr("mock-key"),
            model="gemini-1.5-flash",
            client=client,
        )

        dummy_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00"
        result = provider.extract_attributes(dummy_jpeg)

        assert result.attributes["category"] == "top"
        assert result.attributes["sub_category"] == "t-shirt"
        # Bounded confidence clamping invariant:
        assert result.field_confidence["category"] == 1.0  # Clamped from 1.5
        assert result.field_confidence["sub_category"] == 0.85
        assert result.field_confidence["material"] == 0.0  # Clamped from -0.3

    def test_gemini_vision_malformed_response_raises_provider_error(self) -> None:
        import httpx
        from pydantic import SecretStr
        from app.services.gemini_provider import GeminiVisionProvider

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": [{"text": "not-valid-json"}]}}]},
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        provider = GeminiVisionProvider(
            api_key=SecretStr("mock-key"),
            model="gemini-1.5-flash",
            client=client,
        )
        dummy_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00"
        with pytest.raises(ProviderError):
            provider.extract_attributes(dummy_jpeg)

    def test_gemini_vision_http_error_raises_provider_error(self) -> None:
        import httpx
        from pydantic import SecretStr
        from app.services.gemini_provider import GeminiVisionProvider

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="Internal server error from Gemini")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        provider = GeminiVisionProvider(
            api_key=SecretStr("mock-key"),
            model="gemini-1.5-flash",
            client=client,
        )
        dummy_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00"
        with pytest.raises(ProviderError):
            provider.extract_attributes(dummy_jpeg)


class TestFashionDomainVisionIngestion:
    """Rigorous verification for Phase 2: AI Vision Assistant & Digitization Pipeline."""

    def test_gemini_vision_prompt_contains_fashion_domain_guidelines(self) -> None:
        import httpx
        from pydantic import SecretStr
        from app.services.gemini_provider import GeminiVisionProvider

        captured_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": (
                                            '{\n'
                                            '  "attributes": {\n'
                                            '    "category": "top",\n'
                                            '    "comfort_level": 4,\n'
                                            '    "silhouette_level": 3,\n'
                                            '    "length": "hip",\n'
                                            '    "functional_flags": ["light"]\n'
                                            '  },\n'
                                            '  "field_confidence": {},\n'
                                            '  "quality_warnings": []\n'
                                            '}'
                                        )
                                    }
                                ]
                            }
                        }
                    ]
                },
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        provider = GeminiVisionProvider(
            api_key=SecretStr("mock-key"),
            model="gemini-1.5-flash",
            client=client,
        )
        dummy_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00"
        provider.extract_attributes(dummy_jpeg)

        assert len(captured_requests) == 1
        sent_body = captured_requests[0].read().decode("utf-8")
        # Invariants: Prompt must guide Gemini on fashion domain metrics
        assert "comfort_level" in sent_body
        assert "silhouette_level" in sent_body
        assert "length" in sent_body
        assert "functional_flags" in sent_body
        assert "cropped" in sent_body
        assert "waist" in sent_body
        assert "hip" in sent_body
        assert "long" in sent_body
        assert "work" in sent_body
        assert "sport" in sent_body
        assert "breathability" in sent_body or "cotton" in sent_body

    def test_gemini_vision_extracts_and_normalizes_oversized_tshirt(self) -> None:
        import httpx
        from pydantic import SecretStr
        from app.services.gemini_provider import GeminiVisionProvider

        gemini_response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '{\n'
                                    '  "attributes": {\n'
                                    '    "category": "top",\n'
                                    '    "sub_category": "t-shirt",\n'
                                    '    "primary_color": "black",\n'
                                    '    "pattern": "graphic",\n'
                                    '    "material": "cotton",\n'
                                    '    "style": "streetwear",\n'
                                    '    "fit": "oversized",\n'
                                    '    "formality_level": 1,\n'
                                    '    "comfort_level": 5,\n'
                                    '    "silhouette_level": 5,\n'
                                    '    "length": "hip",\n'
                                    '    "season": ["summer"],\n'
                                    '    "weather_suitability": ["hot", "warm"],\n'
                                    '    "functional_flags": ["light", "movement"],\n'
                                    '    "free_text_tags": ["oversized tee"]\n'
                                    '  },\n'
                                    '  "field_confidence": {\n'
                                    '    "category": 0.98,\n'
                                    '    "comfort_level": 0.95,\n'
                                    '    "silhouette_level": 0.92,\n'
                                    '    "length": 0.94\n'
                                    '  },\n'
                                    '  "quality_warnings": []\n'
                                    '}'
                                )
                            }
                        ]
                    }
                }
            ]
        }

        client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=gemini_response)))
        provider = GeminiVisionProvider(api_key=SecretStr("mock-key"), model="gemini-1.5-flash", client=client)
        dummy_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00"
        result = provider.extract_attributes(dummy_jpeg)

        attrs = result.attributes
        # Acceptance Criterion: Oversized cotton t-shirt suggests comfort >= 4 and silhouette >= 4
        assert attrs["comfort_level"] >= 4
        assert attrs["silhouette_level"] >= 4
        assert attrs["length"] == "hip"
        assert attrs["formality_level"] == 1
        assert "light" in attrs["functional_flags"]
        assert "movement" in attrs["functional_flags"]
        assert result.field_confidence["comfort_level"] == 0.95
        assert result.field_confidence["silhouette_level"] == 0.92

    def test_gemini_vision_extracts_and_normalizes_fitted_formal_shirt(self) -> None:
        import httpx
        from pydantic import SecretStr
        from app.services.gemini_provider import GeminiVisionProvider

        gemini_response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '{\n'
                                    '  "attributes": {\n'
                                    '    "category": "top",\n'
                                    '    "sub_category": "shirt",\n'
                                    '    "primary_color": "white",\n'
                                    '    "pattern": "solid",\n'
                                    '    "material": "cotton_poplin",\n'
                                    '    "style": "formal",\n'
                                    '    "fit": "slim",\n'
                                    '    "formality_level": 5,\n'
                                    '    "comfort_level": 2,\n'
                                    '    "silhouette_level": 1,\n'
                                    '    "length": "hip",\n'
                                    '    "season": ["all_year"],\n'
                                    '    "weather_suitability": ["mild"],\n'
                                    '    "functional_flags": ["protection"]\n'
                                    '  },\n'
                                    '  "field_confidence": {\n'
                                    '    "category": 0.99,\n'
                                    '    "formality_level": 0.98,\n'
                                    '    "silhouette_level": 0.95\n'
                                    '  },\n'
                                    '  "quality_warnings": []\n'
                                    '}'
                                )
                            }
                        ]
                    }
                }
            ]
        }

        client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=gemini_response)))
        provider = GeminiVisionProvider(api_key=SecretStr("mock-key"), model="gemini-1.5-flash", client=client)
        dummy_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00"
        result = provider.extract_attributes(dummy_jpeg)

        attrs = result.attributes
        # Acceptance Criterion: Fitted formal dress shirt suggests high formality (>=4) and fitted silhouette (<=2)
        assert attrs["formality_level"] >= 4
        assert attrs["silhouette_level"] <= 2
        assert attrs["comfort_level"] <= 3
        assert attrs["length"] == "hip"

    def test_gemini_vision_clamps_out_of_bounds_and_invalid_taxonomy(self) -> None:
        import httpx
        from pydantic import SecretStr
        from app.services.gemini_provider import GeminiVisionProvider

        gemini_response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '{\n'
                                    '  "attributes": {\n'
                                    '    "category": "top",\n'
                                    '    "comfort_level": 99,\n'
                                    '    "silhouette_level": -5,\n'
                                    '    "length": "invalid_super_length",\n'
                                    '    "functional_flags": ["  MOVEMENT  ", "", "  Outdoor  "]\n'
                                    '  },\n'
                                    '  "field_confidence": {},\n'
                                    '  "quality_warnings": []\n'
                                    '}'
                                )
                            }
                        ]
                    }
                }
            ]
        }

        client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=gemini_response)))
        provider = GeminiVisionProvider(api_key=SecretStr("mock-key"), model="gemini-1.5-flash", client=client)
        dummy_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00"
        result = provider.extract_attributes(dummy_jpeg)

        attrs = result.attributes
        # Out-of-bounds comfort clamped to 5
        assert attrs["comfort_level"] == 5
        # Negative silhouette clamped to 1
        assert attrs["silhouette_level"] == 1
        # Invalid length falls back to standard "hip"
        assert attrs["length"] == "hip"
        # Functional flags are trimmed, lowercased and filtered
        assert attrs["functional_flags"] == ["movement", "outdoor"]
        # Default confidences supplied
        assert result.field_confidence["comfort_level"] == 0.85
        assert result.field_confidence["silhouette_level"] == 0.85
        assert result.field_confidence["length"] == 0.85

    def test_fake_vision_provider_specialized_scenarios(self) -> None:
        p_tshirt = FakeVisionProvider(scenario="oversized_cotton_tshirt")
        res_tshirt = p_tshirt.extract_attributes(b"any")
        assert res_tshirt.attributes["comfort_level"] == 5
        assert res_tshirt.attributes["silhouette_level"] == 5
        assert res_tshirt.attributes["length"] == "hip"
        assert "light" in res_tshirt.attributes["functional_flags"]

        p_shirt = FakeVisionProvider(scenario="fitted_formal_dress_shirt")
        res_shirt = p_shirt.extract_attributes(b"any")
        assert res_shirt.attributes["formality_level"] == 5
        assert res_shirt.attributes["silhouette_level"] == 1
        assert res_shirt.attributes["comfort_level"] == 2

        p_crop = FakeVisionProvider(scenario="cropped_knit_top")
        res_crop = p_crop.extract_attributes(b"any")
        assert res_crop.attributes["length"] == "cropped"
        assert res_crop.attributes["comfort_level"] == 4
        assert res_crop.attributes["silhouette_level"] == 2

        p_wide = FakeVisionProvider(scenario="wide_leg_trousers")
        res_wide = p_wide.extract_attributes(b"any")
        assert res_wide.attributes["length"] == "long"
        assert res_wide.attributes["silhouette_level"] == 4
        assert res_wide.attributes["comfort_level"] == 4

    def test_ingestion_end_to_end_preserves_fashion_attributes_without_loss(
        self,
        migrated_database: tuple[object, object],
        tmp_path: Path,
    ) -> None:
        """Verify seamless pipeline: crop -> IngestionDetection -> Review API -> WardrobeItem."""
        _, engine = migrated_database
        user_id = str(uuid4())

        from app.models.entities import WardrobeItem
        from app.repositories.object_storage import LocalObjectStorage, StorageBuckets
        from app.services.ingestion_service import (
            confirm_ingestion_batch,
            create_ingestion_batch,
            get_batch_review,
            process_ingestion_batch,
        )
        from app.schemas.ingestion import (
            DetectionConfirmationItem,
            IngestionConfirmRequest,
        )
        from app.services.fakes.vision_fakes import FakeDetector

        buckets = StorageBuckets(
            wardrobe="wardrobe-private",
            thumbnails="wardrobe-thumbnails",
            tryon="tryon-private",
        )
        storage = LocalObjectStorage(root=tmp_path / "storage", buckets=buckets)

        import io
        from PIL import Image

        buf = io.BytesIO()
        img = Image.new("RGB", (100, 100), color=(240, 240, 240))
        img.save(buf, format="JPEG")
        dummy_jpeg = buf.getvalue()

        with Session(engine) as session:
            user = User(id=user_id, email=f"{user_id}@example.com")
            session.add(user)
            session.commit()

            # Create batch using standard ingestion entrypoint
            batch = create_ingestion_batch(
                session=session,
                storage=storage,
                user_id=user_id,
                raw_files=[("photo.jpg", dummy_jpeg)],
            )
            batch_id = batch.id

            # Process ingestion with oversized cotton t-shirt scenario
            detector = FakeDetector(mode="single_item")
            vision_provider = FakeVisionProvider(scenario="oversized_cotton_tshirt")

            updated_batch = process_ingestion_batch(
                session=session,
                storage=storage,
                detector=detector,
                vision_provider=vision_provider,
                batch_id=batch_id,
                user_id=user_id,
            )
            assert updated_batch.status == IngestionStatus.NEEDS_REVIEW

            # Verify Detection in Review API response
            review = get_batch_review(session=session, batch_id=batch_id, user_id=user_id)
            assert len(review.detections) == 1
            det_item = review.detections[0]
            assert det_item.attributes["comfort_level"] == 5
            assert det_item.attributes["silhouette_level"] == 5
            assert det_item.attributes["length"] == "hip"
            assert "light" in det_item.attributes["functional_flags"]
            assert "movement" in det_item.attributes["functional_flags"]
            assert det_item.field_confidence["comfort_level"] >= 0.70
            assert det_item.field_confidence["silhouette_level"] >= 0.70

            # User confirms AI proposal without manual override (custom_attributes=None)
            confirmations = [
                DetectionConfirmationItem(
                    detection_id=det_item.detection_id,
                    accepted=True,
                    custom_attributes=None,
                )
            ]
            confirm_ingestion_batch(
                session=session,
                batch_id=batch_id,
                user_id=user_id,
                confirmations=confirmations,
            )

            # Query persisted WardrobeItem
            from sqlmodel import select
            items = session.exec(select(WardrobeItem).where(WardrobeItem.user_id == user_id)).all()
            assert len(items) == 1
            saved_item = items[0]
            assert saved_item.category == WardrobeCategory.TOP
            assert saved_item.comfort_level == 5
            assert saved_item.silhouette_level == 5
            assert saved_item.length == "hip"
            assert "light" in saved_item.functional_flags
            assert "movement" in saved_item.functional_flags
