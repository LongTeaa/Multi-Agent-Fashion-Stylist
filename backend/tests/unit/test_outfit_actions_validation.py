from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

import pytest
from pydantic import ValidationError

from app.models.entities import RatingSource
from app.schemas.feedback import DismissPromptRequest
from app.schemas.outfits import (
    BookmarkOutfitRequest,
    OutfitRatingRequest,
    WornOutfitRequest,
)
from app.schemas.stylist import StylistChatRequest


class TestOutfitActionsRequestValidation:
    """Validate strict contract rules on request schemas."""

    def test_worn_outfit_requires_valid_uuid_v4_idempotency_key(self) -> None:
        valid_v4 = str(uuid.uuid4())
        req = WornOutfitRequest(idempotency_key=valid_v4)
        assert req.idempotency_key == valid_v4

        # Reject UUID v1
        uuid_v1 = str(uuid.uuid1())
        with pytest.raises(ValidationError) as exc_info:
            WornOutfitRequest(idempotency_key=uuid_v1)
        assert "idempotency_key must be a valid UUID v4" in str(exc_info.value)

        # Reject non-UUID 36 character string
        with pytest.raises(ValidationError) as exc_info:
            WornOutfitRequest(idempotency_key="a" * 36)
        assert "idempotency_key must be a valid UUID v4" in str(exc_info.value)

        # Reject non-UUID random string
        with pytest.raises(ValidationError) as exc_info:
            WornOutfitRequest(idempotency_key="invalid-key")
        assert "idempotency_key must be a valid UUID v4" in str(exc_info.value)

    def test_worn_outfit_requires_timezone_aware_utc_worn_at(self) -> None:
        valid_v4 = str(uuid.uuid4())
        now_utc = datetime.now(timezone.utc)
        req = WornOutfitRequest(idempotency_key=valid_v4, worn_at=now_utc)
        assert req.worn_at == now_utc

        # Reject naive datetime (no timezone)
        naive_dt = datetime(2026, 9, 14, 10, 0, 0)
        with pytest.raises(ValidationError) as exc_info:
            WornOutfitRequest(idempotency_key=valid_v4, worn_at=naive_dt)
        assert "worn_at must be a timezone-aware UTC datetime" in str(exc_info.value)

        # Reject non-UTC timezone (e.g. UTC+7)
        vn_tz = timezone(timedelta(hours=7))
        vn_dt = datetime.now(vn_tz)
        with pytest.raises(ValidationError) as exc_info:
            WornOutfitRequest(idempotency_key=valid_v4, worn_at=vn_dt)
        assert "worn_at must be a timezone-aware UTC datetime" in str(exc_info.value)

        # Reject future datetime
        future_utc = datetime.now(timezone.utc) + timedelta(days=1)
        with pytest.raises(ValidationError) as exc_info:
            WornOutfitRequest(idempotency_key=valid_v4, worn_at=future_utc)
        assert "worn_at cannot be in the future" in str(exc_info.value)

    def test_rating_strictly_enforces_integer_stars_no_bool_or_float(self) -> None:
        session_v4 = str(uuid.uuid4())
        # Valid integer 1..5
        for stars in [1, 2, 3, 4, 5]:
            req = OutfitRatingRequest(stars=stars, source=RatingSource.MANUAL)
            assert req.stars == stars

        # Reject boolean (Pydantic strict=True prevents True -> 1)
        with pytest.raises(ValidationError):
            OutfitRatingRequest(stars=True, source=RatingSource.MANUAL)  # type: ignore[arg-type]

        # Reject float (Pydantic strict=True prevents 4.0 -> 4)
        with pytest.raises(ValidationError):
            OutfitRatingRequest(stars=4.0, source=RatingSource.MANUAL)  # type: ignore[arg-type]

        # Reject out of bounds integers
        with pytest.raises(ValidationError):
            OutfitRatingRequest(stars=0, source=RatingSource.MANUAL)
        with pytest.raises(ValidationError):
            OutfitRatingRequest(stars=6, source=RatingSource.MANUAL)

    def test_rating_prompted_requires_session_id(self) -> None:
        session_v4 = str(uuid.uuid4())
        # Prompted with session ID -> OK
        req = OutfitRatingRequest(
            stars=5,
            source=RatingSource.PROMPTED,
            client_session_id=session_v4,
        )
        assert req.client_session_id == session_v4

        # Prompted without body session ID is allowed in schema (can come from X-Client-Session-Id header)
        req_no_body_session = OutfitRatingRequest(
            stars=5,
            source=RatingSource.PROMPTED,
            client_session_id=None,
        )
        assert req_no_body_session.client_session_id is None

        # Manual rating without session ID -> OK
        manual_req = OutfitRatingRequest(stars=5, source=RatingSource.MANUAL)
        assert manual_req.client_session_id is None

        # Reject non-UUID v4 session ID
        with pytest.raises(ValidationError) as exc_info:
            OutfitRatingRequest(
                stars=5,
                source=RatingSource.PROMPTED,
                client_session_id="not-a-uuid",
            )
        assert "client_session_id must be a valid UUID v4" in str(exc_info.value)

    def test_dismiss_prompt_validates_client_session_id(self) -> None:
        session_v4 = str(uuid.uuid4())
        req = DismissPromptRequest(client_session_id=session_v4)
        assert req.client_session_id == session_v4

        # None is allowed
        req_none = DismissPromptRequest(client_session_id=None)
        assert req_none.client_session_id is None

        # Invalid UUID rejected
        with pytest.raises(ValidationError) as exc_info:
            DismissPromptRequest(client_session_id="bad-uuid")
        assert "client_session_id must be a valid UUID v4" in str(exc_info.value)

    def test_bookmark_request_strictly_requires_boolean(self) -> None:
        req = BookmarkOutfitRequest(is_bookmarked=True)
        assert req.is_bookmarked is True

        # Reject non-boolean string "true" or integer 1
        with pytest.raises(ValidationError):
            BookmarkOutfitRequest(is_bookmarked="true")  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            BookmarkOutfitRequest(is_bookmarked=1)  # type: ignore[arg-type]

    def test_stylist_chat_request_accepts_and_validates_client_session_id(self) -> None:
        session_v4 = str(uuid.uuid4())
        req = StylistChatRequest(query="Mặc gì đi cafe?", client_session_id=session_v4)
        assert req.client_session_id == session_v4

        # Rejects non-UUID v4
        with pytest.raises(ValidationError) as exc_info:
            StylistChatRequest(query="Mặc gì đi cafe?", client_session_id="not-a-uuid")
        assert "client_session_id must be a valid UUID v4" in str(exc_info.value)


