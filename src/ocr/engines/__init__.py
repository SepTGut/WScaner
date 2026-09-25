"""
OCR Engines Package.
Multi-engine adapters supporting Windows Native OCR, Groq Vision, Gemini Vision, and Google Drive OCR.
"""

from .windows_engine import extract_lines_with_boxes, get_ocr_engine_name
from .groq_engine import extract_with_groq
from .gemini_engine import extract_with_gemini
from .drive_engine import extract_with_drive

__all__ = [
    "extract_lines_with_boxes",
    "get_ocr_engine_name",
    "extract_with_groq",
    "extract_with_gemini",
    "extract_with_drive"
]
