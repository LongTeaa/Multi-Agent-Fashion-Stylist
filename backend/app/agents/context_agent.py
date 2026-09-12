from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re
from typing import Any
import unicodedata

from app.agents.state import GarmentConstraint, StylistContext, StylistGraphState
from app.models.entities import WardrobeCategory
from app.services.providers import ContextLLMProviderProtocol, WeatherProviderProtocol

# Vietnam local timezone UTC+7
VIETNAM_TZ = timezone(timedelta(hours=7))

CLARIFICATION_PROMPT_VI = (
    "Bạn dự định mặc trang phục này đi đâu và vào thời gian nào "
    "(ví dụ: đi cafe tối nay, đi làm ngày mai...)?"
)

# Known locations in Vietnam
COMMON_LOCATIONS = [
    "đà lạt",
    "hà nội",
    "sài gòn",
    "tp.hcm",
    "tp hcm",
    "thành phố hồ chí minh",
    "đà nẵng",
    "nha trang",
    "vũng tàu",
    "huế",
    "sa pa",
    "sapa",
    "hải phòng",
    "cần thơ",
    "hội an",
    "quy nhơn",
    "phú quốc",
]

# Canonical garment and color keywords to prevent false positives in constraints
GARMENT_KEYWORDS = [
    "áo", "quần", "váy", "đầm", "giày", "dép", "sneaker", "polo", "sơ mi",
    "blazer", "chinos", "khoác", "hoodie", "cardigan", "jean", "jeans",
    "t-shirt", "thun", "suit", "vest",
]

COLOR_KEYWORDS = [
    "màu đen", "màu trắng", "màu đỏ", "màu xanh", "màu vàng", "màu xám",
    "màu nâu", "màu be", "màu hồng", "màu tím", "màu cam",
    "đen", "trắng", "đỏ", "xanh", "vàng", "xám", "nâu", "be", "hồng",
]


def normalize_text(text: str) -> str:
    """Normalize text using Unicode NFKC and strip excess whitespace."""
    return unicodedata.normalize("NFKC", text).strip()


def _is_negated(text: str, keyword: str) -> bool:
    """Check if keyword is preceded by a Vietnamese negation word."""
    pattern = rf"(?:không|chẳng|chưa|đừng|hết|ko)\s+(?:quá\s+|rất\s+|hề\s+)?{re.escape(keyword)}"
    return bool(re.search(pattern, text))


def is_ambiguous_query(text: str) -> bool:
    """Check whether a query lacks minimum actionable styling context.

    A styling query is actionable if it contains:
    1. A specific occasion (e.g. cafe, đi làm, cưới, tiệc, hẹn hò, phỏng vấn, đi chơi, dạo phố)
    OR
    2. A specific garment or style preference (e.g. áo polo, quần jean, áo khoác, lịch sự, thanh lịch)

    A query with only weather and time (e.g. 'Tối nay trời mát mặc gì?'),
    or only a general location without occasion or garment (e.g. 'Ở Đà Lạt mặc gì?'),
    is materially ambiguous because occasion dramatically changes formality (1 vs 5)
    and styling direction. Such queries require clarification.
    """
    normalized = normalize_text(text).lower()
    cleaned = re.sub(r"[?!.,]", "", normalized).strip()

    # Check known occasion keywords
    has_occasion = any(k in cleaned for k in [
        "cafe", "cà phê", "công sở", "văn phòng", "cưới", "tiệc", "hẹn",
        "dạo", "phỏng vấn", "date", "party", "interview", "sinh nhật",
        "đi chơi", "cuối tuần", "chill", "ở nhà",
    ])
    if "đi làm" in cleaned and not any(neg in cleaned for neg in ["nghỉ làm", "không đi làm", "chưa đi làm"]):
        has_occasion = True

    # Check specific garment or style hints
    has_garment_or_style = any(g in cleaned for g in [
        "polo", "sơ mi", "chinos", "jean", "jacket", "khoác", "blazer",
        "cardigan", "hoodie", "váy", "đầm", "sneaker", "thanh lịch",
        "lịch sự", "sang trọng", "chỉn chu", "đơn giản", "vest",
    ])

    if has_occasion or has_garment_or_style:
        return False

    return True


