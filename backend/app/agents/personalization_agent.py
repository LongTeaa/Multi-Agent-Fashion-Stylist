from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

from app.agents.state import (
    EvaluatedOutfit,
    OutfitItemSlot,
    RankedOutfit,
    StylistContext,
    StylistGraphState,
)
from app.core.database import get_engine
from app.models.entities import (
    OutfitItem,
    OutfitSlotRole,
    UserPreference,
    WearLog,
)

MAJOR_SLOT_ROLES: set[OutfitSlotRole] = {
    OutfitSlotRole.TOP,
    OutfitSlotRole.BOTTOM,
    OutfitSlotRole.DRESS,
    OutfitSlotRole.FOOTWEAR,
    OutfitSlotRole.OUTERWEAR,
}

PALETTE_MAP: dict[str, set[str]] = {
    "neutral": {"white", "black", "grey", "beige", "cream", "khaki", "navy", "brown", "tan"},
    "earth_tone": {"brown", "tan", "beige", "khaki", "olive", "terracotta", "mustard", "cream"},
    "cool_tone": {"blue", "light_blue", "denim_blue", "teal", "navy", "green", "mint", "purple", "lavender", "grey"},
    "warm_tone": {"red", "burgundy", "orange", "terracotta", "yellow", "mustard", "coral", "pink"},
}

PALETTE_VI_MAP: dict[str, str] = {
    "neutral": "trung tính",
    "earth_tone": "tông màu đất",
    "cool_tone": "tông màu lạnh",
    "warm_tone": "tông màu ấm",
    "monochrome": "đơn sắc",
}

PRIORITY_VI_MAP: dict[str, str] = {
    "comfort": "ưu tiên sự thoải mái",
    "polished": "phong thái chỉn chu",
    "expressive": "nổi bật cá tính",
    "mobility": "dễ vận động di chuyển",
    "low_maintenance": "dễ phối tiện lợi",
}

AVOID_RELAXATION_WARNING = (
    "Đã nới lỏng sở thích tránh trang phục vì tất cả các bộ đồ đều chứa yếu tố bạn muốn tránh."
)

REPETITION_WARNING = (
    "Do tủ đồ có số lượng lựa chọn giới hạn, các bộ trang phục gợi ý có thể lặp lại trang phục bạn vừa mặc gần đây."
)


# --- 1. PREFERENCE SCORING PRIMITIVES ---

def calculate_style_preference(
    items: list[OutfitItemSlot],
    preferred_styles: list[str],
) -> tuple[float, list[str]]:
    """Calculate style match score against user preferred styles.
    
    Returns 0.50 (neutral) if user has not selected preferred styles.
    """
    if not preferred_styles:
        return 0.50, []

    major_items = [item for item in items if item.slot_role in MAJOR_SLOT_ROLES]
    if not major_items:
        return 0.50, []

    preferred_set = {s.lower().strip() for s in preferred_styles}
    matched_styles: set[str] = set()
    match_count = 0

    for item in major_items:
        item_style = item.style.lower().strip() if item.style else ""
        if item_style in preferred_set:
            match_count += 1
            matched_styles.add(item_style)

    score = match_count / len(major_items)
    tags = [f"Phù hợp phong cách {s} đã chọn" for s in sorted(matched_styles)]
    return round(score, 4), tags


