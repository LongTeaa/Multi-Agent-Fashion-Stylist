from __future__ import annotations

from io import BytesIO
from pathlib import Path
from statistics import quantiles
from time import perf_counter
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, select

from app.core.dependencies import (
    get_db_session,
    get_detector,
    get_image_provider,
    get_object_storage,
    get_vision_provider,
)
from app.main import app
from app.models.entities import Rating, TryOnRender, WardrobeItem
from app.repositories.object_storage import LocalObjectStorage, StorageBuckets
from app.services.fakes.vision_fakes import FakeDetector, FakeVisionProvider


def _image_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (300, 300), (200, 100, 50)).save(output, format="JPEG")
    return output.getvalue()


def _override_session(engine: object):
    def override_db():
        with Session(engine) as session:
            yield session

    return override_db


def test_complete_offline_mvp_acceptance_flow(
    migrated_database: tuple[object, object],
    tmp_path: Path,
) -> None:
    """Upload -> confirm -> retrieve/chat -> persist -> actions -> rating -> fallback."""
    _, engine = migrated_database
    user_id = str(uuid4())
    other_user_id = str(uuid4())
    storage = LocalObjectStorage(
        root=tmp_path / "storage",
        buckets=StorageBuckets(
            wardrobe="wardrobe-private",
            thumbnails="wardrobe-thumbnails",
            tryon="tryon-private",
        ),
    )
    detector = FakeDetector(mode="multi_item")

    app.dependency_overrides[get_db_session] = lambda: Session(engine)
    app.dependency_overrides[get_object_storage] = lambda: storage
    app.dependency_overrides[get_detector] = lambda: detector
    app.dependency_overrides[get_vision_provider] = lambda: FakeVisionProvider()
    app.dependency_overrides[get_image_provider] = lambda: None

    try:
        client = TestClient(app)
        headers = {"X-User-Id": user_id}

        upload = client.post(
            "/api/v1/ingestions",
            headers=headers,
            files=[("images[]", ("outfit.jpg", _image_bytes(), "image/jpeg"))],
        )
        assert upload.status_code == 202, upload.text
        batch_id = upload.json()["data"]["batch_id"]
        review = client.get(f"/api/v1/ingestions/{batch_id}", headers=headers)
        detections = review.json()["data"]["detections"]
        assert review.status_code == 200 and len(detections) == 2
        confirm = client.post(
            f"/api/v1/ingestions/{batch_id}/confirm",
            headers=headers,
            json={
                "idempotency_token": str(uuid4()),
                "confirmations": [
                    {
                        "detection_id": detections[0]["detection_id"],
                        "accepted": True,
                        "custom_attributes": {
                            "category": "top",
                            "sub_category": "polo",
                            "primary_color": "white",
                            "style": "smart_casual",
                            "formality_level": 3,
                            "weather_suitability": ["cool"],
                        },
                    },
                    {
                        "detection_id": detections[1]["detection_id"],
                        "accepted": True,
                        "custom_attributes": {
                            "category": "bottom",
                            "sub_category": "chinos",
                            "primary_color": "navy",
                            "style": "smart_casual",
                            "formality_level": 3,
                            "weather_suitability": ["cool"],
                        },
                    },
                ],
            },
        )
        assert confirm.status_code == 200

        detector.set_mode("single_item")
        shoe_upload = client.post(
            "/api/v1/ingestions",
            headers=headers,
            files=[("images[]", ("shoes.jpg", _image_bytes(), "image/jpeg"))],
        )
        shoe_batch_id = shoe_upload.json()["data"]["batch_id"]
        shoe_review = client.get(
            f"/api/v1/ingestions/{shoe_batch_id}", headers=headers
        ).json()["data"]
        shoe_confirm = client.post(
            f"/api/v1/ingestions/{shoe_batch_id}/confirm",
            headers=headers,
            json={
                "idempotency_token": str(uuid4()),
                "confirmations": [
                    {
                        "detection_id": shoe_review["detections"][0]["detection_id"],
                        "accepted": True,
                        "custom_attributes": {
                            "category": "footwear",
                            "sub_category": "sneakers",
                            "primary_color": "white",
                            "style": "minimalist",
                            "formality_level": 2,
                            "weather_suitability": ["cool"],
                        },
                    }
                ],
            },
        )
        assert shoe_confirm.status_code == 200

        wardrobe = client.get("/api/v1/wardrobe/items", headers=headers)
        assert wardrobe.status_code == 200
        assert wardrobe.json()["data"]["total"] == 3

        session_id = str(uuid4())
        chat_headers = {**headers, "X-Client-Session-Id": session_id}
        chat_durations: list[float] = []
        eligible_response: dict[str, object] | None = None
        for _ in range(10):
            started = perf_counter()
            response = client.post(
                "/api/v1/stylist/chat",
                headers=chat_headers,
                json={
                    "query": "Tối nay tôi đi cafe với bạn, trời mát, nên mặc gì?",
                    "client_session_id": session_id,
                },
            )
            chat_durations.append(perf_counter() - started)
            assert response.status_code == 200
            data = response.json()["data"]
            assert data["recommendations"]
            eligible_response = data
            if data["feedback_prompt_eligible"]:
                break

        assert eligible_response is not None
        assert eligible_response["feedback_prompt_eligible"] is True
        assert max(chat_durations) <= 5.0
        recommendation = eligible_response["recommendations"][0]
        outfit_id = recommendation["outfit_id"]
        active_ids = {
            item["id"] for item in wardrobe.json()["data"]["items"] if item["is_active"]
        }
        assert {item["item_id"] for item in recommendation["items"]} <= active_ids

        assert client.get(f"/api/v1/outfits/{outfit_id}", headers=headers).status_code == 200
        assert client.put(
            f"/api/v1/outfits/{outfit_id}/bookmark",
            headers=headers,
            json={"is_bookmarked": True},
        ).status_code == 200
        worn = client.post(
            f"/api/v1/outfits/{outfit_id}/worn",
            headers=headers,
            json={"idempotency_key": str(uuid4())},
        )
        assert worn.status_code == 200 and worn.json()["data"]["times_worn"] == 1

        feedback_target = eligible_response["feedback_target_outfit_id"]
        rating = client.put(
            f"/api/v1/outfits/{feedback_target}/rating",
            headers=chat_headers,
            json={"stars": 5, "source": "prompted", "client_session_id": session_id},
        )
        assert rating.status_code == 200 and rating.json()["data"]["stars"] == 5

        tryon_durations_ms: list[int] = []
        tryon_data: dict[str, object] = {}
        for _ in range(20):
            tryon = client.post(
                "/api/v1/tryons", headers=headers, json={"outfit_id": outfit_id}
            )
            assert tryon.status_code == 200
            tryon_data = tryon.json()["data"]
            assert tryon_data["fallback_used"] is True
            assert tryon_data["render_kind"] == "moodboard"
            tryon_durations_ms.append(int(tryon_data["duration_ms"]))
        tryon_p95_ms = quantiles(tryon_durations_ms, n=20)[18]
        print({"moodboard_fallback_p95_ms": round(tryon_p95_ms, 3)})
        assert tryon_p95_ms <= 10_000

        assert client.get(
            f"/api/v1/outfits/{outfit_id}", headers={"X-User-Id": other_user_id}
        ).status_code == 404
        assert client.get(
            tryon_data["image_url"], headers={"X-User-Id": other_user_id}
        ).status_code == 403

        with Session(engine) as session:
            assert len(session.exec(select(WardrobeItem)).all()) == 3
            assert len(session.exec(select(Rating)).all()) == 1
            assert len(session.exec(select(TryOnRender)).all()) == 20
    finally:
        app.dependency_overrides.clear()
