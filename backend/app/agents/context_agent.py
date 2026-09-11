from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re
from typing import Any
import unicodedata

from app.agents.state import StylistContext, StylistGraphState

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

# Ambiguity patterns - queries that have no actionable context
AMBIGUOUS_PATTERNS = [
    r"^(hôm nay\s+)?mặc gì(\s+bây giờ|\s+đây|\s+nhỉ|\s+ta)?\??$",
    r"^tôi nên mặc gì(\s+bây giờ|\s+đây|\s+nhỉ|\s+ta)?\??$",
    r"^nên mặc gì(\s+bây giờ|\s+đây|\s+nhỉ|\s+ta)?\??$",
    r"^tư vấn (phối đồ|đồ|quần áo)\??$",
    r"^gợi ý (đồ|quần áo|set đồ)( cho tôi)?\??$",
    r"^phối đồ giúp tôi\??$",
]


def normalize_text(text: str) -> str:
    """Normalize text using Unicode NFKC and strip excess whitespace."""
    return unicodedata.normalize("NFKC", text).strip()


def is_ambiguous_query(text: str) -> bool:
    """Check whether a query lacks minimum actionable styling context."""
    normalized = normalize_text(text).lower()
    cleaned = re.sub(r"[?!.,]", "", normalized).strip()

    for pattern in AMBIGUOUS_PATTERNS:
        if re.search(pattern, cleaned):
            return True

    # Check if query is very short and has no occasion, garment, weather, or location
    tokens = cleaned.split()
    if len(tokens) <= 3:
        has_any_signal = False
        signal_keywords = [
            "cafe", "cà phê", "làm", "cưới", "tiệc", "hẹn", "chơi", "dạo", "phỏng vấn",
            "mát", "lạnh", "nóng", "mưa", "ấm",
            "áo", "quần", "váy", "đầm", "giày", "polo", "sơ mi", "jean",
            "đà lạt", "hà nội", "sài gòn",
        ]
        for kw in signal_keywords:
            if kw in cleaned:
                has_any_signal = True
                break
        if not has_any_signal:
            return True

    return False


def extract_occasion(text: str) -> str:
    """Extract normalized occasion from Vietnamese query."""
    t = text.lower()
    if any(k in t for k in ["phỏng vấn", "xin việc", "interview"]):
        return "interview"
    if any(k in t for k in ["đám cưới", "tiệc cưới", "lễ cưới", "ăn cưới", "dự cưới", "wedding"]):
        return "wedding"
    if any(k in t for k in ["đi làm", "công sở", "văn phòng", "công ty", "đi dạy", "họp", "làm việc"]):
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
    """Extract ISO date inferred from temporal words."""
    t = text.lower()
    if any(k in t for k in ["ngày mai", "sáng mai", "tối mai", "chiều mai", "trưa mai"]):
        return (current_date + timedelta(days=1)).isoformat()
    if any(k in t for k in ["hôm nay", "tối nay", "sáng nay", "chiều nay", "trưa nay"]):
        return current_date.isoformat()
    return current_date.isoformat()


def extract_location(text: str, explicit_location: str | None = None) -> str | None:
    """Extract location text from explicit input or query string."""
    if explicit_location and explicit_location.strip():
        return explicit_location.strip()
    t = text.lower()
    for loc in COMMON_LOCATIONS:
        if loc in t:
            # Capitalize nicely for common cities
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
    """Extract weather condition and determine its source ('user' vs 'default')."""
    t = text.lower()
    # Check cool first for phrases like 'se lạnh', 'hơi lạnh', 'trời mát'
    if any(k in t for k in ["se lạnh", "hơi lạnh", "se mát", "mát mẻ", "trời mát", "mát", "dịu mát"]):
        return "cool", "user"
    if any(k in t for k in ["lạnh", "buốt", "giá rét", "rét", "mùa đông"]):
        return "cold", "user"
    if any(k in t for k in ["nắng nóng", "nóng nực", "trời nắng", "nắng", "oi bức", "nực", "mùa hè"]):
        return "hot", "user"
    if any(k in t for k in ["ấm áp", "ấm"]):
        return "warm", "user"
    if any(k in t for k in ["mưa", "trời mưa", "mưa rào", "mưa phùn"]):
        return "rainy", "user"
    return "cool", "default"


