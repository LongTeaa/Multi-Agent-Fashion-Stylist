from __future__ import annotations

from collections import defaultdict

from sqlmodel import Session

from app.models.entities import User, UserPreference, utc_now
from app.schemas.common import ValidationError
from app.schemas.profile import (
    PreferenceOptionGroup,
    PreferenceOptionsResponseData,
    PreferenceSelections,
    ProfileResponseData,
)

STYLES = ("casual", "minimalist", "smart_casual", "streetwear", "formal", "vintage")
COLOR_PALETTES = ("neutral", "earth_tone", "cool_tone", "warm_tone", "monochrome")
PRIORITIES = ("comfort", "polished", "expressive", "mobility", "low_maintenance")
FIT_PREFERENCES = ("slim", "regular", "relaxed", "oversized")
COLORS = (
    "white", "black", "grey", "beige", "cream", "khaki", "navy", "brown", "tan",
    "red", "orange", "yellow", "green", "blue", "purple", "pink",
)

_OPTION_SETS = {
    "styles": frozenset(STYLES),
    "color_palettes": frozenset(COLOR_PALETTES),
    "priorities": frozenset(PRIORITIES),
    "avoid_styles": frozenset(STYLES),
    "fit_preferences": frozenset(FIT_PREFERENCES),
}

_WEIGHT_LOOKUP: dict[tuple[str, str], dict[str, float]] = {
    ("styles", "casual"): {"style:casual": 1.0, "formality:low": 0.5},
    ("styles", "minimalist"): {"style:minimalist": 1.0, "pattern:solid": 0.6},
    ("styles", "smart_casual"): {"style:smart_casual": 1.0, "formality:medium": 0.5},
    ("styles", "streetwear"): {"style:streetwear": 1.0, "formality:low": 0.4},
    ("styles", "formal"): {"style:formal": 1.0, "formality:high": 0.6},
    ("styles", "vintage"): {"style:vintage": 1.0},
    ("color_palettes", "neutral"): {"palette:neutral": 1.0},
    ("color_palettes", "earth_tone"): {"palette:earth_tone": 1.0},
    ("color_palettes", "cool_tone"): {"palette:cool_tone": 1.0},
    ("color_palettes", "warm_tone"): {"palette:warm_tone": 1.0},
    ("color_palettes", "monochrome"): {"palette:monochrome": 1.0},
    ("priorities", "comfort"): {"priority:comfort": 1.0},
    ("priorities", "polished"): {"priority:polished": 1.0},
    ("priorities", "expressive"): {"priority:expressive": 1.0},
    ("priorities", "mobility"): {"priority:mobility": 1.0},
    ("priorities", "low_maintenance"): {"priority:low_maintenance": 1.0},
}


def preference_options() -> PreferenceOptionsResponseData:
    return PreferenceOptionsResponseData(
        version=1,
        styles=PreferenceOptionGroup(values=list(STYLES), selection_limit=3),
        color_palettes=PreferenceOptionGroup(values=list(COLOR_PALETTES), selection_limit=3),
        priorities=PreferenceOptionGroup(values=list(PRIORITIES), selection_limit=3),
        fit_preferences=PreferenceOptionGroup(values=list(FIT_PREFERENCES), selection_limit=1),
        avoid_colors=PreferenceOptionGroup(values=list(COLORS), selection_limit=20),
        avoid_styles=PreferenceOptionGroup(values=list(STYLES), selection_limit=20),
    )


def _validate_canonical_options(selections: PreferenceSelections) -> None:
    invalid: dict[str, list[str]] = {}
    for field, allowed in _OPTION_SETS.items():
        unknown = sorted(set(getattr(selections, field)) - allowed)
        if unknown:
            invalid[field] = unknown
    unknown_colors = sorted(set(selections.avoid_colors) - set(COLORS))
    if unknown_colors:
        invalid["avoid_colors"] = unknown_colors
    if invalid:
        raise ValidationError(details={"invalid_options": invalid})


def build_initial_feature_weights(selections: PreferenceSelections) -> dict[str, object]:
    weights: defaultdict[str, float] = defaultdict(float)
    for group in ("styles", "color_palettes", "priorities"):
        for option in getattr(selections, group):
            for feature, weight in _WEIGHT_LOOKUP[(group, option)].items():
                weights[feature] += weight
    return {
        "version": 1,
        "weights": {feature: min(value, 1.0) for feature, value in sorted(weights.items())},
    }


def _ensure_user_and_preferences(session: Session, user_id: str) -> tuple[User, UserPreference]:
    user = session.get(User, user_id)
    if user is None:
        user = User(id=user_id)
        session.add(user)
        session.flush()
    preferences = session.get(UserPreference, user_id)
    if preferences is None:
        preferences = UserPreference(user_id=user_id)
        session.add(preferences)
        session.flush()
    return user, preferences


def _serialize(user: User, preferences: UserPreference) -> ProfileResponseData:
    return ProfileResponseData(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        preferences=PreferenceSelections(
            styles=preferences.styles,
            color_palettes=preferences.color_palettes,
            priorities=preferences.priorities,
            avoid_colors=preferences.avoid_colors,
            avoid_styles=preferences.avoid_styles,
            fit_preferences=preferences.fit_preferences,
        ),
        feature_weights=preferences.learned_feature_weights,
        ratings_count=preferences.ratings_count,
    )


def get_profile(session: Session, user_id: str) -> ProfileResponseData:
    user, preferences = _ensure_user_and_preferences(session, user_id)
    session.commit()
    session.refresh(user)
    session.refresh(preferences)
    return _serialize(user, preferences)


def replace_preferences(
    session: Session, user_id: str, selections: PreferenceSelections
) -> ProfileResponseData:
    _validate_canonical_options(selections)
    user, preferences = _ensure_user_and_preferences(session, user_id)
    preferences.styles = list(selections.styles)
    preferences.color_palettes = list(selections.color_palettes)
    preferences.priorities = list(selections.priorities)
    preferences.avoid_colors = list(selections.avoid_colors)
    preferences.avoid_styles = list(selections.avoid_styles)
    preferences.fit_preferences = list(selections.fit_preferences)
    preferences.learned_feature_weights = build_initial_feature_weights(selections)
    preferences.updated_at = utc_now()
    session.add(preferences)
    session.commit()
    session.refresh(preferences)
    return _serialize(user, preferences)
