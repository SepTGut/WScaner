import os
import sys
import json
import base64
import urllib.request
import urllib.error
from PIL import Image
import io

def get_env_var(key: str, default: str = "") -> str:
    val = os.environ.get(key)
    if val:
        return val
    env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
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
GEMINI_MODEL = get_env_var("GEMINI_MODEL", "gemini-flash-latest")

PROMPT_TEMPLATE = """
Analisis cover majalah/buletin 'Ulul Albab' ini.
Tugas Anda adalah mengekstrak metadata dan 3 artikel di kolom sidebar/daftar isi:
1. "edition": Nomor edisi (contoh: "05", "51", "10")
2. "year_roman": Angka romawi tahun penerbitan (contoh: "XI", "XII"). Jika tidak tercetak jelas di cover, simpulkan berdasarkan tahun penerbitan (contoh 2025 -> "XI").
3. "date": Bulan dan Tahun penerbitan (contoh: "Mei 2025", "April 2026", "Juli 2026")
4. "articles": Daftar 3 artikel yang masing-masing memiliki:
   - "title": Judul lengkap artikel (termasuk subtitle atau penanda Bagian 1 / Bagian 2 jika ada).
   - "author": Nama penulis lengkap (jika ada penulis ganda dengan '&', sertakan keduanya).
   - "surah": Referensi surah/ayat jika disebutkan dalam judul (misal "Surah Al-Hasyr Ayat 9"), jika tidak ada isi "-".

Koreksi typo atau keanehan font kamera (misal "Tohun" -> "Tahun", "Edi5i" -> "Edisi", "Bagtan iJ" -> "(Bagian 1)").

Kembalikan HANYA format JSON valid tanpa tanda kutip markdown, persis dengan struktur:
{
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
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{mod}:generateContent?key={key}"

    if not os.path.exists(image_path):
        return {"status": "error", "message": f"Image not found: {image_path}"}

    # Compress slightly if very large to minimize network upload latency
    try:
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            # Resize if max dimension > 1600
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

    candidate_models = [mod] if mod else ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-flash-latest"]
    last_error = None

    for m in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                out_text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(out_text)
                
                # Format according to WScaner standard output schema
                return {
                    "status": "success",
                    "ocr_engine": f"Gemini Cloud VLM ({m})",
                    "edition": str(parsed.get("edition", "-")).strip(),
                    "year_roman": str(parsed.get("year_roman", "-")).strip(),
                    "date": str(parsed.get("date", "-")).strip(),
                    "articles": parsed.get("articles", [])
                }
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8")
            last_error = f"HTTP {e.code} ({m}): {err_msg}"
            # If 503 (high demand) or 404, try next candidate model
            if e.code in (503, 404, 429):
                continue
            return {"status": "error", "http_code": e.code, "message": last_error}
        except Exception as e:
            last_error = str(e)
            continue

    return {"status": "error", "message": last_error or "All candidate Gemini models failed"}

if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
    else:
        test_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "scans", "01_scan_05_1790135512.jpg")
    
    print(f"Testing Gemini OCR on: {test_file}")
    res = extract_with_gemini(test_file)
    print(json.dumps(res, indent=2, ensure_ascii=False))
