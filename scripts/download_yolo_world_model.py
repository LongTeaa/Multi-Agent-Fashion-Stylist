#!/usr/bin/env python3
"""Download pretrained YOLO-World ONNX checkpoint for Multi-Agent Fashion Stylist.

Usage:
    python scripts/download_yolo_world_model.py [--force] [--output PATH]
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

MODEL_URL = "https://huggingface.co/Instemic/yolo-world-onnx/resolve/main/yolov8s-worldv2.onnx"
DEFAULT_TARGET = Path(__file__).resolve().parents[1] / "backend" / "models" / "yolov8s-worldv2.onnx"
EXPECTED_MIN_SIZE = 45 * 1024 * 1024  # At least 45MB


def download_progress(count: int, block_size: int, total_size: int) -> None:
    percent = int(count * block_size * 100 / total_size) if total_size > 0 else 0
    downloaded_mb = (count * block_size) / (1024 * 1024)
    total_mb = total_size / (1024 * 1024) if total_size > 0 else 0
    sys.stdout.write(f"\rDownloading YOLO-World ONNX: {percent}% [{downloaded_mb:.1f}MB / {total_mb:.1f}MB]")
    sys.stdout.flush()


def download_model(output_path: Path, force: bool = False) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and not force:
        file_size = output_path.stat().st_size
        if file_size >= EXPECTED_MIN_SIZE:
            print(f"Model already exists at: {output_path} ({file_size / (1024 * 1024):.1f}MB)")
            print("To re-download, pass --force")
            return
        else:
            print(f"Existing file is incomplete ({file_size} bytes). Re-downloading...")

    print(f"Downloading YOLO-World v2 Small ONNX model from:\n  {MODEL_URL}\nTo:\n  {output_path}")

    try:
        urllib.request.urlretrieve(MODEL_URL, output_path, reporthook=download_progress)
        print("\nDownload completed successfully!")
    except Exception as exc:
        print(f"\nDownload failed: {exc}", file=sys.stderr)
        if output_path.exists():
            output_path.unlink()
        sys.exit(1)

    file_size = output_path.stat().st_size
    print(f"Verified model file size: {file_size / (1024 * 1024):.2f}MB")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download YOLO-World ONNX model checkpoint")
    parser.add_argument("--force", action="store_true", help="Force re-download if file already exists")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_TARGET,
        help=f"Target path for the model (default: {DEFAULT_TARGET})",
    )
    args = parser.parse_args()

    download_model(args.output, force=args.force)


if __name__ == "__main__":
    main()
