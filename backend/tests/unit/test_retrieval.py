from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlmodel import Session

from app.models.entities import User, WardrobeCategory, WardrobeItem
from app.schemas.retrieval import WardrobeRetrievalQuery
from app.services.retrieval_document_service import refresh_retrieval_document
from app.services.retrieval_service import retrieve_wardrobe_items


def _add_item(
    session: Session,
    *,
    item_id: str,
    user_id: str,
    category: WardrobeCategory = WardrobeCategory.TOP,
    color: str = "white",
    style: str = "smart_casual",
    formality: int = 3,
    weather: list[str] | None = None,
    tags: list[str] | None = None,
    confirmed: bool = True,
    active: bool = True,
    deleted: bool = False,
) -> WardrobeItem:
    item = WardrobeItem(
        id=item_id,
        user_id=user_id,
        category=category,
        sub_category="polo",
        primary_color=color,
        pattern="solid",
        material="cotton",
        style=style,
        fit="regular",
        formality_level=formality,
        weather_suitability=weather or ["warm", "cool"],
        free_text_tags=tags or [],
        is_user_confirmed=confirmed,
        is_active=active,
        deleted_at=datetime.now(timezone.utc) if deleted else None,
    )
    session.add(item)
    session.flush()
    refresh_retrieval_document(session, item)
    return item


def test_metadata_retrieval_filters_ownership_state_constraints_and_category(
    migrated_database: tuple[object, object],
) -> None:
    _, engine = migrated_database
    user_a, user_b = str(uuid4()), str(uuid4())
    with Session(engine) as session:
        session.add(User(id=user_a))
        session.add(User(id=user_b))
        session.flush()
        _add_item(session, item_id="matching", user_id=user_a, tags=["cafe"])
        _add_item(session, item_id="avoided", user_id=user_a, color="orange", tags=["cafe"])
        _add_item(session, item_id="wrong-category", user_id=user_a, category=WardrobeCategory.BOTTOM)
        _add_item(session, item_id="unconfirmed", user_id=user_a, confirmed=False)
        _add_item(session, item_id="inactive", user_id=user_a, active=False)
        _add_item(session, item_id="deleted", user_id=user_a, deleted=True)
        _add_item(session, item_id="other-user", user_id=user_b, tags=["cafe"])
        session.commit()

        results = retrieve_wardrobe_items(
            session=session,
            user_id=user_a,
            query=WardrobeRetrievalQuery(
                categories=[WardrobeCategory.TOP],
                style_hints=["smart_casual"],
                color_hints=["white"],
                weather_condition="cool",
                formality_min=2,
                formality_max=3,
                must_have=["cafe"],
                must_avoid=["orange"],
            ),
        )

    matches = results[WardrobeCategory.TOP]
    assert [match.item.id for match in matches] == ["matching"]
    assert matches[0].metadata_score == 1.0
    assert matches[0].full_text_score == 0.0
    assert matches[0].relaxed_constraints == ()


def test_full_text_ranking_is_optional_and_deterministic(
    migrated_database: tuple[object, object],
) -> None:
    _, engine = migrated_database
    user_id = str(uuid4())
    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()
        _add_item(session, item_id="a-office", user_id=user_id, tags=["office"])
        _add_item(session, item_id="z-retro", user_id=user_id, tags=["retro", "cafe"])
        session.commit()

        metadata_only = retrieve_wardrobe_items(
            session=session,
            user_id=user_id,
            query=WardrobeRetrievalQuery(
                categories=[WardrobeCategory.TOP], text_query="retro cafe"
            ),
        )
        with_full_text = retrieve_wardrobe_items(
            session=session,
            user_id=user_id,
            query=WardrobeRetrievalQuery(
                categories=[WardrobeCategory.TOP],
                text_query="retro cafe",
                enable_full_text=True,
            ),
        )

    assert [match.item.id for match in metadata_only[WardrobeCategory.TOP]] == [
        "a-office",
        "z-retro",
    ]
    ranked = with_full_text[WardrobeCategory.TOP]
    assert [match.item.id for match in ranked] == ["z-retro", "a-office"]
    assert ranked[0].full_text_score == 1.0
    assert ranked[0].composite_score > ranked[1].composite_score


def test_weather_then_formality_relaxation_is_reported_but_avoid_is_never_relaxed(
    migrated_database: tuple[object, object],
) -> None:
    _, engine = migrated_database
    user_id = str(uuid4())
    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()
        _add_item(
            session,
            item_id="summer-cap",
            user_id=user_id,
            category=WardrobeCategory.ACCESSORY,
            formality=1,
            weather=["hot"],
            tags=["cap"],
        )
        session.commit()
        results = retrieve_wardrobe_items(
            session=session,
            user_id=user_id,
            query=WardrobeRetrievalQuery(
                categories=[WardrobeCategory.ACCESSORY],
                weather_condition="cold",
                formality_min=5,
                formality_max=5,
            ),
        )
        excluded = retrieve_wardrobe_items(
            session=session,
            user_id=user_id,
            query=WardrobeRetrievalQuery(
                categories=[WardrobeCategory.ACCESSORY],
                weather_condition="cold",
                formality_min=5,
                formality_max=5,
                must_avoid=["cap"],
            ),
        )

    assert results[WardrobeCategory.ACCESSORY][0].relaxed_constraints == (
        "weather",
        "formality",
    )
    assert excluded[WardrobeCategory.ACCESSORY] == []


def test_retrieval_caps_each_category_at_fifteen(
    migrated_database: tuple[object, object],
) -> None:
    _, engine = migrated_database
    user_id = str(uuid4())
    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()
        for index in range(20):
            _add_item(session, item_id=f"top-{index:02d}", user_id=user_id)
        session.commit()
        results = retrieve_wardrobe_items(
            session=session,
            user_id=user_id,
            query=WardrobeRetrievalQuery(categories=[WardrobeCategory.TOP]),
        )
    assert len(results[WardrobeCategory.TOP]) == 15


@pytest.mark.parametrize(
    "payload",
    [
        {"categories": []},
        {"categories": ["top", "top"]},
        {"categories": ["top"], "formality_min": 4, "formality_max": 2},
        {"categories": ["top"], "limit_per_category": 16},
        {"categories": ["top"], "must_have": ["cafe", "cafe"]},
    ],
)
def test_retrieval_query_rejects_invalid_bounds(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        WardrobeRetrievalQuery.model_validate(payload)
