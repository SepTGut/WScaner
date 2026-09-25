import os
import sys
import json
import base64
import urllib.request
import urllib.error
from PIL import Image
import io

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def get_env_var(key: str, default: str = "") -> str:
    val = os.environ.get(key)
    if val:
        return val
    env_file = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() == key:
                            return v.strip().strip("'").strip('"')
        except Exception:
            pass
    return default


GEMINI_API_KEY = get_env_var("GEMINI_API_KEY", "")
GEMINI_MODEL = get_env_var("GEMINI_MODEL", "gemini-3.5-flash-lite")

PROMPT_TEMPLATE = """
Periksa apakah gambar ini benar-benar cover majalah/buletin 'Ulul Albab'.

PENTING:
Jika gambar ini BUKAN cover majalah/buletin (misalnya foto wajah manusia, selfie, dinding, pemandangan, atau objek lain):
Kembalikan HANYA:
{"is_magazine": false, "reason": "Bukan cover majalah Ulul Albab"}

HANYA jika gambar ini terbukti adalah cover majalah/buletin Ulul Albab, ekstrak:
1. "is_magazine": true
2. "edition": Nomor edisi (contoh: "05", "51", "10")
3. "year_roman": Angka romawi tahun penerbitan (contoh: "XI", "XII")
4. "date": Bulan dan Tahun penerbitan (contoh: "Mei 2025", "April 2026")
5. "articles": Daftar 3 artikel nyata yang tertulis di cover majalah:
   - "title": Judul lengkap artikel (termasuk subtitle atau penanda Bagian jika ada)
   - "author": Nama penulis lengkap
   - "surah": Referensi surah jika ada, jika tidak ada isi "-"

Koreksi typo atau keanehan font kamera (misal "Tohun" -> "Tahun", "Edi5i" -> "Edisi", "Bagtan iJ" -> "(Bagian 1)").

Kembalikan HANYA format JSON valid tanpa tanda kutip markdown, persis dengan struktur:
{
  "is_magazine": true,
  "edition": "...",
  "year_roman": "...",
  "date": "...",
  "articles": [
    {"title": "...", "author": "...", "surah": "-"}
  ]
}
"""


def extract_with_gemini(image_path: str, api_key: str = None, model: str = None) -> dict:
    """
    Extracts magazine cover metadata and articles using Google Gemini Vision LLM.
    Runs in Google Cloud, consuming almost zero local RAM and zero local GPU.
    """
    key = api_key or GEMINI_API_KEY
    mod = model or GEMINI_MODEL

    if not os.path.exists(image_path):
        return {"status": "error", "message": f"Image not found: {image_path}"}

    try:
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85, optimize=True)
            img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        return {"status": "error", "message": f"Failed to read image: {e}"}

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": PROMPT_TEMPLATE},
                    {
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": img_b64
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1
        }
    }

    fallbacks = ["gemini-3.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]
    candidate_models = [mod] if mod else []
    for fb in fallbacks:
        if fb not in candidate_models:
            candidate_models.append(fb)
    last_error = None

    for m in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                out_text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(out_text)

                if parsed.get("is_magazine") is False:
                    return {
                        "status": "error",
                        "message": parsed.get("reason") or "Gambar terdeteksi bukan cover majalah Ulul Albab."
                    }

                articles = parsed.get("articles", [])
                clean_articles = []
                for a in articles:
                    if isinstance(a, dict):
                        t_val = str(a.get("title", "")).strip()
                        t_low = t_val.lower()
                        if len(t_val) >= 5 and "tidak ditemukan" not in t_low and "tidak ada" not in t_low:
                            clean_articles.append({
                                "title": t_val,
                                "author": str(a.get("author", "")).strip(),
                                "surah": str(a.get("surah", "-")).strip() or "-"
                            })

                ed_val = str(parsed.get("edition", "-")).strip()
                if ed_val in ("-", "null", "none", "", "?"):
                    ed_val = "-"

                if ed_val == "-" and len(clean_articles) == 0:
                    return {
                        "status": "error",
                        "message": "Bukan cover majalah Ulul Albab / metadata tidak ditemukan."
                    }

                return {
                    "status": "success",
                    "ocr_engine": f"Gemini Cloud VLM ({m})",
                    "edition": ed_val,
                    "year_roman": str(parsed.get("year_roman", "-")).strip(),
                    "date": str(parsed.get("date", "-")).strip(),
                    "articles": clean_articles[:3]
                }
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8")
            last_error = f"HTTP {e.code} ({m}): {err_msg}"
            if e.code in (503, 404, 429):
                continue
            return {"status": "error", "http_code": e.code, "message": last_error}
        except Exception as e:
            last_error = str(e)
            continue

    return {"status": "error", "message": last_error or "All candidate Gemini models failed"}
