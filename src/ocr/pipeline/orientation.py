"""
Orientation detection and deskew/rotation normalization for document scans.
Detects whether an image is oriented normally (0°), upside-down (180°), or sideways (90°/270°),
and automatically rotates it to upright portrait orientation.
"""

import sys
import re
import cv2
import numpy as np
from PIL import Image

# Check for Windows Native OCR availability
HAS_WINOCR = False
try:
    import winocr
    import asyncio
    HAS_WINOCR = True
except Exception:
    HAS_WINOCR = False

try:
    import pytesseract
except ImportError:
    pytesseract = None

# Indonesian & magazine-specific domain keywords for orientation scoring
KEYWORDS = [
    r'artikel', r'edisi', r'tahun', r'nomor', r'no\.', r'menara', r'pengawal',
    r'sedarlah', r'januari', r'februari', r'maret', r'april', r'mei', r'juni',
    r'juli', r'agustus', r'september', r'oktober', r'november', r'desember',
    r'warta', r'bulan', r'indonesia', r'surah', r'halaman', r'daftar', r'judul'
]


async def _score_angle_winocr(thumb: Image.Image, angle: int) -> int:
    """Scores a rotated PIL thumbnail using Windows Native OCR."""
    if not HAS_WINOCR:
        return 0
    try:
        t = thumb.rotate(angle, expand=True) if angle != 0 else thumb
        res = await winocr.recognize_pil(t, lang='en-US')
        lines = [l.text for l in res.lines]
        text = ' '.join(lines).lower()
        kw_matches = sum(1 for kw in KEYWORDS if re.search(r'\b' + kw, text))
        line_count = len(lines)
        word_count = sum(len(l.split()) for l in lines)
        return (kw_matches * 100) + (word_count * 2) + line_count
    except Exception:
        return 0


def _score_angle_tesseract(thumb: Image.Image, angle: int) -> int:
    """Scores a rotated PIL thumbnail using Tesseract OCR fallback."""
    if not pytesseract:
        return 0
    try:
        t = thumb.rotate(angle, expand=True) if angle != 0 else thumb
        data = pytesseract.image_to_data(t, lang='ind+eng', output_type=pytesseract.Output.DICT)
        words = [w.strip().lower() for w in data.get('text', []) if w.strip()]
        text = ' '.join(words)
        kw_matches = sum(1 for kw in KEYWORDS if re.search(r'\b' + kw, text))
        word_count = len(words)
        return (kw_matches * 100) + (word_count * 2)
    except Exception:
        return 0


def detect_best_orientation_pil(img: Image.Image) -> int:
    """
    Detects the best rotation angle (in degrees counter-clockwise for PIL rotate)
    to make the document upright.
    Returns: 0, 90, 180, or 270.
    """
    w, h = img.size

    # Create a small thumbnail for ultra-fast OCR scoring (<40ms)
    thumb = img.copy()
    thumb.thumbnail((450, 450), Image.Resampling.LANCZOS)

    # Order of evaluation:
    # If landscape (w > h), test 90 and 270 first, then 0 and 180.
    # If portrait (h >= w), test 0 and 180 first, then 90 and 270.
    if w > h:
        angles_to_check = [270, 90, 0, 180]
    else:
        angles_to_check = [0, 180, 270, 90]

    best_angle = angles_to_check[0]
    best_score = -1

    if HAS_WINOCR:
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            async def _eval():
                b_ang = angles_to_check[0]
                b_sc = -1
                for ang in angles_to_check:
                    sc = await _score_angle_winocr(thumb, ang)
                    if sc > b_sc:
                        b_sc = sc
                        b_ang = ang
                return b_ang, b_sc

            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    best_angle, best_score = pool.submit(lambda: asyncio.run(_eval())).result()
            else:
                best_angle, best_score = asyncio.run(_eval())

        except Exception as e:
            print(f"[WARN] Orientation detection via winocr failed: {e}", file=sys.stderr)
            best_score = -1

    elif pytesseract:
        for ang in angles_to_check:
            sc = _score_angle_tesseract(thumb, ang)
            if sc > best_score:
                best_score = sc
                best_angle = ang

    # If OCR score was inconclusive (e.g. blank page or failed OCR):
    # If wider than tall (landscape), rotate 90° CW (270° CCW in PIL) to make it portrait.
    if best_score <= 5 and (w > h * 1.05):
        return 270

    return best_angle


def auto_orient_pil(img: Image.Image) -> tuple[Image.Image, int]:
    """
    Detects orientation and returns (oriented_pil_image, angle_applied).
    """
    angle = detect_best_orientation_pil(img)
    if angle == 0:
        return img, 0
    oriented = img.rotate(angle, expand=True)
    return oriented, angle


def auto_orient_cv2(image_bgr: np.ndarray) -> tuple[np.ndarray, int]:
    """
    Detects orientation and rotates an OpenCV BGR numpy array to upright portrait.
    Returns: (oriented_cv2_image, angle_applied_degrees).
    """
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)
    angle = detect_best_orientation_pil(pil_img)

    if angle == 0:
        return image_bgr, 0
    elif angle == 90:
        return cv2.rotate(image_bgr, cv2.ROTATE_90_COUNTERCLOCKWISE), 90
    elif angle == 180:
        return cv2.rotate(image_bgr, cv2.ROTATE_180), 180
    elif angle == 270:
        return cv2.rotate(image_bgr, cv2.ROTATE_90_CLOCKWISE), 270
    return image_bgr, 0
