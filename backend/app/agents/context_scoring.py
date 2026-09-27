from __future__ import annotations

from typing import Any
from app.agents.fashion_scoring import calculate_formality_score
from app.agents.state import OutfitItemSlot, StylistContext
from app.models.entities import OutfitSlotRole

MAJOR_SLOT_ROLES: set[OutfitSlotRole] = {
    OutfitSlotRole.TOP,
    OutfitSlotRole.BOTTOM,
    OutfitSlotRole.DRESS,
    OutfitSlotRole.FOOTWEAR,
    OutfitSlotRole.OUTERWEAR,
}

# --- 1. DYNAMIC CONTEXT WEIGHT PROFILES (ADVISOR SPECIFICATION) ---
# Sum of weights in every profile is strictly 1.00.

WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    # Formal Profile: Weddings, interviews, conferences, formal parties
    # Formality (30%) & Aesthetic (25%) prioritized
    "formal": {
        "formality": 0.30,
        "aesthetic": 0.25,
        "personal": 0.10,
        "weather_comfort": 0.15,
        "functional": 0.20,
    },
    # Comfort / Casual Profile: Hot days, cafe with friends, relaxed weekend, travel
    # Combined weather/comfort fit (55%) is prioritized; formality is 10%.
    "comfort": {
        "weather_comfort": 0.55,
        "aesthetic": 0.15,
        "functional": 0.20,
        "personal": 0.00,
        "formality": 0.10,
    },
    # Active / Outdoor Profile: Motorcycling, outdoor activity, heavy movement, rain
    # Function (30%) and combined weather/comfort fit (45%) are prioritized.
    "active": {
        "functional": 0.30,
        "weather_comfort": 0.45,
        "personal": 0.00,
        "aesthetic": 0.15,
        "formality": 0.10,
    },
    # Balanced Profile: General or unspecified styling request
    "balanced": {
        "aesthetic": 0.20,
        "formality": 0.20,
        "weather_comfort": 0.20,
        "functional": 0.20,
        "personal": 0.20,
    },
}


# --- 2. WEATHER & COMFORT FIT ---

def calculate_weather_comfort_fit(
    items: list[OutfitItemSlot],
    weather_condition: str,
    environment: str | None = None,
) -> float:
    """Calculate Tier-3 Weather & Comfort Fit combining garment comfort_level (1-5) and weather suitability.

    Domain Rules from Advisor:
    - Normalizes comfort_level (1-5) across major items to a 0.0 - 1.0 baseline.
    - Weather suitability ratio checks whether each item accommodates the target weather.
    - Hot weather:
      * Breathable soft garments (comfort_level >= 4) receive a bonus.
      * Heavy, stiff, or tight garments (comfort_level <= 2 or 'heavy' flag) are penalized.
    - Cold weather:
      * Warm outerwear and insulating items receive a bonus.
      * Insufficient layering without cold-suitable garments is penalized.
    - Rainy weather:
      * Requires water_resistant flags for outdoor protection.
    """
    major_items = [i for i in items if i.slot_role in MAJOR_SLOT_ROLES]
    if not major_items:
        return 1.0

    target_weather = weather_condition.lower().strip()
    env = environment.lower().strip() if environment else None

    # Baseline 1: Average comfort level (1-5 -> 0.2 - 1.0)
    avg_comfort = sum(item.comfort_level for item in major_items) / len(major_items)
    comfort_norm = avg_comfort / 5.0

    # Baseline 2: Weather suitability ratio
    suitable_count = sum(
        1 for item in major_items
        if any(target_weather in w.lower() for w in item.weather_suitability)
    )
    suitability_ratio = suitable_count / len(major_items)

    base_score = 0.50 * comfort_norm + 0.50 * suitability_ratio
    adjustment = 0.0

    outerwear_items = [i for i in items if i.slot_role == OutfitSlotRole.OUTERWEAR]
    footwear_items = [i for i in items if i.slot_role == OutfitSlotRole.FOOTWEAR]
    has_outerwear = len(outerwear_items) > 0

    # Hot weather rules
    if target_weather == "hot":
        # Bonus if overall outfit is very comfortable (soft, breathable, light)
        if avg_comfort >= 4.0 or all(item.comfort_level >= 4 for item in major_items):
            adjustment += 0.10
        # Heavy penalty for stiff, thick, or tight garments
        if any(item.comfort_level <= 2 for item in major_items):
            adjustment -= 0.20
        if any(item.material.lower() in {"wool", "leather", "fleece", "velvet"} for item in major_items):
            adjustment -= 0.25
        if has_outerwear and any("heavy" in item.functional_flags for item in outerwear_items):
            adjustment -= 0.30

    # Cold weather rules
    elif target_weather == "cold":
        has_cold_outerwear = any(
            any("cold" in w.lower() for w in item.weather_suitability)
            for item in outerwear_items
        )
        if has_cold_outerwear:
            adjustment += 0.10
        elif not has_outerwear:
            adjustment -= 0.35

    # Rainy weather rules
    elif target_weather == "rainy":
        if env == "outdoor":
            has_water_resistant = any("water_resistant" in item.functional_flags for item in items)
            if not has_water_resistant:
                adjustment -= 0.20
        for shoe in footwear_items:
            if shoe.material.lower() in {"suede", "canvas"} and "light" in shoe.functional_flags:
                adjustment -= 0.20
                break

    final_score = max(0.0, min(1.0, base_score + adjustment))
    return round(final_score, 4)


