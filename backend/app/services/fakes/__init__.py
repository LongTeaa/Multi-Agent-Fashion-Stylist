from __future__ import annotations

from app.services.fakes.image_fakes import FakeImageProvider
from app.services.fakes.vision_fakes import FakeDetector, FakeVisionProvider

__all__ = ["FakeDetector", "FakeImageProvider", "FakeVisionProvider"]
