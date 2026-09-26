"""
OCR Processing and Parsing Pipeline.
Coordinates extraction, metadata normalization, article structuring, and Google Apps Script sync.
"""

from .parser import parse_metadata, parse_articles, clean_title, clean_author_name, normalize_roman, INDONESIAN_MONTHS
from .gas_client import send_to_gas
from .processor import process_image
from .orientation import detect_best_orientation_pil, auto_orient_pil, auto_orient_cv2

__all__ = [
    "parse_metadata",
    "parse_articles",
    "clean_title",
    "clean_author_name",
    "normalize_roman",
    "INDONESIAN_MONTHS",
    "send_to_gas",
    "process_image",
    "detect_best_orientation_pil",
    "auto_orient_pil",
    "auto_orient_cv2"
]