# --- 3. FUNCTIONAL FIT ---

def _derive_item_functional_flags(item: OutfitItemSlot) -> set[str]:
    """Derive implicit functional tags from sub_category and name if missing from explicit flags."""
    flags = set(f.lower().strip() for f in item.functional_flags)
    if "water_resistant" in flags:
        flags.add("rain")
    if "rain" in flags:
        flags.add("water_resistant")
    sub = (item.sub_category or "").lower().strip()
    name = (item.name or "").lower().strip()

    if any(k in sub or k in name for k in ["sneaker", "running", "sport", "athletic"]):
        flags.update(["movement", "outdoor", "sport"])
    if any(k in sub or k in name for k in ["jacket", "khoác", "windbreaker", "hoodie"]):
        flags.update(["outdoor", "protection"])
    if any(k in sub or k in name for k in ["nón", "mũ", "cap", "hat", "kính", "sunglasses"]):
        flags.update(["sun", "outdoor"])
    if any(k in sub or k in name for k in ["raincoat", "chống nước", "waterproof"]):
        flags.update(["water_resistant", "rain"])

    return flags


def calculate_functional_fit(
    items: list[OutfitItemSlot],
    target_functional_tags: list[str] | None = None,
) -> float:
    """Calculate Tier-3 Functional Fit matching garment functional capabilities to user query intent.

    Advisor Example:
    - User: "Tôi đi xe máy ngoài trời, trời nắng" -> target_functional_tags: ['outdoor', 'sun', 'movement']
    - System prioritizes garments with matching functional capabilities.
    - If user specifies no special functional needs, returns default full score (1.0).
    """
    if not target_functional_tags:
        return 1.0

    target_tags = {tag.lower().strip() for tag in target_functional_tags if tag.strip()}
    if not target_tags:
        return 1.0

    # Collect all functional flags present in the outfit with intelligent derivation
    available_flags: set[str] = set()
    for item in items:
        available_flags.update(_derive_item_functional_flags(item))

    matched_count = sum(1 for tag in target_tags if tag in available_flags)
    score = matched_count / len(target_tags)
    return round(max(0.0, min(1.0, score)), 4)


# --- 4. TIER-3 CONTEXT COMPOSITE SCORE ---

def calculate_context_composite_score(
    formality_fit: float,
    weather_comfort_fit: float,
    functional_fit: float,
    aesthetic_score: float,
    personal_fit: float,
    weight_profile: str = "balanced",
) -> tuple[float, dict[str, float | str]]:
    """Synthesize Tier-3 Final Outfit Score using the Dynamic Weight Profile specified by Advisor.

    Formula:
      Final Outfit Score = w_f * FormalityFit
                         + w_c * WeatherComfortFit
                         + w_fn * FunctionalFit
                         + w_a * AestheticScore
                         + w_p * PersonalPref
    """
    profile = WEIGHT_PROFILES.get(weight_profile.lower(), WEIGHT_PROFILES["balanced"])

    w_formality = profile["formality"]
    w_comfort = profile["weather_comfort"]
    w_functional = profile["functional"]
    w_aesthetic = profile["aesthetic"]
    w_personal = profile["personal"]

    final_score = (
        w_formality * formality_fit
        + w_comfort * weather_comfort_fit
        + w_functional * functional_fit
        + w_aesthetic * aesthetic_score
        + w_personal * personal_fit
    )
    final_score_clamped = round(max(0.0, min(1.0, final_score)), 4)

    breakdown: dict[str, float | str] = {
        "formality_fit": formality_fit,
        "weather_comfort_fit": weather_comfort_fit,
        "functional_fit": functional_fit,
        "aesthetic_score": aesthetic_score,
        "personal_fit": personal_fit,
        "final_composite_score": final_score_clamped,
        "weight_profile": weight_profile,
    }
    return final_score_clamped, breakdown
