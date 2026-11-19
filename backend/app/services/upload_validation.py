from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from typing import Final

from PIL import Image, ImageOps, UnidentifiedImageError

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


_EXIF_ORIENTATION_TAG: Final[int] = 0x0112
_JPEG_COMMENT_KEYS: Final[frozenset[str]] = frozenset({"comment", "COM"})
_XMP_KEYS: Final[frozenset[str]] = frozenset({"xmp", "XML:com.adobe.xmp"})


def _has_personal_metadata(source: Image.Image) -> bool:
    """EXIF (camera, GPS, timestamps), XMP, JPEG comments, or PNG text chunks."""
    if len(source.getexif()) > 0:
        return True
    if _XMP_KEYS & source.info.keys() or _JPEG_COMMENT_KEYS & source.info.keys():
        return True
    return bool(getattr(source, "text", None))


def _strip_metadata(source: Image.Image, img_format: str) -> tuple[bytes, tuple[int, int]] | None:
    """Re-encode an upload without metadata, with its EXIF orientation applied.

    User photos are stored and sent to external providers (Gemini, FASHN), so EXIF
    GPS and device data MUST NOT survive. Pixels are rotated to the orientation that
    browsers display, so normalized crop coordinates address the visible image.
    Returns ``None`` when the upload has no metadata and can be kept byte for byte.
    The colour profile is kept; JPEG keeps its quantization tables and subsampling,
    so a photo that needs no rotation is not degraded to Pillow's default quality.
    """
    if not _has_personal_metadata(source):
        return None

    needs_rotation = source.getexif().get(_EXIF_ORIENTATION_TAG, 1) != 1
    clean = ImageOps.exif_transpose(source) if needs_rotation else source.copy()
    clean.info = {}  # Pillow 12 writes only metadata passed to save(); clear for safety.

    options: dict[str, object] = {}
    if "transparency" in source.info:
        options["transparency"] = source.info["transparency"]
    icc_profile = source.info.get("icc_profile")
    if icc_profile:
        options["icc_profile"] = icc_profile
    if img_format == "JPEG":
        from PIL import JpegImagePlugin

        options["qtables"] = getattr(source, "quantization", None) or "web_high"
        sampling = JpegImagePlugin.get_sampling(source)
        if sampling >= 0:
            options["subsampling"] = sampling
    elif img_format == "WEBP":
        options["quality"] = 95

    buffer = BytesIO()
    clean.save(buffer, format=img_format, **options)
    return buffer.getvalue(), clean.size


def validate_image_bytes(raw_bytes: bytes) -> ValidatedImage:
    """Validate image bytes for MIME type, size limit, and pixel dimensions.

    The returned bytes carry no EXIF, XMP, comment, or text metadata, and their pixels
    use the orientation the EXIF tag described.

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
    try:
        with Image.open(BytesIO(raw_bytes)) as source:
            sanitized = _strip_metadata(source, img_format)
    except (OSError, ValueError) as error:
        raise ValidationError(details={"reason": "invalid_image_orientation"}) from error
    if sanitized is not None:
        raw_bytes, (img_width, img_height) = sanitized
        size_bytes = len(raw_bytes)
        if size_bytes > MAX_FILE_SIZE_BYTES:
            raise ValidationError(details={"reason": "normalized_image_too_large"})
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
