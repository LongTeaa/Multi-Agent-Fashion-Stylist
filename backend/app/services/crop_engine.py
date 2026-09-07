from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO

from PIL import Image

from app.models.entities import BoundingBox


@dataclass(frozen=True)
class CroppedItem:
    crop_bytes: bytes
    crop_mime_type: str
    crop_extension: str
    crop_width: int
    crop_height: int
    crop_size_bytes: int
    crop_sha256: str

    thumb_bytes: bytes
    thumb_mime_type: str
    thumb_extension: str
    thumb_width: int
    thumb_height: int
    thumb_size_bytes: int
    thumb_sha256: str


def crop_item_and_generate_thumbnail(
    image_bytes: bytes,
    box: BoundingBox,
    thumbnail_size: tuple[int, int] = (256, 256),
) -> CroppedItem:
    """Crop an image candidate using normalized bounding box coordinates [ymin, xmin, ymax, xmax]

    and generate an optimized WebP thumbnail.
    """
    with Image.open(BytesIO(image_bytes)) as img:
        img_width, img_height = img.size

        # Normalized coordinates [ymin, xmin, ymax, xmax]
        ymin, xmin, ymax, xmax = box

        top = max(0, min(img_height, int(ymin * img_height)))
        left = max(0, min(img_width, int(xmin * img_width)))
        bottom = max(0, min(img_height, int(ymax * img_height)))
        right = max(0, min(img_width, int(xmax * img_width)))

        # Ensure non-degenerate dimensions
        if right <= left:
            right = min(img_width, left + 1)
        if bottom <= top:
            bottom = min(img_height, top + 1)

        cropped_img = img.crop((left, top, right, bottom))
        crop_w, crop_h = cropped_img.size

        # 1. Export Crop as PNG
        crop_buffer = BytesIO()
        cropped_img.save(crop_buffer, format="PNG")
        crop_bytes = crop_buffer.getvalue()
        crop_sha256 = hashlib.sha256(crop_bytes).hexdigest()

        # 2. Export Thumbnail as WebP
        thumb_img = cropped_img.copy()
        if thumb_img.mode not in ("RGB", "RGBA"):
            thumb_img = thumb_img.convert("RGBA" if "transparency" in thumb_img.info or thumb_img.mode == "LA" else "RGB")
        thumb_img.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)
        thumb_w, thumb_h = thumb_img.size

        thumb_buffer = BytesIO()
        thumb_img.save(thumb_buffer, format="WEBP", quality=85)
        thumb_bytes = thumb_buffer.getvalue()
        thumb_sha256 = hashlib.sha256(thumb_bytes).hexdigest()

        return CroppedItem(
            crop_bytes=crop_bytes,
            crop_mime_type="image/png",
            crop_extension="png",
            crop_width=crop_w,
            crop_height=crop_h,
            crop_size_bytes=len(crop_bytes),
            crop_sha256=crop_sha256,
            thumb_bytes=thumb_bytes,
            thumb_mime_type="image/webp",
            thumb_extension="webp",
            thumb_width=thumb_w,
            thumb_height=thumb_h,
            thumb_size_bytes=len(thumb_bytes),
            thumb_sha256=thumb_sha256,
        )