def extract_occasion(text: str) -> str:
    """Extract normalized occasion from Vietnamese query."""
    t = text.lower()
    if any(k in t for k in ["phỏng vấn", "xin việc", "interview"]):
        return "interview"
    if any(k in t for k in ["đám cưới", "tiệc cưới", "lễ cưới", "ăn cưới", "dự cưới", "wedding"]):
        return "wedding"
    if any(k in t for k in ["đi làm", "công sở", "văn phòng", "công ty", "đi dạy", "họp", "làm việc"]):
        if not any(neg in t for neg in ["nghỉ làm", "không đi làm", "không phải đi làm", "chưa đi làm"]):
            return "daily_work"
    if any(k in t for k in ["tiệc", "party", "dạ hội", "sinh nhật", "quán bar", "pub", "club"]):
        return "party"
    if any(k in t for k in ["hẹn hò", "date", "người yêu", "buổi hẹn"]):
        return "date"
    if any(k in t for k in ["cafe", "cà phê", "quán cafe", "uống cafe"]):
        return "cafe"
    if any(k in t for k in ["đi dạo", "dạo phố", "đi chơi", "cuối tuần", "chill", "ở nhà"]):
        return "casual"
    return "casual"


def extract_time_of_day(text: str, occasion: str) -> str:
    """Extract normalized time of day."""
    t = text.lower()
    if any(k in t for k in ["khuya", "đêm"]):
        return "night"
    if any(k in t for k in ["tối nay", "tối mai", "buổi tối", "tối", "chiều tối"]):
        return "evening"
    if any(k in t for k in ["trưa nay", "buổi trưa", "trưa", "chiều nay", "chiều mai", "buổi chiều", "chiều"]):
        return "afternoon"
    if any(k in t for k in ["sáng mai", "sáng nay", "buổi sáng", "sáng"]):
        return "morning"
    if occasion in ("wedding", "party", "date", "cafe"):
        return "evening"
    if occasion in ("daily_work", "interview"):
        return "morning"
    return "morning"


def extract_event_date(text: str, current_date: date) -> str | None:
    """Extract ISO date inferred from temporal words; None if no date specified."""
    t = text.lower()
    if any(k in t for k in ["ngày mai", "sáng mai", "tối mai", "chiều mai", "trưa mai"]):
        return (current_date + timedelta(days=1)).isoformat()
    if any(k in t for k in ["hôm nay", "tối nay", "sáng nay", "chiều nay", "trưa nay"]):
        return current_date.isoformat()
    return None


def extract_location(text: str, explicit_location: str | None = None) -> str | None:
    """Extract location text from explicit input or query string."""
    if explicit_location and explicit_location.strip():
        return explicit_location.strip()
    t = text.lower()
    for loc in COMMON_LOCATIONS:
        if loc in t:
            if loc in ("đà lạt", "đà nẵng", "hà nội", "sài gòn", "nha trang", "vũng tàu", "hải phòng", "cần thơ", "hội an", "quy nhơn", "phú quốc"):
                return " ".join(word.capitalize() for word in loc.split())
            if loc in ("tp.hcm", "tp hcm", "thành phố hồ chí minh"):
                return "TP.HCM"
            return loc.capitalize()
    return None


def extract_environment(text: str, occasion: str) -> str | None:
    """Extract environment: indoor, outdoor, or mixed."""
    t = text.lower()
    if any(k in t for k in ["ngoài trời", "outdoor", "vỉa hè", "công viên", "bờ hồ", "phố đi bộ", "sân vườn"]):
        return "outdoor"
    if any(k in t for k in ["trong nhà", "indoor", "văn phòng", "phòng máy lạnh", "trung tâm thương mại", "mall"]):
        return "indoor"
    if occasion == "daily_work":
        return "indoor"
    return None