def calculate_palette_preference(
    items: list[OutfitItemSlot],
    preferred_palettes: list[str],
) -> tuple[float, list[str]]:
    """Calculate color palette match score against user preferred palettes.
    
    Returns 0.50 (neutral) if user has not selected preferred palettes.
    """
    if not preferred_palettes:
        return 0.50, []

    major_items = [item for item in items if item.slot_role in MAJOR_SLOT_ROLES]
    if not major_items:
        return 0.50, []

    preferred_set = {p.lower().strip() for p in preferred_palettes}
    colors = [item.primary_color.lower().strip() for item in major_items if item.primary_color]

    is_monochrome = False
    if "monochrome" in preferred_set and colors:
        distinct_colors = len(set(colors))
        if distinct_colors <= 1:
            is_monochrome = True
        elif all(c in PALETTE_MAP["neutral"] for c in colors):
            is_monochrome = True

    match_count = 0
    matched_palettes: set[str] = set()

    for item in major_items:
        color = item.primary_color.lower().strip() if item.primary_color else ""
        item_matched = False
        for pal in preferred_set:
            if pal in PALETTE_MAP and color in PALETTE_MAP[pal]:
                item_matched = True
                matched_palettes.add(pal)
        if item_matched or (is_monochrome and "monochrome" in preferred_set):
            match_count += 1
            if is_monochrome:
                matched_palettes.add("monochrome")

    score = match_count / len(major_items) if major_items else 0.50
    tags = [
        f"Bảng màu {PALETTE_VI_MAP.get(p, p)} theo sở thích"
        for p in sorted(matched_palettes)
    ]
    return round(score, 4), tags


def calculate_priority_preference(
    items: list[OutfitItemSlot],
    priorities: list[str],
) -> tuple[float, list[str]]:
    """Calculate priority match score (comfort, polished, expressive, mobility, low_maintenance).
    
    Returns 0.50 (neutral) if user has not selected priorities.
    """
    if not priorities:
        return 0.50, []

    major_items = [item for item in items if item.slot_role in MAJOR_SLOT_ROLES]
    if not major_items:
        return 0.50, []

    p_set = {p.lower().strip() for p in priorities}
    matches = 0
    matched_priorities: set[str] = set()

    for item in major_items:
        item_match = False
        style = item.style.lower().strip() if item.style else ""
        fit = item.fit.lower().strip() if item.fit else ""
        mat = item.material.lower().strip() if item.material else ""
        pat = item.pattern.lower().strip() if item.pattern else ""
        role = item.slot_role
        color = item.primary_color.lower().strip() if item.primary_color else ""

        if "comfort" in p_set:
            if fit in {"regular", "relaxed", "oversized"} or mat in {"cotton", "linen", "knit", "denim"}:
                item_match = True
                matched_priorities.add("comfort")
        if "polished" in p_set:
            if item.formality_level >= 3 or style in {"smart_casual", "formal", "minimalist"}:
                item_match = True
                matched_priorities.add("polished")
        if "expressive" in p_set:
            if pat not in {"solid", "none", ""} or style in {"streetwear", "vintage"}:
                item_match = True
                matched_priorities.add("expressive")
        if "mobility" in p_set:
            if role == OutfitSlotRole.FOOTWEAR and ("sneaker" in item.name.lower() or style in {"casual", "streetwear"}):
                item_match = True
                matched_priorities.add("mobility")
            elif fit in {"regular", "relaxed", "oversized"}:
                item_match = True
                matched_priorities.add("mobility")
        if "low_maintenance" in p_set:
            if pat in {"solid", "none", ""} and color in PALETTE_MAP["neutral"]:
                item_match = True
                matched_priorities.add("low_maintenance")

        if item_match:
            matches += 1

    score = matches / len(major_items)
    tags = [PRIORITY_VI_MAP.get(p, p) for p in sorted(matched_priorities)]
    return round(min(1.0, score), 4), tags


def calculate_learned_affinity(
    items: list[OutfitItemSlot],
    learned_feature_weights: dict[str, Any] | None,
    ratings_count: int = 0,
) -> float:
    """Calculate learned rating affinity score.
    
    Invariant:
    - Before five ratings exist, returns neutral baseline 0.50.
    - With >= 5 ratings, computes feature alignment normalized to [0.0, 1.0].
    """
    if ratings_count < 5 or not learned_feature_weights:
        return 0.50

    raw_weights = learned_feature_weights.get("weights", {})
    if not raw_weights or not isinstance(raw_weights, dict):
        return 0.50

    outfit_features: list[str] = []
    for item in items:
        if item.style:
            outfit_features.append(f"style:{item.style.lower().strip()}")
        if item.primary_color:
            outfit_features.append(f"color:{item.primary_color.lower().strip()}")
        if item.pattern:
            outfit_features.append(f"pattern:{item.pattern.lower().strip()}")
        if item.formality_level <= 2:
            outfit_features.append("formality:low")
        elif item.formality_level == 3:
            outfit_features.append("formality:medium")
        else:
            outfit_features.append("formality:high")

    matched_weights = [
        raw_weights[f]
        for f in outfit_features
        if f in raw_weights and isinstance(raw_weights[f], (int, float))
    ]
    if not matched_weights:
        return 0.50

    avg_weight = sum(matched_weights) / len(matched_weights)
    # Map avg_weight from [-1.0, 1.0] to [0.0, 1.0]: 0.5 + avg_weight * 0.5
    score = 0.50 + (avg_weight * 0.50)
    return round(max(0.0, min(1.0, score)), 4)


