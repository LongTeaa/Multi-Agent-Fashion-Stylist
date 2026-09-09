from __future__ import annotations

from app.models.entities import WardrobeCategory, WardrobeItem
from app.services.retrieval_document_service import build_retrieval_document


def test_build_retrieval_document_normalizes_all_retrieval_attributes() -> None:
    item = WardrobeItem(
        user_id="user-1",
        category=WardrobeCategory.TOP,
        sub_category="  Áo Polo  ",
        primary_color="WHITE",
        secondary_color="Navy",
        pattern="Solid",
        material="Cotton",
        style="Smart_Casual",
        fit="Regular",
        formality_level=3,
        season=[" Spring "],
        weather_suitability=["Cool"],
        functional_flags=["Breathable"],
        free_text_tags=["Đi cà phê"],
        is_active=True,
        is_user_confirmed=True,
    )

    searchable_text, metadata = build_retrieval_document(item)

    assert searchable_text == (
        "top áo polo white navy solid cotton smart_casual regular "
        "spring cool breathable đi cà phê formality_3"
    )
    assert metadata["category"] == "top"
    assert metadata["weather_suitability"] == ["Cool"]
    assert metadata["formality_level"] == 3
