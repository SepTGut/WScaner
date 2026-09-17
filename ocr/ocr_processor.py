import sys
import os
import json
import asyncio
from datetime import datetime
from PIL import Image, ImageOps

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ocr.engine import extract_lines_with_boxes, get_ocr_engine_name
from ocr.parser import parse_metadata, parse_articles, INDONESIAN_MONTHS
from ocr.gas_client import send_to_gas


async def process_image(image_path: str, gas_url: str = None):
    if not os.path.exists(image_path):
        return {"status": "error", "message": f"File not found: {image_path}"}

    img = Image.open(image_path)
    # Auto-orient based on smartphone EXIF metadata
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    W, H = img.size
    aspect = W / H

    # 1. First pass OCR on the full image
    full_lines = await extract_lines_with_boxes(img)
    edition, date_val, raw_bottom = parse_metadata(full_lines)

    # Review Pass A (Targeted Footer Pass): If edition or date missing, crop bottom footer with contrast enhancement
    if (not edition or not date_val) and 0.45 <= aspect <= 2.0:
        try:
            footer_box = (0, int(0.68 * H), W, H)
            footer_crop = img.crop(footer_box)
            if footer_crop.height < 400:
                scale = 2.0
                footer_crop = footer_crop.resize(
                    (int(footer_crop.width * scale), int(footer_crop.height * scale)),
                    Image.Resampling.LANCZOS
                )
            footer_enhanced = ImageOps.autocontrast(footer_crop.convert('L'), cutoff=1)
            footer_lines = await extract_lines_with_boxes(footer_enhanced)
            ed_retry, dt_retry, _ = parse_metadata(footer_lines)
            if ed_retry and not edition:
                edition = ed_retry
            if dt_retry and not date_val:
                date_val = dt_retry
        except Exception as e:
            print(f"[WARN] Targeted footer OCR error: {e}", file=sys.stderr)

    # If date still not detected from cover, fallback to current month & year
    if not date_val:
        now = datetime.now()
        curr_month = INDONESIAN_MONTHS[now.month - 1].capitalize()
        date_val = f"{curr_month} {now.year}"

    # 2. Adaptive Sidebar Extraction
    sidebar_lines = []

    # Case A: Image is a horizontal strip / footer only (Aspect > 2.0)
    if aspect > 2.0:
        sidebar_lines = []

    # Case B: Image is already a cropped vertical strip / sidebar (Aspect < 0.45)
    elif aspect < 0.45:
        # All lines on the image belong to the sidebar directly
        sidebar_lines = full_lines

    # Case C: Standard full cover / page layout (0.45 <= Aspect <= 2.0)
    else:
        # Detect dynamic top anchor (where 'Artikel edisi ini' is located on the left)
        start_y = int(0.18 * H)
        end_y = int(0.82 * H)

        for l in full_lines:
            t_low = l['text'].lower()
            # Top boundary: immediately after header tags on left column
            if ('edisi ini' in t_low or ('artikel' in t_low and l['y'] < 0.4 * H)) and l['x'] < 0.38 * W:
                start_y = max(start_y, l['y'] + l['h'])
            # Bottom boundary: footer metadata line
            if ('tahun' in t_low or 'edisi' in t_low) and l['y'] > 0.65 * H:
                end_y = min(end_y, l['y'])

        # Extract sidebar lines within left column bounds (excluding paper edge border noise)
        left_min_x = int(0.04 * W)
        left_max_x = int(0.40 * W)

        sidebar_lines = [
            l for l in full_lines
            if left_min_x <= l['x'] <= left_max_x
            and start_y <= l['y'] < end_y
        ]

        # Fallback: If coordinate filtering yielded fewer than 4 lines, run a dedicated crop OCR pass
        if len(sidebar_lines) < 4:
            try:
                sidebar_box = (int(0.05 * W), int(0.18 * H), int(0.41 * W), int(0.80 * H))
                sidebar_crop = img.crop(sidebar_box)
                if sidebar_crop.width < 700:
                    scale = 1.5
                    sidebar_crop = sidebar_crop.resize(
                        (int(sidebar_crop.width * scale), int(sidebar_crop.height * scale)),
                        Image.Resampling.LANCZOS
                    )
                sidebar_enhanced = ImageOps.autocontrast(sidebar_crop.convert('L'), cutoff=1)
                sidebar_lines = await extract_lines_with_boxes(sidebar_enhanced)
            except Exception as e:
                print(f"[WARN] Fallback crop OCR error: {e}", file=sys.stderr)

    # 3. Parse 3 articles with title, author, and surah
    articles = parse_articles(sidebar_lines)

    # Review Pass B: If fewer than 3 articles detected on full cover, run targeted enhanced sidebar pass
    if len(articles) < 3 and 0.45 <= aspect <= 2.0:
        try:
            sidebar_box = (int(0.04 * W), int(0.18 * H), int(0.42 * W), int(0.82 * H))
            sidebar_crop = img.crop(sidebar_box)
            if sidebar_crop.width < 700:
                scale = 1.5
                sidebar_crop = sidebar_crop.resize(
                    (int(sidebar_crop.width * scale), int(sidebar_crop.height * scale)),
                    Image.Resampling.LANCZOS
                )
            sidebar_enhanced = ImageOps.autocontrast(sidebar_crop.convert('L'), cutoff=1)
            retry_lines = await extract_lines_with_boxes(sidebar_enhanced)
            retry_articles = parse_articles(retry_lines)
            if len(retry_articles) > len(articles):
                articles = retry_articles
        except Exception as e:
            print(f"[WARN] Review pass sidebar OCR error: {e}", file=sys.stderr)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # Encode image to Base64 for Google Drive storage
    import base64
    image_b64 = None
    try:
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        print(f"[WARN] Gagal membaca gambar untuk base64: {e}", file=sys.stderr)

    result = {
        "status": "success",
        "ocr_engine": get_ocr_engine_name(),
        "timestamp": now_str,
        "date": date_val,
        "edition": edition,
        "filename": os.path.basename(image_path),
        "articles": articles,
        "image_base64": image_b64,
        "image_mime": "image/jpeg",
        "image_name": f"scan_{edition or 'edisi'}_{int(datetime.now().timestamp())}.jpg"
    }

    # 4. Post to Google Sheet via GAS if URL provided
    if gas_url:
        result["gas_response"] = send_to_gas(gas_url, result)

    # Remove base64 data before stdout so JSON response is lightweight
    result.pop("image_base64", None)

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "Usage: python ocr/ocr_processor.py <image_path> [--gas-url <url>]"}))
        sys.exit(1)

    img_path = sys.argv[1]
    gas_webhook = None
    if "--gas-url" in sys.argv:
        idx = sys.argv.index("--gas-url")
        if idx + 1 < len(sys.argv):
            gas_webhook = sys.argv[idx + 1]

    data = asyncio.run(process_image(img_path, gas_webhook))
    print(json.dumps(data, indent=2))
