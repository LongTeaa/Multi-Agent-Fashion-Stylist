from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from sqlmodel import Session, select

from app.models.entities import (
    WardrobeCategory,
    WardrobeItem,
    WardrobeRetrievalDocument,
)
from app.schemas.retrieval import WardrobeRetrievalQuery

_TOKEN_PATTERN = re.compile(r"[^\W_]+(?:_[^\W_]+)*", re.UNICODE)


@dataclass(frozen=True)
class RetrievalMatch:
    item: WardrobeItem
    metadata_score: float
    full_text_score: float
    composite_score: float
    relaxed_constraints: tuple[str, ...]


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).strip().lower().split())


def _tokens(value: str) -> set[str]:
    return set(_TOKEN_PATTERN.findall(_normalize(value)))


def _contains_constraints(document: str, constraints: list[str]) -> bool:
    return all(_normalize(constraint) in document for constraint in constraints)


def _matches_formality(item: WardrobeItem, query: WardrobeRetrievalQuery) -> bool:
    minimum = query.formality_min if query.formality_min is not None else 1
    maximum = query.formality_max if query.formality_max is not None else 5
    return minimum <= item.formality_level <= maximum


def _strict_candidates(
    rows: list[tuple[WardrobeItem, WardrobeRetrievalDocument]],
    query: WardrobeRetrievalQuery,
    *,
    enforce_weather: bool,
    enforce_formality: bool,
) -> list[tuple[WardrobeItem, WardrobeRetrievalDocument]]:
    selected: list[tuple[WardrobeItem, WardrobeRetrievalDocument]] = []
    weather = _normalize(query.weather_condition) if query.weather_condition else None
    for item, document in rows:
        searchable_text = _normalize(document.searchable_text)
        if not _contains_constraints(searchable_text, query.must_have):
            continue
        if any(_normalize(value) in searchable_text for value in query.must_avoid):
            continue
        if enforce_weather and weather is not None:
            if weather not in {_normalize(value) for value in item.weather_suitability}:
                continue
        if enforce_formality and not _matches_formality(item, query):
            continue
        selected.append((item, document))
    return selected


def _select_with_relaxation(
    rows: list[tuple[WardrobeItem, WardrobeRetrievalDocument]],
    query: WardrobeRetrievalQuery,
) -> tuple[list[tuple[WardrobeItem, WardrobeRetrievalDocument]], tuple[str, ...]]:
    enforce_weather = query.weather_condition is not None
    enforce_formality = query.formality_min is not None or query.formality_max is not None
    selected = _strict_candidates(
        rows,
        query,
        enforce_weather=enforce_weather,
        enforce_formality=enforce_formality,
    )
    relaxed: list[str] = []
    if not selected and enforce_weather:
        enforce_weather = False
        relaxed.append("weather")
        selected = _strict_candidates(
            rows,
            query,
            enforce_weather=False,
            enforce_formality=enforce_formality,
        )
    if not selected and enforce_formality:
        relaxed.append("formality")
        selected = _strict_candidates(
            rows,
            query,
            enforce_weather=enforce_weather,
            enforce_formality=False,
        )
    return selected, tuple(relaxed)


def _metadata_score(item: WardrobeItem, query: WardrobeRetrievalQuery) -> float:
    weighted_matches = 0.0
    total_weight = 0.0
    if query.color_hints:
        total_weight += 0.25
        colors = {_normalize(item.primary_color)}
        if item.secondary_color:
            colors.add(_normalize(item.secondary_color))
        if colors & {_normalize(value) for value in query.color_hints}:
            weighted_matches += 0.25
    if query.style_hints:
        total_weight += 0.30
        if _normalize(item.style) in {_normalize(value) for value in query.style_hints}:
            weighted_matches += 0.30
    if query.formality_min is not None or query.formality_max is not None:
        total_weight += 0.25
        if _matches_formality(item, query):
            weighted_matches += 0.25
    if query.weather_condition:
        total_weight += 0.20
        if _normalize(query.weather_condition) in {
            _normalize(value) for value in item.weather_suitability
        }:
            weighted_matches += 0.20
    return round(weighted_matches / total_weight, 6) if total_weight else 0.5


def _full_text_score(document: WardrobeRetrievalDocument, text_query: str | None) -> float:
    query_tokens = _tokens(text_query or "")
    if not query_tokens:
        return 0.0
    return round(len(query_tokens & _tokens(document.searchable_text)) / len(query_tokens), 6)


def retrieve_wardrobe_items(
    *, session: Session, user_id: str, query: WardrobeRetrievalQuery
) -> dict[WardrobeCategory, list[RetrievalMatch]]:
    """Retrieve a bounded, grounded candidate pool grouped by required category."""
    rows = session.exec(
        select(WardrobeItem, WardrobeRetrievalDocument)
        .join(
            WardrobeRetrievalDocument,
            WardrobeRetrievalDocument.wardrobe_item_id == WardrobeItem.id,
        )
        .where(
            WardrobeItem.user_id == user_id,
            WardrobeRetrievalDocument.user_id == user_id,
            WardrobeItem.is_active.is_(True),
            WardrobeItem.is_user_confirmed.is_(True),
            WardrobeItem.deleted_at.is_(None),
            WardrobeItem.category.in_(query.categories),
        )
    ).all()

    results: dict[WardrobeCategory, list[RetrievalMatch]] = {}
    for category in query.categories:
        category_rows = [(item, document) for item, document in rows if item.category == category]
        selected, relaxed = _select_with_relaxation(category_rows, query)
        matches: list[RetrievalMatch] = []
        for item, document in selected:
            metadata_score = _metadata_score(item, query)
            full_text_score = (
                _full_text_score(document, query.text_query)
                if query.enable_full_text
                else 0.0
            )
            composite_score = (
                0.8 * metadata_score + 0.2 * full_text_score
                if query.enable_full_text and query.text_query
                else metadata_score
            )
            matches.append(
                RetrievalMatch(
                    item=item,
                    metadata_score=metadata_score,
                    full_text_score=full_text_score,
                    composite_score=round(composite_score, 6),
                    relaxed_constraints=relaxed,
                )
            )
        matches.sort(
            key=lambda match: (
                -match.composite_score,
                -match.metadata_score,
                match.item.id,
            )
        )
        results[category] = matches[: query.limit_per_category]
    return results