def extract_weather(text: str) -> tuple[str, str]:
    """Extract weather condition with rain priority, negation detection, and API contract mapping."""
    t = text.lower()

    # 1. Rainy condition has top priority (critical for footwear/outerwear safety)
    rainy_kws = ["trời mưa", "mưa rào", "mưa phùn", "mưa"]
    for kw in rainy_kws:
        if kw in t and not _is_negated(t, kw) and not _is_negated(t, "mưa"):
            return "rainy", "user"

    # 2. Specific cold modifier per API_CONTRACT.md: 'hơi lạnh' -> 'cold'
    if ("hơi lạnh" in t or "rất lạnh" in t or "quá lạnh" in t) and not _is_negated(t, "lạnh"):
        return "cold", "user"

    # 3. Cool condition (includes 'se lạnh', 'mát mẻ', etc. before generic 'lạnh')
    cool_kws = ["se lạnh", "se mát", "mát mẻ", "trời mát", "dịu mát", "se se", "mát"]
    for kw in cool_kws:
        if kw in t and not _is_negated(t, kw):
            return "cool", "user"

    # 4. Cold condition: generic 'lạnh', 'rét', 'buốt'
    cold_kws = ["giá rét", "rét", "buốt", "lạnh", "mùa đông"]
    for kw in cold_kws:
        if kw in t and not _is_negated(t, kw) and not _is_negated(t, "lạnh"):
            return "cold", "user"

    # 5. Hot condition
    hot_kws = ["nắng nóng", "nóng nực", "trời nóng", "trời nắng", "nóng", "nắng", "oi bức", "nực", "mùa hè"]
    for kw in hot_kws:
        if kw in t and not _is_negated(t, kw) and not _is_negated(t, "nóng") and not _is_negated(t, "nắng"):
            return "hot", "user"

    # 6. Warm condition
    warm_kws = ["ấm áp", "ấm"]
    for kw in warm_kws:
        if kw in t and not _is_negated(t, kw):
            return "warm", "user"

    return "cool", "default"


def extract_formality_range(text: str, occasion: str) -> list[int]:
    """Determine target formality range [min, max] on 1-5 scale."""
    t = text.lower()

    if occasion in ("wedding", "interview"):
        base_range = [4, 5]
    elif occasion == "daily_work":
        base_range = [3, 4]
    elif occasion == "party":
        base_range = [3, 4]
    elif occasion in ("cafe", "date"):
        base_range = [2, 3]
    else:
        base_range = [1, 2]

    # Modifiers
    if any(k in t for k in ["lịch sự nhẹ", "thanh lịch nhẹ", "chỉnh chu nhẹ"]):
        base_range = [2, 3]
    elif any(k in t for k in ["trang trọng", "chỉnh chu", "lịch thiệp", "sang trọng", "lịch sự"]):
        base_range = [max(base_range[0], 3), min(5, max(base_range[1], 4))]
    elif any(k in t for k in ["thoải mái", "đơn giản", "tiện lợi", "thoải mái nhất"]):
        base_range = [max(1, base_range[0] - 1), max(2, base_range[1] - 1)]

    if base_range[1] - base_range[0] > 2:
        base_range[1] = base_range[0] + 2

    return base_range


def extract_style_hints(text: str) -> list[str]:
    """Extract style hints: smart_casual, minimalist, streetwear, vintage, casual, formal."""
    t = text.lower()
    styles = []
    if any(k in t for k in ["smart casual", "smart_casual", "lịch sự nhẹ", "thanh lịch", "lịch sự", "chỉnh chu"]):
        styles.append("smart_casual")
    if any(k in t for k in ["tối giản", "minimalist", "minimalism", "đơn giản"]):
        styles.append("minimalist")
    if any(k in t for k in ["streetwear", "đường phố", "bụi bặm", "cool ngầu"]):
        styles.append("streetwear")
    if any(k in t for k in ["vintage", "cổ điển", "retro"]):
        styles.append("vintage")
    if any(k in t for k in ["trang trọng", "sang trọng", "formal"]):
        styles.append("formal")
    if any(k in t for k in ["casual", "năng động", "thoải mái"]):
        styles.append("casual")
    return list(dict.fromkeys(styles))