def check_outfit_avoid_violations(
    items: list[OutfitItemSlot],
    avoid_colors: list[str],
    avoid_styles: list[str],
) -> list[str]:
    """Identify any items in the outfit that violate explicit avoid preferences."""
    violations: list[str] = []
    avoid_c_set = {c.lower().strip() for c in avoid_colors}
    avoid_s_set = {s.lower().strip() for s in avoid_styles}

    for item in items:
        color = item.primary_color.lower().strip() if item.primary_color else ""
        sec_color = item.secondary_color.lower().strip() if item.secondary_color else ""
        style = item.style.lower().strip() if item.style else ""

        if color and color in avoid_c_set:
            violations.append(f"màu {color}")
        if sec_color and sec_color in avoid_c_set:
            violations.append(f"màu {sec_color}")
        if style and style in avoid_s_set:
            violations.append(f"phong cách {style}")

    return list(dict.fromkeys(violations))


def calculate_recent_wear_penalty(
    items: list[OutfitItemSlot],
    recent_wear_data: dict[str, Any],
    reference_time: datetime | None = None,
) -> tuple[float, list[str]]:
    """Apply anti-repetition penalties according to Section 5:
    
    - Exact outfit confirmed worn within 3 days (72h): strong penalty (-0.40).
    - Major item confirmed worn within 48h: smaller penalty (-0.15 per item, max -0.30).
    """
    ref = reference_time or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)

    penalty = 0.0
    notes: list[str] = []

    candidate_item_ids = {item.item_id for item in items}
    exact_outfits_72h = recent_wear_data.get("exact_outfits_72h", [])
    if any(candidate_item_ids == worn_set for worn_set in exact_outfits_72h):
        penalty += 0.40
        notes.append("Đã mặc trong 3 ngày qua (-0.40)")

    worn_48h_ids = recent_wear_data.get("items_worn_48h", set())
    major_worn_count = 0
    for item in items:
        if item.slot_role in MAJOR_SLOT_ROLES:
            is_recent = item.item_id in worn_48h_ids
            if not is_recent and item.last_worn_at:
                try:
                    raw = item.last_worn_at.replace("Z", "+00:00")
                    dt = datetime.fromisoformat(raw)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if 0 <= (ref - dt).total_seconds() <= 48 * 3600:
                        is_recent = True
                except (ValueError, TypeError):
                    pass
            if is_recent:
                major_worn_count += 1

    if major_worn_count > 0:
        item_penalty = min(0.30, major_worn_count * 0.15)
        penalty += item_penalty
        notes.append(f"Có {major_worn_count} món chính vừa mặc trong 48 giờ (-{item_penalty:.2f})")

    return round(penalty, 4), notes


# --- 2. DATA RETRIEVAL WITH STRICT USER ISOLATION ---