class TestOutfitActionsEndpointStubs:
    """Verify endpoint stubs return standard 501 NOT_IMPLEMENTED envelope, not unhandled 500."""

    @pytest.fixture
    def client(self, migrated_database: tuple[object, object]) -> Any:
        from starlette.testclient import TestClient
        from sqlmodel import Session
        from app.core.dependencies import get_db_session
        from app.main import app

        _, engine = migrated_database

        def override_db():
            with Session(engine) as session:
                yield session

        app.dependency_overrides[get_db_session] = override_db
        test_client = TestClient(app)
        try:
            yield test_client
        finally:
            app.dependency_overrides.pop(get_db_session, None)

    def test_outfit_endpoints_and_remaining_stubs(self, client: Any) -> None:
        headers = {"X-User-Id": "test-user-id"}
        outfit_id = str(uuid.uuid4())

        # 1. GET /api/v1/outfits/saved (implemented in 5.2: returns 200 with empty list for new user)
        resp = client.get("/api/v1/outfits/saved", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["data"]["total"] == 0
        assert resp.json()["data"]["items"] == []

        # 2. GET /api/v1/outfits/{id} (implemented in 5.2: returns 404 for unknown outfit)
        resp = client.get(f"/api/v1/outfits/{outfit_id}", headers=headers)
        assert resp.status_code == 404
        assert resp.json()["success"] is False
        assert resp.json()["error"]["code"] == "OUTFIT_NOT_FOUND"

        # 3. PUT /api/v1/outfits/{id}/bookmark (implemented in 5.2: returns 404 for unknown outfit)
        resp = client.put(f"/api/v1/outfits/{outfit_id}/bookmark", headers=headers, json={"is_bookmarked": True})
        assert resp.status_code == 404
        assert resp.json()["success"] is False
        assert resp.json()["error"]["code"] == "OUTFIT_NOT_FOUND"

        # 4. POST /api/v1/outfits/{id}/worn (implemented in 5.3: returns 404 for unknown outfit)
        resp = client.post(
            f"/api/v1/outfits/{outfit_id}/worn",
            headers=headers,
            json={"idempotency_key": str(uuid.uuid4())},
        )
        assert resp.status_code == 404
        assert resp.json()["success"] is False
        assert resp.json()["error"]["code"] == "OUTFIT_NOT_FOUND"

        # 5. PUT /api/v1/outfits/{id}/rating (implemented in 5.4: returns 404 for unknown outfit)
        resp = client.put(
            f"/api/v1/outfits/{outfit_id}/rating",
            headers=headers,
            json={"stars": 5, "source": "prompted", "client_session_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404
        assert resp.json()["success"] is False
        assert resp.json()["error"]["code"] == "OUTFIT_NOT_FOUND"

        # 6. POST /api/v1/feedback/prompts/dismiss (stub: returns 501 until Task 5.5)
        resp = client.post("/api/v1/feedback/prompts/dismiss", headers=headers, json={})
        assert resp.status_code == 501
        assert resp.json()["error"]["code"] == "NOT_IMPLEMENTED"


class TestMultiSessionAndCadencePersistence:
    """Verify data model guarantees for multi-session suppression and duplicate outfit delivery."""

    @pytest.fixture
    def session(self) -> Any:
        from sqlmodel import Session, SQLModel, create_engine
        engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as s:
            yield s

    def test_multi_session_suppression_allows_independent_sessions(self, session: Any) -> None:
        from app.models.entities import FeedbackSuppressedSession, User
        from sqlmodel import select

        user = User(id=str(uuid.uuid4()), email="test@example.com", name="Tester")
        session.add(user)
        session.commit()

        session_a = str(uuid.uuid4())
        session_b = str(uuid.uuid4())

        # Tab A rates and suppresses prompt
        sup_a = FeedbackSuppressedSession(user_id=user.id, client_session_id=session_a)
        session.add(sup_a)
        session.commit()

        # Tab B rates and suppresses prompt
        sup_b = FeedbackSuppressedSession(user_id=user.id, client_session_id=session_b)
        session.add(sup_b)
        session.commit()

        # Both sessions exist independently; neither overwrote the other
        rows = session.exec(
            select(FeedbackSuppressedSession).where(FeedbackSuppressedSession.user_id == user.id)
        ).all()
        assert len(rows) == 2
        session_ids = {r.client_session_id for r in rows}
        assert session_a in session_ids
        assert session_b in session_ids

    def test_delivered_outfits_enforces_distinct_outfits_per_user(self, session: Any) -> None:
        from sqlalchemy.exc import IntegrityError
        from app.models.entities import FeedbackDeliveredOutfit, OutfitRecommendation, User

        user = User(id=str(uuid.uuid4()), email="test@example.com", name="Tester")
        session.add(user)
        session.commit()

        outfit = OutfitRecommendation(
            id=str(uuid.uuid4()),
            user_id=user.id,
            request_id=str(uuid.uuid4()),
            user_query="test query",
            context_snapshot={"occasion": "cafe"},
            explanation_vi="gợi ý mặc đẹp",
            fashion_score=0.85,
            personalization_score=0.95,
            composite_score=0.9,
            rank=1,
            rule_version="v1.0",
        )
        session.add(outfit)
        session.commit()

        # First delivery: recorded successfully
        deliv1 = FeedbackDeliveredOutfit(
            user_id=user.id,
            outfit_id=outfit.id,
            request_id=outfit.request_id,
        )
        session.add(deliv1)
        session.commit()

        # Second delivery of SAME outfit (e.g. user retries query or regenerates)
        deliv2 = FeedbackDeliveredOutfit(
            user_id=user.id,
            outfit_id=outfit.id,
            request_id=str(uuid.uuid4()),
        )
        session.add(deliv2)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_idempotency_conflict_error_semantics(self) -> None:
        from app.schemas.common import IdempotencyConflictError

        err = IdempotencyConflictError()
        assert err.status_code == 409
        assert err.code == "IDEMPOTENCY_CONFLICT"


class TestSessionContractAndReconciliation:
    """Verify strict contract rules on X-Client-Session-Id header and body reconciliation."""

    def test_validate_header_accepts_valid_uuid_v4(self) -> None:
        from app.core.dependencies import validate_client_session_id_header

        valid_v4 = str(uuid.uuid4())
        assert validate_client_session_id_header(valid_v4) == valid_v4
        assert validate_client_session_id_header(None) is None
        assert validate_client_session_id_header("   ") is None

    def test_validate_header_rejects_non_uuid_and_uuid_v1(self) -> None:
        from app.core.dependencies import validate_client_session_id_header
        from app.schemas.common import ValidationError

        # Non-UUID string
        with pytest.raises(ValidationError) as exc:
            validate_client_session_id_header("not-a-uuid")
        assert exc.value.status_code == 422
        assert exc.value.details.get("reason") == "must_be_valid_uuid_v4"

        # UUID v1
        uuid_v1 = str(uuid.uuid1())
        with pytest.raises(ValidationError) as exc:
            validate_client_session_id_header(uuid_v1)
        assert exc.value.status_code == 422
        assert exc.value.details.get("reason") == "must_be_valid_uuid_v4"

    def test_reconcile_accepts_matching_or_single_source(self) -> None:
        from app.core.dependencies import reconcile_client_session_id

        v4_a = str(uuid.uuid4())

        # Both match
        assert reconcile_client_session_id(v4_a, v4_a) == v4_a
        # Header only
        assert reconcile_client_session_id(v4_a, None) == v4_a
        # Body only
        assert reconcile_client_session_id(None, v4_a) == v4_a
        # Neither
        assert reconcile_client_session_id(None, None) is None

    def test_reconcile_rejects_mismatch_with_422(self) -> None:
        from app.core.dependencies import reconcile_client_session_id
        from app.schemas.common import ValidationError

        v4_a = str(uuid.uuid4())
        v4_b = str(uuid.uuid4())

        with pytest.raises(ValidationError) as exc:
            reconcile_client_session_id(v4_a, v4_b)
        assert exc.value.status_code == 422
        assert exc.value.details.get("reason") == "header_and_body_mismatch"

    def test_endpoint_rejects_mismatched_session_headers_and_body(self) -> None:
        from starlette.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        headers = {
            "X-User-Id": "test-user-id",
            "X-Client-Session-Id": str(uuid.uuid4()),
        }
        different_session = str(uuid.uuid4())

        # Stylist chat: mismatched body and header
        resp = client.post(
            "/api/v1/stylist/chat",
            headers=headers,
            json={"query": "Mặc gì đi cafe?", "client_session_id": different_session},
        )
        assert resp.status_code == 422
        err = resp.json()
        assert err["success"] is False
        assert err["error"]["code"] == "VALIDATION_ERROR"
        assert err["error"]["details"]["reason"] == "header_and_body_mismatch"

        # Rating: mismatched body and header
        resp = client.put(
            f"/api/v1/outfits/{uuid.uuid4()}/rating",
            headers=headers,
            json={"stars": 5, "source": "prompted", "client_session_id": different_session},
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

        # Invalid header on stylist chat
        resp = client.post(
            "/api/v1/stylist/chat",
            headers={"X-User-Id": "test-user-id", "X-Client-Session-Id": "invalid-uuid"},
            json={"query": "Mặc gì đi cafe?"},
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