def extract_formality_range(text: str, occasion: str) -> list[int]:
    """Determine target formality range [min, max] on 1-5 scale."""
    t = text.lower()

    # Base range by occasion
    if occasion in ("wedding", "interview"):
        base_range = [4, 5]
    elif occasion == "daily_work":
        base_range = [3, 4]
    elif occasion == "party":
        base_range = [3, 4]
    elif occasion in ("cafe", "date"):
        base_range = [2, 3]
    else:  # casual
        base_range = [1, 2]

    # Modifiers
    if any(k in t for k in ["lịch sự nhẹ", "thanh lịch nhẹ", "chỉnh chu nhẹ"]):
        base_range = [2, 3]
    elif any(k in t for k in ["trang trọng", "chỉnh chu", "lịch thiệp", "sang trọng", "lịch sự"]):
        base_range = [max(base_range[0], 3), min(5, max(base_range[1], 4))]
    elif any(k in t for k in ["thoải mái", "đơn giản", "tiện lợi", "thoải mái nhất"]):
        base_range = [max(1, base_range[0] - 1), max(2, base_range[1] - 1)]

    # Invariant: span must not exceed 2 levels
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
            # If a more specific candidate already captured this (e.g. "lịch sự nhẹ" covers "lịch sự"), skip
            if any(candidate != existing and candidate in existing for existing in vibes):
                continue
            vibes.append(candidate)

    # Filter out shorter substrings if a longer phrase was added later
    filtered_vibes = []
    for v in vibes:
        if not any(v != other and v in other for other in vibes):
            filtered_vibes.append(v)
    return list(dict.fromkeys(filtered_vibes))


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


def extract_constraints(text: str) -> tuple[list[str], list[str]]:
    """Extract explicit exclusions (must_avoid) and inclusions (must_have)."""
    t = text.lower()
    must_have: list[str] = []
    must_avoid: list[str] = []

    # Patterns for must_avoid
    avoid_patterns = [
        r"(?:không mặc|tránh|không thích|đừng chọn|không muốn)\s+(màu\s+[a-zà-ỹ]+|[a-zà-ỹ\s]+?)(?:,|$|\.|\bvà\b|\bnhưng\b)",
    ]
    for pattern in avoid_patterns:
        for match in re.finditer(pattern, t):
            val = match.group(1).strip()
            # Ensure it references a garment or color
            if any(g in val for g in GARMENT_KEYWORDS) or any(c in val for c in COLOR_KEYWORDS):
                must_avoid.append(val)

    # Patterns for must_have
    have_patterns = [
        r"(?:muốn mặc|thích mặc|thích|cần mặc|cần đi|ưu tiên|muốn)\s+(áo\s+[a-zà-ỹ]+|quần\s+[a-zà-ỹ]+|váy\s*[a-zà-ỹ]*|đầm\s*[a-zà-ỹ]*|giày\s*[a-zà-ỹ]*|polo|sneaker|[a-zà-ỹ\s]+?)(?:,|$|\.|\bvà\b|\bnhưng\b)",
    ]
    for pattern in have_patterns:
        for match in re.finditer(pattern, t):
            val = match.group(1).strip()
            # Ensure it references a garment or color, and not a vibe/occasion/common verb
            is_garment_or_color = any(g in val for g in GARMENT_KEYWORDS) or any(c in val for c in COLOR_KEYWORDS)
            is_vibe = any(v in val for v in ["lịch sự", "thoải mái", "đẹp", "xinh", "ngầu", "chỉnh chu", "thanh lịch"])
            if is_garment_or_color and not is_vibe:
                must_have.append(val)

    return list(dict.fromkeys(must_have)), list(dict.fromkeys(must_avoid))


def extract_context(
    query: str,
    location: str | None = None,
    current_date: date | None = None,
) -> StylistContext:
    """Analyze a Vietnamese query and produce a structured StylistContext."""
    norm_query = normalize_text(query)
    today = current_date or datetime.now(timezone.utc).date()

    # Ambiguity check
    if is_ambiguous_query(norm_query):
        return StylistContext(
            occasion="casual",
            time_of_day="morning",
            event_date=today.isoformat(),
            location_text=location,
            environment=None,
            weather_condition="warm",
            temperature_celsius=None,
            target_formality_range=[2, 3],
            style_hints=[],
            vibe_keywords=[],
            must_have=[],
            must_avoid=[],
            weather_source="default",
            needs_clarification=True,
            clarification_question=CLARIFICATION_PROMPT_VI,
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
    must_have, must_avoid = extract_constraints(norm_query)

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
        weather_source=weather_source,
        needs_clarification=False,
        clarification_question=None,
    )


def context_agent_node(state: StylistGraphState) -> dict[str, Any]:
    """LangGraph node execution function for the Context Agent."""
    query = state.get("user_query", "")
    context = extract_context(query)
    return {
        "context": context,
    }
