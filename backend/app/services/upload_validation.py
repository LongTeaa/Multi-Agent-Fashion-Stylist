from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from typing import Final

from PIL import Image, UnidentifiedImageError

from app.schemas.common import ValidationError

MAX_FILE_SIZE_BYTES: Final[int] = 10 * 1024 * 1024  # 10 MB
MIN_PIXEL_DIMENSION: Final[int] = 64
MAX_PIXEL_DIMENSION: Final[int] = 10000

SUPPORTED_FORMATS: Final[dict[str, tuple[str, str]]] = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}


@dataclass(frozen=True)
class ValidatedImage:
    raw_bytes: bytes
    mime_type: str
    extension: str
    width: int
    height: int
    size_bytes: int
    sha256: str


def validate_image_bytes(raw_bytes: bytes) -> ValidatedImage:
    """Validate image bytes for MIME type, size limit, and pixel dimensions.

    Raises:
        ValidationError: If the image is invalid, corrupted, disguised, too large, or too small.
    """
    size_bytes = len(raw_bytes)
    if size_bytes == 0:
        raise ValidationError(
            message="Tệp tải lên rỗng. Vui lòng kiểm tra lại.",
            details={"reason": "empty_file"},
        )

    if size_bytes > MAX_FILE_SIZE_BYTES:
        raise ValidationError(
            message="Dung lượng ảnh vượt quá giới hạn 10MB.",
            details={"size_bytes": size_bytes, "max_bytes": MAX_FILE_SIZE_BYTES},
        )

    try:
        # First verification pass: read header and verify integrity
        with Image.open(BytesIO(raw_bytes)) as img:
            img_format = img.format
            img_width, img_height = img.size

        if img_format not in SUPPORTED_FORMATS:
            raise ValidationError(
                message="Định dạng ảnh không được hỗ trợ. Chỉ chấp nhận JPEG, PNG hoặc WebP.",
                details={"format": img_format},
            )
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ValidationError(
            message="Tệp ảnh không hợp lệ hoặc bị hỏng.",
            details={"error": str(error)},
        ) from error

    if img_width < MIN_PIXEL_DIMENSION or img_height < MIN_PIXEL_DIMENSION:
        raise ValidationError(
            message=f"Kích thước ảnh quá nhỏ. Tối thiểu phải từ {MIN_PIXEL_DIMENSION}x{MIN_PIXEL_DIMENSION} pixel.",
            details={"width": img_width, "height": img_height, "min_dimension": MIN_PIXEL_DIMENSION},
        )

    if img_width > MAX_PIXEL_DIMENSION or img_height > MAX_PIXEL_DIMENSION:
        raise ValidationError(
            message=f"Kích thước ảnh quá lớn. Tối đa không vượt quá {MAX_PIXEL_DIMENSION} pixel.",
            details={"width": img_width, "height": img_height, "max_dimension": MAX_PIXEL_DIMENSION},
        )

    mime_type, extension = SUPPORTED_FORMATS[img_format]
    sha256_hash = hashlib.sha256(raw_bytes).hexdigest()

    return ValidatedImage(
        raw_bytes=raw_bytes,
        mime_type=mime_type,
        extension=extension,
        width=img_width,
        height=img_height,
        size_bytes=size_bytes,
        sha256=sha256_hash,
    )
