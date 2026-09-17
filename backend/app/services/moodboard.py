from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from app.models.entities import OutfitSlotRole

_CANVAS_SIZE = (768, 1024)
_BACKGROUND = "#F4F0E8"
_CARD = "#FFFEFA"
_INK = "#25231F"
_MUTED = "#706B61"
_ACCENT = "#985A3B"


@dataclass(frozen=True)
class MoodboardItem:
    asset_id: str
    slot: OutfitSlotRole
    name: str
    color: str
    image_bytes: bytes


@dataclass(frozen=True)
class MoodboardResult:
    image_bytes: bytes
    mime_type: str
    width: int
    height: int
    included_asset_ids: tuple[str, ...]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size=size)
    except OSError:
        return ImageFont.load_default(size=size)


def _open_crop(item: MoodboardItem) -> Image.Image:
    try:
        with Image.open(BytesIO(item.image_bytes)) as source:
            source.load()
            return source.convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ValueError(f"Asset {item.asset_id!r} is not a valid image.") from error


def _draw_card(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    item: MoodboardItem,
    box: tuple[int, int, int, int],
) -> None:
    left, top, right, bottom = box
    draw.rounded_rectangle(box, radius=26, fill=_CARD, outline="#DED8CD", width=2)

    label_height = 86
    image_box = (left + 24, top + 24, right - 24, bottom - label_height)
    image_width = image_box[2] - image_box[0]
    image_height = image_box[3] - image_box[1]
    crop = _open_crop(item)
    crop.thumbnail((image_width, image_height), Image.Resampling.LANCZOS)
    position = (
        image_box[0] + (image_width - crop.width) // 2,
        image_box[1] + (image_height - crop.height) // 2,
    )
    neutral_card = Image.new("RGBA", (image_width, image_height), "#F7F4EE")
    neutral_card.alpha_composite(crop, (position[0] - image_box[0], position[1] - image_box[1]))
    canvas.paste(neutral_card.convert("RGB"), image_box[:2])

    slot_name = item.slot.value.upper()
    safe_name = item.name.strip() or "Trang phục"
    safe_color = item.color.strip() or "Không xác định"
    draw.text((left + 24, bottom - 68), slot_name, font=_font(14), fill=_ACCENT)
    draw.text((left + 24, bottom - 45), safe_name, font=_font(20), fill=_INK)
    color_width = draw.textlength(safe_color, font=_font(15))
    draw.text((right - 24 - color_width, bottom - 42), safe_color, font=_font(15), fill=_MUTED)


def render_moodboard(items: Iterable[MoodboardItem]) -> MoodboardResult:
    """Render a vertical neutral-card moodboard from opaque or alpha item crops."""

    normalized_items = tuple(items)
    if not 2 <= len(normalized_items) <= 4:
        raise ValueError("A moodboard requires 2 to 4 outfit items.")

    canvas = Image.new("RGB", _CANVAS_SIZE, _BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    draw.text((48, 42), "MOODBOARD", font=_font(18), fill=_ACCENT)
    draw.text((48, 72), "Moodboard dự phòng", font=_font(38), fill=_INK)
    draw.text(
        (48, 122),
        "Bố cục minh họa từ các món đồ trong tủ của bạn",
        font=_font(17),
        fill=_MUTED,
    )

    gap = 22
    content_left, content_right = 48, _CANVAS_SIZE[0] - 48
    content_top, content_bottom = 178, _CANVAS_SIZE[1] - 48
    columns = 1 if len(normalized_items) == 2 else 2
    rows = (len(normalized_items) + columns - 1) // columns
    card_width = (content_right - content_left - gap * (columns - 1)) // columns
    card_height = (content_bottom - content_top - gap * (rows - 1)) // rows

    for index, item in enumerate(normalized_items):
        row, column = divmod(index, columns)
        left = content_left + column * (card_width + gap)
        top = content_top + row * (card_height + gap)
        _draw_card(canvas, draw, item, (left, top, left + card_width, top + card_height))

    buffer = BytesIO()
    canvas.save(buffer, format="WEBP", quality=88, method=6)
    return MoodboardResult(
        image_bytes=buffer.getvalue(),
        mime_type="image/webp",
        width=_CANVAS_SIZE[0],
        height=_CANVAS_SIZE[1],
        included_asset_ids=tuple(item.asset_id for item in normalized_items),
    )