def extract_vibe_keywords(text: str) -> list[str]:
    """Extract atmospheric and subjective vibe keywords."""
    t = text.lower()
    vibes = []
    vibe_candidates = [
        "lịch sự nhẹ",
        "lịch sự",
        "thoải mái",
        "thanh lịch",
        "năng động",
        "ấm áp",
        "trẻ trung",
        "tinh tế",
        "chỉnh chu",
        "nhẹ nhàng",
        "nổi bật",
    ]
    for candidate in vibe_candidates:
        if candidate in t:
            if any(candidate != existing and candidate in existing for existing in vibes):
                continue
            vibes.append(candidate)

    filtered_vibes = []
    for v in vibes:
        if not any(v != other and v in other for other in vibes):
            filtered_vibes.append(v)
    return list(dict.fromkeys(filtered_vibes))


SPECIFIC_GARMENT_DEFS: list[tuple[list[str], WardrobeCategory, str, str | None]] = [
    # Outerwear (Checked first to prevent 'áo' from capturing jacket/blazer/vest)
    (["áo khoác", "khoác", "jacket"], WardrobeCategory.OUTERWEAR, "jacket", None),
    (["áo blazer", "blazer"], WardrobeCategory.OUTERWEAR, "blazer", None),
    (["áo vest", "vest", "veston", "suit jacket"], WardrobeCategory.OUTERWEAR, "blazer", None),
    (["áo cardigan", "cardigan"], WardrobeCategory.OUTERWEAR, "cardigan", None),
    (["áo hoodie", "hoodie"], WardrobeCategory.OUTERWEAR, "hoodie", None),

    # Dresses
    (["váy đầm", "đầm hoa", "váy hoa", "đầm", "váy", "dress"], WardrobeCategory.DRESS, "dress", None),

    # Footwear
    (["giày da", "giày tây"], WardrobeCategory.FOOTWEAR, "oxford", "leather"),
    (["giày sneaker", "giày thể thao", "sneaker", "sneakers"], WardrobeCategory.FOOTWEAR, "sneakers", None),
    (["giày lười", "giày loafer", "loafer", "loafers"], WardrobeCategory.FOOTWEAR, "loafers", None),
    (["giày sandal", "dép sandal", "sandal", "sandals"], WardrobeCategory.FOOTWEAR, "sandals", None),
    (["giày boots", "boots", "bốt"], WardrobeCategory.FOOTWEAR, "boots", None),

    # Bottoms
    (["quần chinos", "chinos"], WardrobeCategory.BOTTOM, "chinos", None),
    (["quần jean", "quần jeans", "quần bò", "jean", "jeans"], WardrobeCategory.BOTTOM, "jeans", None),
    (["quần tây", "quần âu", "trousers"], WardrobeCategory.BOTTOM, "trousers", None),
    (["quần kaki", "kaki"], WardrobeCategory.BOTTOM, "chinos", None),
    (["quần short", "quần soóc", "shorts"], WardrobeCategory.BOTTOM, "shorts", None),

    # Tops
    (["áo polo", "polo"], WardrobeCategory.TOP, "polo", None),
    (["áo sơ mi", "sơ mi", "shirt"], WardrobeCategory.TOP, "shirt", None),
    (["áo thun", "áo phông", "t-shirt", "thun"], WardrobeCategory.TOP, "t-shirt", None),
]

GENERIC_CATEGORY_DEFS: list[tuple[list[str], WardrobeCategory]] = [
    (["áo"], WardrobeCategory.TOP),
    (["quần"], WardrobeCategory.BOTTOM),
    (["giày", "dép"], WardrobeCategory.FOOTWEAR),
]

