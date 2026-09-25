"""Backward-compatible proxy to src.ocr.engines.drive_engine."""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.ocr.engines.drive_engine import extract_with_drive, run_google_drive_ocr, parse_drive_ocr_lines

__all__ = ["extract_with_drive", "run_google_drive_ocr", "parse_drive_ocr_lines"]
