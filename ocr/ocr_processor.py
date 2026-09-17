import sys
import os
import json
import asyncio
from datetime import datetime
from PIL import Image

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ocr.engine import extract_lines_with_boxes, get_ocr_engine_name
from ocr.parser import parse_metadata, parse_articles
from ocr.gas_client import send_to_gas


async def process_image(image_path: str, gas_url: str = None):
    if not os.path.exists(image_path):
        return {"status": "error", "message": f"File not found: {image_path}"}

    img = Image.open(image_path)
    W, H = img.size

    # 1. Full page OCR for bottom metadata
    full_lines = await extract_lines_with_boxes(img)
    edition, date_val, raw_bottom = parse_metadata(full_lines)

    # 2. Crop sidebar (relative position for magazine layout)
    sidebar_box = (int(0.06 * W), int(0.20 * H), int(0.39 * W), int(0.79 * H))
    sidebar_crop = img.crop(sidebar_box)
    sidebar_lines = await extract_lines_with_boxes(sidebar_crop)

    # 3. Parse 3 articles with title, author, and surah
    articles = parse_articles(sidebar_lines)

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
