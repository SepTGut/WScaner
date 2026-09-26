import sys
import os
import json
import asyncio
from datetime import datetime
from PIL import Image, ImageOps

# Ensure project root & src are in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

def _load_env():
    env_file = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_file):
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
        except Exception:
            try:
                with open(env_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'").strip('"')
                            if k and k not in os.environ:
                                os.environ[k] = v
            except Exception:
                pass

_load_env()


from src.ocr.engines import (
    extract_lines_with_boxes,
    get_ocr_engine_name,
    extract_with_gemini,
    extract_with_drive,
    extract_with_groq
)
from src.ocr.pipeline.parser import parse_metadata, parse_articles, INDONESIAN_MONTHS
from src.ocr.pipeline.gas_client import send_to_gas


import io
import base64

def prepare_drive_image_base64(img: Image.Image, max_dim: int = 1600, quality: int = 82) -> str:
    """
    Compresses and resizes the PIL image for Google Drive storage.
    Reduces typical 3-10MB phone camera images down to ~200-300KB while preserving excellent text readability.
    """
    try:
        drive_img = img.copy()
        if drive_img.mode in ('RGBA', 'P'):
            drive_img = drive_img.convert('RGB')
        drive_img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        drive_img.save(buf, format='JPEG', quality=quality, optimize=True)
        return base64.b64encode(buf.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"[WARN] Image compression for Drive failed: {e}", file=sys.stderr)
        return None


async def process_image(
    image_path: str,
    gas_url: str = None,
    include_drive_image: bool = True,
    send_gas: bool = True,
    engine: str = None
):
    if not os.path.exists(image_path):
        return {"status": "error", "message": f"File not found: {image_path}"}

    target_engine = (engine or os.environ.get("OCR_ENGINE", "windows")).lower().strip()

    img = Image.open(image_path)
    # Auto-orient based on smartphone EXIF metadata
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    # Auto-orient based on text direction (0°, 90°, 180°, 270°)
    effective_image_path = image_path
    oriented_temp_path = None
    try:
        from src.ocr.pipeline.orientation import auto_orient_pil
        img, angle_rotated = auto_orient_pil(img)
        if angle_rotated != 0:
            print(f"[INFO] Auto-orient: Gambar diputar {angle_rotated}° ke posisi tegak (upright).", file=sys.stderr)
            temp_dir = os.path.join(PROJECT_ROOT, "runtime", "temp")
            os.makedirs(temp_dir, exist_ok=True)
            oriented_temp_path = os.path.join(temp_dir, f"oriented_{int(datetime.now().timestamp() * 1000)}.jpg")
            img.save(oriented_temp_path, format="JPEG", quality=95)
            effective_image_path = oriented_temp_path
    except Exception as e:
        print(f"[WARN] Auto-orient dilewati: {e}", file=sys.stderr)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Generate high-speed compressed Base64 image for Google Drive
    image_b64 = None
    if include_drive_image:
        image_b64 = prepare_drive_image_base64(img)

    # -------------------------------------------------------------
    # OPTION 1: Groq Cloud Vision LLM (Ultra-Fast LPU Inference)
    # -------------------------------------------------------------
    if target_engine in ("groq", "qwen", "llama"):
        groq_res = extract_with_groq(effective_image_path)
        if groq_res.get("status") == "success":
            groq_res["timestamp"] = now_str
            groq_res["filename"] = os.path.basename(image_path)
            groq_res["image_base64"] = image_b64
            groq_res["image_mime"] = "image/jpeg"
            ed = groq_res.get("edition") or "edisi"
            groq_res["image_name"] = f"scan_{ed}_{int(datetime.now().timestamp())}.jpg"
            if send_gas and gas_url:
                groq_res["gas_response"] = send_to_gas(gas_url, groq_res)
            if oriented_temp_path and os.path.exists(oriented_temp_path):
                try: os.remove(oriented_temp_path)
                except Exception: pass
            return groq_res
        else:
            print(f"[WARN] Groq extraction failed: {groq_res.get('message')}. Falling back...", file=sys.stderr)

    # -------------------------------------------------------------
    # OPTION 2: Explicit Gemini Vision LLM
    # -------------------------------------------------------------
    if target_engine in ("gemini", "llm", "vlm"):
        gem_res = extract_with_gemini(effective_image_path)
        if gem_res.get("status") == "success":
            gem_res["timestamp"] = now_str
            gem_res["filename"] = os.path.basename(image_path)
            gem_res["image_base64"] = image_b64
            gem_res["image_mime"] = "image/jpeg"
            ed = gem_res.get("edition") or "edisi"
            gem_res["image_name"] = f"scan_{ed}_{int(datetime.now().timestamp())}.jpg"
            if send_gas and gas_url:
                gem_res["gas_response"] = send_to_gas(gas_url, gem_res)
            if oriented_temp_path and os.path.exists(oriented_temp_path):
                try: os.remove(oriented_temp_path)
                except Exception: pass
            return gem_res
        else:
            print(f"[WARN] Gemini extraction failed: {gem_res.get('message')}. Falling back to Windows OCR...", file=sys.stderr)

    # -------------------------------------------------------------
    # OPTION 2: Google Drive Native OCR (Built-in Google Docs OCR)
    # -------------------------------------------------------------
    if target_engine in ("drive", "googledrive", "gdrive"):
        drive_res = extract_with_drive(effective_image_path)
        if drive_res.get("status") == "success":
            drive_res["timestamp"] = now_str
            drive_res["filename"] = os.path.basename(image_path)
            drive_res["image_base64"] = image_b64
            drive_res["image_mime"] = "image/jpeg"
            ed = drive_res.get("edition") or "edisi"
            drive_res["image_name"] = f"scan_{ed}_{int(datetime.now().timestamp())}.jpg"
            if send_gas and gas_url:
                drive_res["gas_response"] = send_to_gas(gas_url, drive_res)
            if oriented_temp_path and os.path.exists(oriented_temp_path):
                try: os.remove(oriented_temp_path)
                except Exception: pass
            return drive_res
        else:
            print(f"[WARN] Google Drive OCR failed: {drive_res.get('message')}. Falling back to Windows OCR...", file=sys.stderr)


    # -------------------------------------------------------------
    # OPTION 3: Windows Native OCR (Standard Local Pipeline)
    # -------------------------------------------------------------
    W, H = img.size
    aspect = W / H

    # 1. First pass OCR on the full image
    full_lines = await extract_lines_with_boxes(img)
    edition, date_val, raw_bottom, year_roman = parse_metadata(full_lines)

    # Review Pass A (Targeted Footer Pass): If edition, date, or year roman missing, crop bottom footer with contrast enhancement
    if (not edition or not date_val or not year_roman) and 0.45 <= aspect <= 2.0:
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
            ed_retry, dt_retry, _, yr_retry = parse_metadata(footer_lines)
            if ed_retry and not edition:
                edition = ed_retry
            if dt_retry and not date_val:
                date_val = dt_retry
            if yr_retry and not year_roman:
                year_roman = yr_retry
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
            if ('edisi ini' in t_low or ('artikel' in t_low and l['y'] < 0.4 * H)) and l['x'] < 0.35 * W:
                start_y = max(start_y, l['y'] + l['h'])
            # Bottom boundary: footer metadata line (supporting camera typo variants)
            import re
            if re.search(r'\b(tahun|tohun|tabun|thun|edisi|edi5i)\b', t_low) and l['y'] > 0.65 * H:
                end_y = min(end_y, l['y'])

        # Extract sidebar lines within left column bounds (strictly excluding right-column body text)
        left_min_x = int(0.00 * W)
        left_max_x = int(0.28 * W)

        sidebar_lines = [
            l for l in full_lines
            if left_min_x <= l['x'] <= left_max_x
            and start_y <= l['y'] < end_y
        ]

        # Fallback: If coordinate filtering yielded fewer than 4 lines, run a dedicated crop OCR pass
        if len(sidebar_lines) < 4:
            try:
                sidebar_box = (int(0.00 * W), int(0.18 * H), int(0.28 * W), int(0.82 * H))
                sidebar_crop = img.crop(sidebar_box)
                if sidebar_crop.width < 700:
                    scale = 2.0
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
            sidebar_box = (int(0.00 * W), int(0.18 * H), int(0.29 * W), int(0.82 * H))
            sidebar_crop = img.crop(sidebar_box)
            if sidebar_crop.width < 700:
                scale = 2.0
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

    # -------------------------------------------------------------
    # OPTION 3: Auto / Hybrid Fallback to Gemini if Windows OCR Incomplete
    # -------------------------------------------------------------
    if target_engine in ("auto", "hybrid") and (not edition or not date_val or len(articles) < 3):
        # 1. Fallback to Groq Vision LLM (Ultra-Fast ~1.2s)
        try:
            print("[INFO] Auto-fallback: Windows OCR incomplete, querying Groq Vision LLM...", file=sys.stderr)
            groq_res = extract_with_groq(effective_image_path)
            if groq_res.get("status") == "success":
                groq_res["timestamp"] = now_str
                groq_res["filename"] = os.path.basename(image_path)
                groq_res["image_base64"] = image_b64
                groq_res["image_mime"] = "image/jpeg"
                ed = groq_res.get("edition") or "edisi"
                groq_res["image_name"] = f"scan_{ed}_{int(datetime.now().timestamp())}.jpg"
                if send_gas and gas_url:
                    groq_res["gas_response"] = send_to_gas(gas_url, groq_res)
                if oriented_temp_path and os.path.exists(oriented_temp_path):
                    try: os.remove(oriented_temp_path)
                    except Exception: pass
                return groq_res
        except Exception as e:
            print(f"[WARN] Auto Groq fallback error: {e}", file=sys.stderr)

        # 2. Fallback to Gemini if configured
        try:
            print("[INFO] Auto-fallback: Trying Gemini Vision LLM...", file=sys.stderr)
            gem_res = extract_with_gemini(effective_image_path)
            if gem_res.get("status") == "success":
                gem_res["timestamp"] = now_str
                gem_res["filename"] = os.path.basename(image_path)
                gem_res["image_base64"] = image_b64
                gem_res["image_mime"] = "image/jpeg"
                ed = gem_res.get("edition") or "edisi"
                gem_res["image_name"] = f"scan_{ed}_{int(datetime.now().timestamp())}.jpg"
                if send_gas and gas_url:
                    gem_res["gas_response"] = send_to_gas(gas_url, gem_res)
                if oriented_temp_path and os.path.exists(oriented_temp_path):
                    try: os.remove(oriented_temp_path)
                    except Exception: pass
                return gem_res
        except Exception as e:
            print(f"[WARN] Auto Gemini fallback error: {e}", file=sys.stderr)

        # 3. Fallback to Google Drive Native OCR
        try:
            print("[INFO] Auto-fallback: Trying Google Drive Native OCR...", file=sys.stderr)
            drive_res = extract_with_drive(effective_image_path)
            if drive_res.get("status") == "success":
                drive_res["timestamp"] = now_str
                drive_res["filename"] = os.path.basename(image_path)
                drive_res["image_base64"] = image_b64
                drive_res["image_mime"] = "image/jpeg"
                ed = drive_res.get("edition") or "edisi"
                drive_res["image_name"] = f"scan_{ed}_{int(datetime.now().timestamp())}.jpg"
                if send_gas and gas_url:
                    drive_res["gas_response"] = send_to_gas(gas_url, drive_res)
                if oriented_temp_path and os.path.exists(oriented_temp_path):
                    try: os.remove(oriented_temp_path)
                    except Exception: pass
                return drive_res
        except Exception as e:
            print(f"[WARN] Auto Drive fallback error: {e}", file=sys.stderr)

    if oriented_temp_path and os.path.exists(oriented_temp_path):
        try: os.remove(oriented_temp_path)
        except Exception: pass


    # Filter valid articles with non-empty titles
    articles = [
        a for a in articles
        if isinstance(a, dict) and len(str(a.get("title", "")).strip()) >= 5
    ]

    # If neither edition nor any articles were found, this is not a valid magazine cover
    if not edition and len(articles) == 0:
        return {
            "status": "error",
            "message": "Bukan cover majalah Ulul Albab / teks tidak terdeteksi.",
            "ocr_engine": get_ocr_engine_name(),
            "timestamp": now_str,
            "filename": os.path.basename(image_path)
        }

    result = {
        "status": "success",
        "ocr_engine": get_ocr_engine_name(),
        "timestamp": now_str,
        "date": date_val,
        "edition": edition,
        "year_roman": year_roman,
        "filename": os.path.basename(image_path),
        "articles": articles,
        "image_base64": image_b64,
        "image_mime": "image/jpeg",
        "image_name": f"scan_{edition or 'edisi'}_{int(datetime.now().timestamp())}.jpg"
    }

    # 4. Post to Google Sheet via GAS if requested and URL provided
    if send_gas and gas_url:
        result["gas_response"] = send_to_gas(gas_url, result)

    return result


def main():
    import argparse

    parser = argparse.ArgumentParser(description="WScaner OCR, Groq, Drive & Gemini Processor")
    parser.add_argument("image_path", nargs="?", help="Path ke file gambar pindaian")
    parser.add_argument("--engine", "-e", choices=["windows", "gemini", "groq", "drive", "auto", "ocr"], default=None,
                        help="Pilih mesin: 'windows' (Native OCR), 'groq' (Groq VLM), 'gemini' (Vision LLM), 'drive' (Google Drive OCR), atau 'auto'")
    parser.add_argument("--groq", action="store_true", help="Gunakan Groq Cloud Vision LLM")
    parser.add_argument("--gemini", action="store_true", help="Gunakan Google Gemini Vision LLM")
    parser.add_argument("--drive", action="store_true", help="Gunakan Google Drive Native OCR")
    parser.add_argument("--windows", "--ocr", action="store_true", help="Gunakan Windows Native OCR")
    parser.add_argument("--auto", action="store_true", help="Gunakan mode otomatis / hybrid")
    parser.add_argument("--gas-url", help="Webhook URL Google Apps Script")
    parser.add_argument("--no-gas", action="store_true", help="Jangan kirim ke GAS")
    parser.add_argument("--keep-b64", action="store_true", help="Sertakan base64 image pada output JSON")

    args = parser.parse_args()

    engine_choice = args.engine
    if args.groq:
        engine_choice = "groq"
    elif args.gemini:
        engine_choice = "gemini"
    elif args.drive:
        engine_choice = "drive"
    elif args.windows:
        engine_choice = "windows"
    elif args.auto:
        engine_choice = "auto"

    img_path = args.image_path
    if not img_path:
        print("=" * 60)
        print("          WScaner - Multi-Engine Document Scanner")
        print("=" * 60)
        print("Pilih Mesin Pemindaian:")
        print("  [1] Windows Native OCR (Lokal, Super Cepat, Offline, Gratis)")
        print("  [2] Groq Cloud Vision LLM (Ultra-Cepat ~1.2s, Cloud LPU AI)")
        print("  [3] Google Gemini Vision LLM (Cloud AI, Sangat Cerdas, Bebas Regex)")
        print("  [4] Google Drive Native OCR (Cloud Native OCR, Built-in Google Docs)")
        print("  [5] Auto / Hybrid (Windows OCR -> Fallback Cloud jika kurang lengkap)")
        sel = input("Pilihan Anda [1/2/3/4/5] (default: 1): ").strip()
        if sel == "2":
            engine_choice = "groq"
        elif sel == "3":
            engine_choice = "gemini"
        elif sel == "4":
            engine_choice = "drive"
        elif sel == "5":
            engine_choice = "auto"
        else:
            engine_choice = "windows"

        img_path = input("Masukkan path file gambar: ").strip().strip('"').strip("'")
        if not img_path or not os.path.exists(img_path):
            print(f"[ERROR] File tidak ditemukan: '{img_path}'")
            sys.exit(1)

    send_gas_flag = not args.no_gas
    gas_webhook = args.gas_url

    data = asyncio.run(process_image(
        img_path,
        gas_url=gas_webhook,
        include_drive_image=True,
        send_gas=send_gas_flag,
        engine=engine_choice
    ))

    if not args.keep_b64:
        data.pop("image_base64", None)

    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