def get_user_personalization_data(
    session: Session,
    user_id: str,
    reference_time: datetime | None = None,
) -> tuple[UserPreference | None, dict[str, Any]]:
    """Load user preferences and recent wear data with strict user isolation.
    
    Guarantees that User B's preferences and wear history never leak into User A.
    """
    preferences = session.get(UserPreference, user_id)

    ref = reference_time or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)

    since_72h = ref - timedelta(hours=72)
    since_48h = ref - timedelta(hours=48)

    # Query WearLog strictly owned by user_id
    wear_logs = session.exec(
        select(WearLog).where(
            WearLog.user_id == user_id,
            WearLog.worn_at >= since_72h,
        )
    ).all()

    exact_outfits_72h: list[set[str]] = []
    items_worn_48h: set[str] = set()

    for log in wear_logs:
        outfit_items = session.exec(
            select(OutfitItem).where(
                OutfitItem.outfit_id == log.outfit_id,
                OutfitItem.user_id == user_id,
            )
        ).all()
        item_ids = {oi.wardrobe_item_id for oi in outfit_items}
        if item_ids:
            exact_outfits_72h.append(item_ids)

        log_worn_at = log.worn_at
        if log_worn_at.tzinfo is None:
            log_worn_at = log_worn_at.replace(tzinfo=timezone.utc)
        if log_worn_at >= since_48h:
            items_worn_48h.update(item_ids)

    recent_wear_data = {
        "exact_outfits_72h": exact_outfits_72h,
        "items_worn_48h": items_worn_48h,
    }

    return preferences, recent_wear_data


# --- 3. RERANKING ENGINE ---

def rerank_evaluated_outfits(
    candidates: list[EvaluatedOutfit],
    preferences: UserPreference | None = None,
    recent_wear_data: dict[str, Any] | None = None,
    context: StylistContext | None = None,
    reference_time: datetime | None = None,
    max_output: int = 3,
) -> tuple[list[RankedOutfit], list[str]]:
    """Rerank up to 5 evaluated candidates into 1 to 3 final RankedOutfit results.
    
    Formula:
      preference_score = (
          0.35 * style_match
          + 0.25 * color_palette_match
          + 0.20 * priority_match
          + 0.20 * learned_rating_affinity
          - explicit_avoid_penalty
          - recent_wear_penalty
      ) clamped to [0.0, 1.0].
      
      composite_score = round(0.60 * fashion_score + 0.40 * preference_score, 4).

    Invariants:
      - Explicit exclusions win: If any clean (non-violating) candidate exists,
        violating candidates are strictly filtered out and never appear in output.
      - Controlled relaxation: Only when ALL candidates violate avoid constraints,
        constraints are relaxed with AVOID_RELAXATION_WARNING.
      - Anti-repetition: When all candidates in a limited wardrobe repeat recent wears,
        REPETITION_WARNING is emitted without hard-rejecting.
    """
    if not candidates:
        return [], []

    # Bound candidate inputs at 5
    bounded_candidates = candidates[:5]
    warnings: list[str] = []
    recent_data = recent_wear_data or {}

    styles = preferences.styles if preferences else []
    color_palettes = preferences.color_palettes if preferences else []
    priorities = preferences.priorities if preferences else []
    avoid_colors = preferences.avoid_colors if preferences else []
    avoid_styles = preferences.avoid_styles if preferences else []
    learned_weights = preferences.learned_feature_weights if preferences else None
    ratings_count = preferences.ratings_count if preferences else 0

    # Check explicit avoid violations across all candidates
    candidate_violations = [
        check_outfit_avoid_violations(c.items, avoid_colors, avoid_styles)
        for c in bounded_candidates
    ]

    has_avoid_rules = bool(avoid_colors or avoid_styles)
    clean_pairs = [
        (c, v) for c, v in zip(bounded_candidates, candidate_violations) if len(v) == 0
    ]

    if has_avoid_rules and clean_pairs:
        # Invariant: Explicit exclusions win. Only clean candidates are eligible for ranking/output.
        active_pairs = clean_pairs
        is_relaxed = False
    elif has_avoid_rules and not clean_pairs:
        # Controlled relaxation: every valid candidate violates avoid rules.
        # Relax constraints with warning to avoid empty recommendation.
        warnings.append(AVOID_RELAXATION_WARNING)
        active_pairs = list(zip(bounded_candidates, candidate_violations))
        is_relaxed = True
    else:
        active_pairs = list(zip(bounded_candidates, candidate_violations))
        is_relaxed = False

    scored_candidates: list[tuple[float, float, float, EvaluatedOutfit, list[str]]] = []
    wear_penalties: list[float] = []

    for cand, violations in active_pairs:
        style_score, style_tags = calculate_style_preference(cand.items, styles)
        palette_score, palette_tags = calculate_palette_preference(cand.items, color_palettes)
        priority_score, priority_tags = calculate_priority_preference(cand.items, priorities)
        affinity_score = calculate_learned_affinity(cand.items, learned_weights, ratings_count)

        avoid_penalty = (0.10 * len(violations)) if is_relaxed else 0.0

        wear_penalty, wear_notes = calculate_recent_wear_penalty(
            cand.items, recent_data, reference_time
        )
        wear_penalties.append(wear_penalty)

        raw_preference = (
            0.35 * style_score
            + 0.25 * palette_score
            + 0.20 * priority_score
            + 0.20 * affinity_score
            - avoid_penalty
            - wear_penalty
        )
        pref_score = round(max(0.0, min(1.0, raw_preference)), 4)

        composite = round(
            max(0.0, min(1.0, 0.60 * cand.fashion_score + 0.40 * pref_score)), 4
        )

        applied_prefs = style_tags + palette_tags + priority_tags
        scored_candidates.append((composite, cand.fashion_score, pref_score, cand, applied_prefs))

    # Anti-repetition warning for small wardrobes where all active choices repeat recent wears
    if wear_penalties and all(p > 0.0 for p in wear_penalties):
        warnings.append(REPETITION_WARNING)

    # Sort deterministically:
    # 1. Descending composite_score
    # 2. Descending fashion_score
    # 3. Descending preference_score
    # 4. Ascending combination_id
    scored_candidates.sort(
        key=lambda item: (-item[0], -item[1], -item[2], item[3].combination_id)
    )

    # Truncate to top 1..3 results (strictly clamped to [1, 3] per contract)
    effective_max_output = max(1, min(3, max_output))
    top_candidates = scored_candidates[:effective_max_output]
    ranked_outfits: list[RankedOutfit] = []

    for rank_idx, (comp_score, f_score, p_score, cand, applied_tags) in enumerate(
        top_candidates, start=1
    ):
        ranked = RankedOutfit(
            outfit_id=None,
            rank=rank_idx,
            composite_score=comp_score,
            fashion_score=f_score,
            personalization_score=p_score,
            items=cand.items,
            explanation_vi="",  # Grounded explanation is produced by Coordinator in Part 4.5
            applied_preferences=applied_tags,
        )
        ranked_outfits.append(ranked)

    return ranked_outfits, warnings