COLOR_CANONICAL_MAP: dict[str, str] = {
    "màu đen": "black", "đen": "black",
    "màu trắng": "white", "trắng": "white",
    "màu xanh navy": "navy", "xanh navy": "navy", "navy": "navy",
    "màu xanh dương": "blue", "xanh dương": "blue",
    "màu xanh lá": "green", "xanh lá": "green",
    "màu xanh": "blue", "xanh": "blue",
    "màu đỏ": "red", "đỏ": "red",
    "màu vàng": "yellow", "vàng": "yellow",
    "màu xám": "grey", "xám": "grey", "màu ghi": "grey", "ghi": "grey",
    "màu nâu": "brown", "nâu": "brown",
    "màu be": "beige", "be": "beige",
    "màu kem": "cream", "kem": "cream",
    "màu hồng": "pink", "hồng": "pink",
    "màu tím": "purple", "tím": "purple",
    "màu cam": "orange", "cam": "orange",
}

MATERIAL_CANONICAL_MAP: dict[str, str] = {
    "da": "leather",
    "cotton": "cotton",
    "denim": "denim",
    "linen": "linen",
    "len": "wool",
}


def _parse_single_constraint(phrase: str) -> GarmentConstraint | None:
    p = phrase.strip().lower()
    if not p:
        return None

    matched_cat: WardrobeCategory | None = None
    matched_sub: str | None = None
    matched_mat: str | None = None
    matched_garment_kw: str | None = None
    is_category_only = False

    # 1. Check specific garments (longest keywords first)
    for kws, cat, sub, mat in SPECIFIC_GARMENT_DEFS:
        for kw in sorted(kws, key=len, reverse=True):
            if kw in p:
                matched_cat = cat
                matched_sub = sub
                matched_mat = mat
                matched_garment_kw = kw
                break
        if matched_cat is not None:
            break

    # 2. If no specific garment, check generic category keywords
    if matched_cat is None:
        for kws, cat in GENERIC_CATEGORY_DEFS:
            for kw in kws:
                if re.search(rf"\b{re.escape(kw)}\b", p):
                    matched_cat = cat
                    matched_garment_kw = kw
                    is_category_only = True
                    break
            if matched_cat is not None:
                break

    # 3. Check color in phrase
    matched_color: str | None = None
    matched_color_kw: str | None = None
    for color_kw, canonical_color in sorted(COLOR_CANONICAL_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if color_kw in p:
            matched_color = canonical_color
            matched_color_kw = color_kw
            break

    # 4. Check material in phrase if not already set
    if matched_mat is None:
        for mat_kw, canonical_mat in MATERIAL_CANONICAL_MAP.items():
            if re.search(rf"\b{re.escape(mat_kw)}\b", p):
                matched_mat = canonical_mat
                break

    if matched_cat is None and matched_color is None and matched_mat is None:
        return None

    # Construct clean raw_text
    parts = []
    if matched_garment_kw:
        parts.append(matched_garment_kw)
    if matched_color_kw and (matched_garment_kw is None or matched_color_kw not in matched_garment_kw):
        parts.append(matched_color_kw)
    raw_text = " ".join(parts) if parts else p

    return GarmentConstraint(
        category=matched_cat,
        sub_category=matched_sub,
        color=matched_color,
        material=matched_mat,
        raw_text=raw_text,
        is_category_only=is_category_only,
    )


def extract_constraints(
    text: str,
) -> tuple[list[str], list[str], list[GarmentConstraint], list[GarmentConstraint]]:
    """Extract explicit exclusions (must_avoid) and inclusions (must_have) with structured bindings."""
    t = text.lower()
    raw_must_have: list[str] = []
    raw_must_avoid: list[str] = []
    structured_must_have: list[GarmentConstraint] = []
    structured_must_avoid: list[GarmentConstraint] = []

    # Split into clauses by punctuation to handle compound sentences
    clauses = re.split(r"[,;.]|\bnhưng\b", t)

    avoid_triggers = [
        "không mặc", "tránh", "không thích", "đừng chọn", "không muốn",
        "ghét", "đừng phối", "đừng mang", "không mang",
    ]
    have_triggers = [
        "muốn mặc", "thích mặc", "thích", "cần mặc", "cần đi",
        "ưu tiên", "muốn", "phải có", "phải mang", "phải mặc",
    ]

    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue

        # Check for avoid triggers
        for trig in avoid_triggers:
            if trig in clause:
                idx = clause.find(trig) + len(trig)
                rest = clause[idx:].strip()
                items = [item.strip() for item in re.split(r"\bvà\b|\bhoặc\b", rest)]
                for item in items:
                    c = _parse_single_constraint(item)
                    if c is not None:
                        structured_must_avoid.append(c)
                        raw_must_avoid.append(c.raw_text)

        # Check for have triggers
        for trig in have_triggers:
            if trig in clause and not any(neg in clause for neg in ["không ", "chẳng ", "đừng ", "chưa "]):
                idx = clause.find(trig) + len(trig)
                rest = clause[idx:].strip()
                items = [item.strip() for item in re.split(r"\bvà\b|\bhoặc\b", rest)]
                for item in items:
                    if any(v in item for v in ["lịch sự", "thoải mái", "đẹp", "xinh", "ngầu", "chỉnh chu"]):
                        continue
                    c = _parse_single_constraint(item)
                    if c is not None:
                        structured_must_have.append(c)
                        raw_must_have.append(c.raw_text)

    # Deduplicate while preserving order
    dedup_raw_have = list(dict.fromkeys(raw_must_have))
    dedup_raw_avoid = list(dict.fromkeys(raw_must_avoid))
    return dedup_raw_have, dedup_raw_avoid, structured_must_have, structured_must_avoid


def extract_context(
    query: str,
    location: str | None = None,
    current_date: date | None = None,
) -> StylistContext:
    """Analyze a Vietnamese query and produce a structured StylistContext using Vietnam local time."""
    norm_query = normalize_text(query)
    today = current_date or datetime.now(VIETNAM_TZ).date()

    # Ambiguity check
    if is_ambiguous_query(norm_query):
        return StylistContext(
            occasion="casual",
            time_of_day="morning",
            event_date=extract_event_date(norm_query, today),
            location_text=location,
            environment=None,
            weather_condition="warm",
            temperature_celsius=None,
            target_formality_range=[2, 3],
            style_hints=[],
            vibe_keywords=[],
            must_have=[],
            must_avoid=[],
            structured_must_have=[],
            structured_must_avoid=[],
            weather_source="default",
            needs_clarification=True,
            clarification_question=CLARIFICATION_PROMPT_VI,
            confidence=0.3,
        )

    occasion = extract_occasion(norm_query)
    time_of_day = extract_time_of_day(norm_query, occasion)
    event_date = extract_event_date(norm_query, today)
    location_text = extract_location(norm_query, location)
    environment = extract_environment(norm_query, occasion)
    weather_condition, weather_source = extract_weather(norm_query)
    target_formality_range = extract_formality_range(norm_query, occasion)
    style_hints = extract_style_hints(norm_query)
    vibe_keywords = extract_vibe_keywords(norm_query)
    must_have, must_avoid, struct_have, struct_avoid = extract_constraints(norm_query)

    # Calibrated confidence scoring based on explicitly stated vs defaulted attributes
    has_explicit_occasion = any(k in norm_query.lower() for k in [
        "phỏng vấn", "xin việc", "interview", "đám cưới", "tiệc cưới", "lễ cưới",
        "ăn cưới", "dự cưới", "wedding", "công sở", "văn phòng", "công ty",
        "đi dạy", "họp", "làm việc", "tiệc", "party", "dạ hội", "sinh nhật",
        "quán bar", "pub", "club", "hẹn hò", "date", "người yêu", "buổi hẹn",
        "cafe", "cà phê", "quán cafe", "uống cafe", "đi dạo", "dạo phố",
        "đi chơi", "cuối tuần", "chill", "ở nhà",
    ]) or ("đi làm" in norm_query.lower() and not any(neg in norm_query.lower() for neg in ["nghỉ làm", "không đi làm", "chưa đi làm"]))

    confidence = 0.95
    if not has_explicit_occasion:
        confidence -= 0.15
    if weather_source == "default":
        confidence -= 0.10
    confidence = round(max(0.3, min(1.0, confidence)), 2)

    return StylistContext(
        occasion=occasion,
        time_of_day=time_of_day,
        event_date=event_date,
        location_text=location_text,
        environment=environment,
        weather_condition=weather_condition,
        temperature_celsius=None,
        target_formality_range=target_formality_range,
        style_hints=style_hints,
        vibe_keywords=vibe_keywords,
        must_have=must_have,
        must_avoid=must_avoid,
        structured_must_have=struct_have,
        structured_must_avoid=struct_avoid,
        weather_source=weather_source,
        needs_clarification=False,
        clarification_question=None,
        confidence=confidence,
    )


CONTEXT_FALLBACK_WARNING = "Không thể phân tích đầy đủ yêu cầu bằng dịch vụ AI; đã dùng quy tắc dự phòng."
WEATHER_FALLBACK_WARNING = "Không thể lấy dữ liệu thời tiết; đã dùng thông tin trong yêu cầu hoặc giá trị mặc định."


def extract_context_with_providers(
    query: str,
    *,
    location: str | None = None,
    current_date: date | None = None,
    llm_provider: ContextLLMProviderProtocol | None = None,
    weather_provider: WeatherProviderProtocol | None = None,
) -> tuple[StylistContext, list[str]]:
    """Extract context through an optional provider, with deterministic fallbacks.

    Explicit weather and garment constraints parsed from the user's query always
    override provider output. Weather enrichment runs only when both location and
    event date are known and the user did not state the weather.
    """
    today = current_date or datetime.now(VIETNAM_TZ).date()
    fallback = extract_context(query, location=location, current_date=today)
    warnings: list[str] = []
    context = fallback

    if llm_provider is not None:
        try:
            provider_payload = llm_provider.extract_context(
                query=query,
                location=location,
                current_date=today,
            )
            context = StylistContext.model_validate(provider_payload)
        except Exception:
            context = fallback
            warnings.append(CONTEXT_FALLBACK_WARNING)

    updates: dict[str, Any] = {}
    if fallback.location_text is not None:
        updates["location_text"] = fallback.location_text
    if fallback.event_date is not None:
        updates["event_date"] = fallback.event_date
    if fallback.must_have:
        updates["must_have"] = fallback.must_have
        updates["structured_must_have"] = fallback.structured_must_have
    if fallback.must_avoid:
        updates["must_avoid"] = fallback.must_avoid
        updates["structured_must_avoid"] = fallback.structured_must_avoid
    if fallback.weather_source == "user":
        updates["weather_condition"] = fallback.weather_condition
        updates["weather_source"] = "user"
        updates["temperature_celsius"] = fallback.temperature_celsius
    if updates:
        context = context.model_copy(update=updates)

    if (
        weather_provider is not None
        and not context.needs_clarification
        and context.weather_source == "default"
        and context.location_text
        and context.event_date
    ):
        try:
            weather = weather_provider.get_weather(
                location=context.location_text,
                event_date=date.fromisoformat(context.event_date),
            )
            context = context.model_copy(
                update={
                    "weather_condition": weather.condition,
                    "temperature_celsius": weather.temperature_celsius,
                    "weather_source": "api",
                }
            )
        except Exception:
            warnings.append(WEATHER_FALLBACK_WARNING)

    return context, warnings


def context_agent_node(
    state: StylistGraphState,
    *,
    current_date: date | None = None,
    llm_provider: ContextLLMProviderProtocol | None = None,
    weather_provider: WeatherProviderProtocol | None = None,
) -> dict[str, Any]:
    """LangGraph node execution function for the Context Agent."""
    query = state.get("user_query", "")
    location = state.get("location")
    context, warnings = extract_context_with_providers(
        query,
        location=location,
        current_date=current_date,
        llm_provider=llm_provider,
        weather_provider=weather_provider,
    )
    return {
        "context": context,
        "warnings": list(state.get("warnings", [])) + warnings,
    }
