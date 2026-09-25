"""Backward-compatible proxy to src.ocr.pipeline.processor."""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from src.ocr.pipeline.processor import (
    process_image,
    prepare_drive_image_base64,
    main
)

__all__ = ["process_image", "prepare_drive_image_base64", "main"]

if __name__ == "__main__":
    main()
