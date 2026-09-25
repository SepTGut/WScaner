"""Backward-compatible proxy to src.ocr.engines.windows_engine."""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.ocr.engines.windows_engine import extract_lines_with_boxes, get_ocr_engine_name, HAS_WINOCR

__all__ = ["extract_lines_with_boxes", "get_ocr_engine_name", "HAS_WINOCR"]
