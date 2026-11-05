"""Inspect crop guard boundaries offline; synthetic markers are not face detection."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys
from typing import Literal

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from PIL import Image, ImageDraw
from pydantic import BaseModel, Field

from app.models.entities import BoundingBox, InputKind
from app.services.classifier import classify_scene
from app.services.crop_engine import crop_item_and_generate_thumbnail
from app.services.crop_policy import AUTO_CROP_POLICY_VERSION, review_crop_boxes
from app.services.providers import BoundingBoxDetection, DetectionResult


class Candidate(BaseModel):
    box: BoundingBox
    label: str
    confidence: float = Field(ge=0, le=1)


class BoundaryCase(BaseModel):
    id: str
    source_kind: Literal["real_photo", "synthetic_markers"]
    source_file: str | None = None
    source_sha256: str | None = None
    scene: InputKind
    candidates: list[Candidate] = Field(min_length=1)
    protected_regions: list[BoundingBox]
    expect_expansion: bool
    expect_protected_increase: bool
    evidence_kind: Literal["guard", "positive_control", "negative_control"]


class BoundaryDataset(BaseModel):
    dataset_version: str
    policy_version: str
    synthetic_size: tuple[int, int]
    cases: list[BoundaryCase]


def pixels(box: BoundingBox, size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = size
    return int(box[0] * width), int(box[1] * height), int(box[2] * width), int(box[3] * height)


def draw_region(image: Image.Image, box: BoundingBox, fill: str | int) -> None:
    left, top, right, bottom = pixels(box, image.size)
    if right > left and bottom > top:
        ImageDraw.Draw(image).rectangle((left, top, right - 1, bottom - 1), fill=fill)


def source_bytes(case: BoundaryCase, directory: Path, size: tuple[int, int]) -> bytes:
    if case.source_kind == "real_photo":
        if not case.source_file or not case.source_sha256:
            raise ValueError("Real sources require a filename and digest")
        path = (directory / case.source_file).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError("Source must remain inside private input directory")
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != case.source_sha256:
            raise ValueError("Source digest mismatch")
        return raw
    image = Image.new("RGB", size, "white")
    for candidate in case.candidates:
        draw_region(image, candidate.box, "black")
    for box in case.protected_regions:
        draw_region(image, box, "red")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def evaluate_case(case: BoundaryCase, raw: bytes, output: Path, index: int) -> dict[str, object]:
    class FixedDetector:
        def detect(self, image_bytes: bytes) -> DetectionResult:
            return DetectionResult(case.scene, [BoundingBoxDetection(c.box, c.label, c.confidence)
                                                for c in case.candidates])

    detection = classify_scene(FixedDetector(), raw)
    before = detection.boxes[0].box
    effective = review_crop_boxes(detection)[0].box
    crops = []
    with Image.open(BytesIO(raw)) as source:
        mask = Image.new("L", source.size, 0)
        for box in case.protected_regions:
            draw_region(mask, box, 255)
        baseline = mask.crop(pixels(before, source.size)).histogram()[255]
        current = mask.crop(pixels(effective, source.size)).histogram()[255]
    for suffix, box in (("raw", before), ("effective", effective)):
        cropped = crop_item_and_generate_thumbnail(raw, box)
        file = f"case-{index:02}-{suffix}.png"
        (output / file).write_bytes(cropped.crop_bytes)
        crops.append(dict(file=file, sha256=cropped.crop_sha256,
                          size=[cropped.crop_width, cropped.crop_height]))
    increase = max(0, current - baseline)
    expanded = before != effective
    conforms = expanded == case.expect_expansion and (increase > 0) == case.expect_protected_increase
    return dict(id=case.id, source_kind=case.source_kind, evidence_kind=case.evidence_kind,
                source_sha256=sha256(raw).hexdigest(), input_kind_inferred=detection.input_kind_inferred,
                raw_box=before, effective_box=effective, baseline_protected_pixels=baseline,
                effective_protected_pixels=current, added_protected_pixels=increase,
                protected_region_guard_passed=increase == 0, policy_conforms_to_fixture=conforms,
                crops=crops)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/fixtures/crop_boundary_v1.json")
    parser.add_argument("--input-dir", type=Path, default=ROOT / "data/private-vision-review")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    dataset = BoundaryDataset.model_validate_json(args.manifest.read_text(encoding="utf-8"))
    if dataset.policy_version != AUTO_CROP_POLICY_VERSION:
        parser.error("Manifest policy version differs from implementation")
    output = args.input_dir / datetime.now(timezone.utc).strftime("boundaries-%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True)
    rows = [evaluate_case(case, source_bytes(case, args.input_dir, dataset.synthetic_size), output, index)
            for index, case in enumerate(dataset.cases, 1)]
    guards = [row for row in rows if row["evidence_kind"] == "guard"]
    positives = [row for row in rows if row["evidence_kind"] == "positive_control"]
    limitations = [row for row in rows if row["evidence_kind"] == "negative_control"]
    report = dict(dataset_version=dataset.dataset_version, policy_version=AUTO_CROP_POLICY_VERSION,
        execution_mode="offline_real_pixel_and_synthetic_marker_replay_not_ai",
        manifest_sha256=sha256(args.manifest.read_bytes()).hexdigest(),
        policy_conforming_cases=sum(bool(row["policy_conforms_to_fixture"]) for row in rows),
        total_cases=len(rows), guarded_cases=len(guards),
        guarded_cases_without_added_protected_pixels=sum(bool(row["protected_region_guard_passed"]) for row in guards),
        positive_controls=len(positives),
        positive_controls_conforming=sum(bool(row["policy_conforms_to_fixture"]) for row in positives),
        negative_controls_with_protected_leak=sum(not row["protected_region_guard_passed"] for row in limitations),
        cases=rows)
    serialized = json.dumps(report, indent=2) + "\n"
    (output / "report.json").write_text(serialized, encoding="utf-8")
    if args.report:
        args.report.write_text(serialized, encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "cases"}))
    print(f"Private crops: {output}")
    # Conformance is separate from the deliberately failing negative control.
    return 0 if all(row["policy_conforms_to_fixture"] for row in rows) and all(
        row["protected_region_guard_passed"] for row in guards) else 1


if __name__ == "__main__":
    raise SystemExit(main())
