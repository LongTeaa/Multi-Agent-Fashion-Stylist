#!/usr/bin/env python3
"""Benchmark object detection latency and memory between YOLO-World ONNX (CPU) and Gemini API.

Usage:
    python scripts/benchmark_detection.py [--iterations N] [--model PATH]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

# Ensure backend root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = WORKSPACE_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings
from app.services.classifier import classify_scene
from app.services.yolo_world_detector import YoloWorldDetector


def run_benchmark(
    model_path: Path,
    iterations: int = 5,
    fixtures_dir: Path | None = None,
) -> None:
    if fixtures_dir is None:
        fixtures_dir = WORKSPACE_ROOT / "data" / "fixtures" / "vision_v1"

    test_samples = [
        ("v01.jpg", "Single Item (Flat-lay Shirt)"),
        ("v21.jpg", "Multi Item (Flat-lay Top + Pants)"),
        ("v24.jpg", "Worn Outfit (Person wearing Top + Pants)"),
    ]

    print("=" * 72)
    print("  MULTI-AGENT FASHION STYLIST - OBJECT DETECTION BENCHMARK")
    print("=" * 72)
    print(f"Hardware: CPU Execution Provider (ONNX Runtime)")
    print(f"Model Checkpoint: {model_path}")
    print(f"Test Iterations per image: {iterations}")
    print("-" * 72)

    if not model_path.is_file():
        print(f"Error: Model not found at '{model_path}'.", file=sys.stderr)
        print("Please run: python scripts/download_yolo_world_model.py", file=sys.stderr)
        sys.exit(1)

    # Initialize YOLO-World detector
    print("Loading YOLO-World ONNX session into memory...")
    t0 = time.perf_counter()
    detector = YoloWorldDetector(
        model_path=str(model_path),
        confidence_threshold=0.20,
        iou_threshold=0.45,
        padding=0.05,
    )
    load_time_ms = (time.perf_counter() - t0) * 1000
    print(f"Model loaded successfully in {load_time_ms:.1f}ms\n")

    # Benchmark YOLO-World
    results_table: list[dict[str, Any]] = []

    for filename, desc in test_samples:
        img_path = fixtures_dir / filename
        if not img_path.is_file():
            print(f"Warning: Fixture {filename} not found at {img_path}. Skipping.")
            continue

        image_bytes = img_path.read_bytes()

        # Warmup
        _ = detector.detect(image_bytes)

        # Timed runs
        latencies_ms: list[float] = []
        for _ in range(iterations):
            start = time.perf_counter()
            detection_res = detector.detect(image_bytes)
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies_ms.append(elapsed_ms)

        # Classify scene
        scene_res = classify_scene(detector=detector, image_bytes=image_bytes)

        avg_lat = sum(latencies_ms) / len(latencies_ms)
        min_lat = min(latencies_ms)
        max_lat = max(latencies_ms)

        results_table.append({
            "sample": filename,
            "description": desc,
            "avg_ms": avg_lat,
            "min_ms": min_lat,
            "max_ms": max_lat,
            "boxes_count": len(scene_res.boxes),
            "input_kind": scene_res.input_kind.value,
            "has_person": scene_res.person_box is not None,
        })

    # Print Report
    print(f"{'Image':<10} | {'Type / Description':<32} | {'Avg Latency':<12} | {'Min - Max':<14} | {'Scene Kind':<12}")
    print("-" * 90)
    for r in results_table:
        print(
            f"{r['sample']:<10} | {r['description']:<32} | {r['avg_ms']:>8.1f} ms | "
            f"{r['min_ms']:>5.1f} - {r['max_ms']:>5.1f} ms | {r['input_kind']:<12}"
        )

    print("-" * 90)
    overall_avg = sum(r["avg_ms"] for r in results_table) / len(results_table) if results_table else 0.0
    print(f"\n=> OVERALL AVERAGE CPU LATENCY: {overall_avg:.1f} ms per image")
    print(f"=> ESTIMATED THROUGHPUT: {1000.0 / overall_avg:.1f} images / second")
    print("=" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark detection speed")
    parser.add_argument(
        "--model",
        type=Path,
        default=BACKEND_ROOT / "models" / "yolov8s-worldv2.onnx",
        help="Path to YOLO-World ONNX model",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=5,
        help="Number of inference repetitions per image (default: 5)",
    )
    args = parser.parse_args()

    run_benchmark(model_path=args.model, iterations=args.iterations)


if __name__ == "__main__":
    main()