# --- 4. LANGGRAPH NODE EXECUTION ---

def personalization_agent_node(
    state: StylistGraphState,
    session: Session | None = None,
) -> dict[str, Any]:
    """LangGraph node execution function for the Personalization Agent.
    
    Consumes evaluated_outfits, loads requesting user's profile and wear logs,
    and produces ranked_outfits.
    """
    user_id = state.get("user_id", "")
    evaluated_outfits = state.get("evaluated_outfits", [])
    context = state.get("context")
    reference_time = state.get("reference_time")
    existing_errors = list(state.get("errors", []))
    existing_warnings = list(state.get("warnings", []))

    if not evaluated_outfits:
        return {"ranked_outfits": []}

    # Load user data with session
    preferences: UserPreference | None = None
    recent_wear_data: dict[str, Any] = {}

    try:
        if session is not None:
            preferences, recent_wear_data = get_user_personalization_data(
                session, user_id, reference_time
            )
        else:
            with Session(get_engine()) as db_session:
                preferences, recent_wear_data = get_user_personalization_data(
                    db_session, user_id, reference_time
                )
    except Exception as exc:
        logger.exception("Failed to load personalization data for user %s: %s", user_id, exc)
        return {
            "ranked_outfits": [],
            "errors": existing_errors + ["PERSONALIZATION_DB_ERROR"],
            "warnings": existing_warnings,
        }

    ranked, warnings = rerank_evaluated_outfits(
        evaluated_outfits,
        preferences=preferences,
        recent_wear_data=recent_wear_data,
        context=context,
        reference_time=reference_time,
        max_output=3,
    )

    return {
        "ranked_outfits": ranked,
        "warnings": existing_warnings + warnings,
    }
