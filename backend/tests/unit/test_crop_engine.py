from __future__ import annotations

from io import BytesIO
import pytest
from PIL import Image

from app.services.crop_engine import crop_item_and_generate_thumbnail


def _create_solid_image(width: int, height: int, color: tuple[int, int, int] = (200, 200, 200)) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _create_four_quadrant_image(size: int = 200) -> bytes:
    """Create a 200x200 image with 4 distinct colored quadrants:

    - Top-Left: Red (255, 0, 0)
    - Top-Right: Green (0, 255, 0)
    - Bottom-Left: Blue (0, 0, 255)
    - Bottom-Right: Yellow (255, 255, 0)
    """
    half = size // 2
    img = Image.new("RGB", (size, size))
    for x in range(size):
        for y in range(size):
            if x < half and y < half:
                img.putpixel((x, y), (255, 0, 0))  # Top-Left: Red
            elif x >= half and y < half:
                img.putpixel((x, y), (0, 255, 0))  # Top-Right: Green
            elif x < half and y >= half:
                img.putpixel((x, y), (0, 0, 255))  # Bottom-Left: Blue
            else:
                img.putpixel((x, y), (255, 255, 0))  # Bottom-Right: Yellow

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestCropEngineCoordinatesAndValidation:
    """Unit tests for canonical [x_min, y_min, x_max, y_max] coordinate order and validation."""

    def test_landscape_image_asymmetric_crop(self) -> None:
        raw_bytes = _create_solid_image(1000, 500)
        # Canonical: x in [0.10, 0.40] (width 300px), y in [0.60, 0.90] (height 150px)
        box = (0.10, 0.60, 0.40, 0.90)
        cropped = crop_item_and_generate_thumbnail(raw_bytes, box)

        assert cropped.crop_width == 300
        assert cropped.crop_height == 150
        assert cropped.crop_mime_type == "image/png"
        assert cropped.thumb_mime_type == "image/webp"

    def test_portrait_image_asymmetric_crop(self) -> None:
        raw_bytes = _create_solid_image(600, 1200)
        # Canonical: x in [0.20, 0.80] (width 360px), y in [0.10, 0.50] (height 480px)
        box = (0.20, 0.10, 0.80, 0.50)
        cropped = crop_item_and_generate_thumbnail(raw_bytes, box)

        assert cropped.crop_width == 360
        assert cropped.crop_height == 480

    def test_synthetic_four_quadrant_color_crop(self) -> None:
        raw_bytes = _create_four_quadrant_image(200)
        # Select Bottom-Left quadrant: x in [0.0, 0.5], y in [0.5, 1.0] -> MUST be Blue!
        box = (0.0, 0.5, 0.5, 1.0)
        cropped = crop_item_and_generate_thumbnail(raw_bytes, box)

        with Image.open(BytesIO(cropped.crop_bytes)) as c_img:
            # Convert to RGB to ignore alpha if present
            rgb_img = c_img.convert("RGB")
            center_pixel = rgb_img.getpixel((rgb_img.width // 2, rgb_img.height // 2))
            # Bottom-Left is Blue: (0, 0, 255)
            assert center_pixel == (0, 0, 255), f"Expected Blue (0, 0, 255), got {center_pixel}"

        # Select Top-Right quadrant: x in [0.5, 1.0], y in [0.0, 0.5] -> MUST be Green!
        box_top_right = (0.5, 0.0, 1.0, 0.5)
        cropped_tr = crop_item_and_generate_thumbnail(raw_bytes, box_top_right)
        with Image.open(BytesIO(cropped_tr.crop_bytes)) as c_img:
            rgb_img = c_img.convert("RGB")
            center_pixel = rgb_img.getpixel((rgb_img.width // 2, rgb_img.height // 2))
            assert center_pixel == (0, 255, 0), f"Expected Green (0, 255, 0), got {center_pixel}"

    def test_reject_negative_coordinates(self) -> None:
        raw_bytes = _create_solid_image(100, 100)
        with pytest.raises(ValueError) as exc_info:
            crop_item_and_generate_thumbnail(raw_bytes, (-0.1, 0.1, 0.5, 0.5))
        assert "Invalid or degenerate" in str(exc_info.value)

    def test_reject_greater_than_one_coordinates(self) -> None:
        raw_bytes = _create_solid_image(100, 100)
        with pytest.raises(ValueError) as exc_info:
            crop_item_and_generate_thumbnail(raw_bytes, (0.1, 0.1, 1.05, 0.5))
        assert "Invalid or degenerate" in str(exc_info.value)

    def test_reject_inverted_x_coordinates(self) -> None:
        raw_bytes = _create_solid_image(100, 100)
        with pytest.raises(ValueError) as exc_info:
            crop_item_and_generate_thumbnail(raw_bytes, (0.8, 0.1, 0.2, 0.5))
        assert "Invalid or degenerate" in str(exc_info.value)

    def test_reject_inverted_y_coordinates(self) -> None:
        raw_bytes = _create_solid_image(100, 100)
        with pytest.raises(ValueError) as exc_info:
            crop_item_and_generate_thumbnail(raw_bytes, (0.1, 0.8, 0.5, 0.2))
        assert "Invalid or degenerate" in str(exc_info.value)

    def test_reject_zero_area_coordinates(self) -> None:
        raw_bytes = _create_solid_image(100, 100)
        with pytest.raises(ValueError) as exc_info:
            crop_item_and_generate_thumbnail(raw_bytes, (0.3, 0.2, 0.3, 0.8))
        assert "Invalid or degenerate" in str(exc_info.value)
