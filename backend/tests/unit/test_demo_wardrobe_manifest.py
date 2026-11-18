"""The demo wardrobe manifest must stay a coherent, licence-clean, verifiable fixture."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from app.models.entities import WardrobeCategory

MANIFEST = Path(__file__).resolve().parents[3] / "data" / "fixtures" / "demo_wardrobe_v1.json"
SOURCE_PREFIX = "https://raw.githubusercontent.com/alexeygrigorev/clothing-dataset/master/images/"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_declares_a_public_domain_source() -> None:
    manifest = _manifest()
    assert manifest["dataset_version"] == "demo-wardrobe-v1"
    assert manifest["source"]["license"] == "CC0-1.0"
    assert manifest["known_gaps"], "gaps such as missing bags must stay documented"


def test_every_item_is_unique_verifiable_and_maps_to_a_wardrobe_category() -> None:
    items = _manifest()["items"]
    valid_categories = {category.value for category in WardrobeCategory}

    assert 40 <= len(items) <= 60
    assert len({item["source_image_id"] for item in items}) == len(items)
    assert len({item["sha256"] for item in items}) == len(items)
    for item in items:
        assert re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
        assert item["source_url"] == f"{SOURCE_PREFIX}{item['source_image_id']}.jpg"
        assert item["expected_category"] in valid_categories


def test_each_persona_can_form_both_outfit_branches_where_applicable() -> None:
    items = _manifest()["items"]
    counts = Counter((item["persona"], item["expected_category"]) for item in items)

    assert {item["persona"] for item in items} == {"female", "male"}
    for persona in ("female", "male"):
        assert counts[(persona, "top")] >= 5
        assert counts[(persona, "bottom")] >= 4
        assert counts[(persona, "footwear")] >= 3
        assert counts[(persona, "outerwear")] >= 3
        assert counts[(persona, "accessory")] >= 1
    # The dress branch (dress + footwear) must be exercisable on real images.
    assert counts[("female", "dress")] >= 3


def test_rejected_candidates_are_not_in_the_wardrobe() -> None:
    manifest = _manifest()
    rejected = {entry["source_image_id"] for entry in manifest["rejected_candidates"]}
    assert rejected
    assert rejected.isdisjoint(item["source_image_id"] for item in manifest["items"])
