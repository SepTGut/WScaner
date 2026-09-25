"""Backward-compatible proxy to src.ocr.engines.groq_engine."""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.ocr.engines.groq_engine import extract_with_groq

__all__ = ["extract_with_groq"]
