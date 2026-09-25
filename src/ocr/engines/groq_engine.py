import os
import sys
import json
import base64
import requests
from PIL import Image
import io

# Ensure project root & src are in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from ocr.parser import clean_title, clean_author_name, normalize_roman


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


GROQ_API_KEY = get_env_var("GROQ_API_KEY", "")
GROQ_MODEL = get_env_var("GROQ_MODEL", "qwen/qwen3.8-27b")

PROMPT_TEMPLATE = """
Periksa apakah gambar ini benar-benar cover majalah/buletin 'Ulul Albab'.

PENTING:
Jika gambar ini BUKAN cover majalah/buletin (misalnya foto wajah manusia, selfie, dinding, ruangan, atau objek lain):
Kembalikan HANYA:
{"is_magazine": false, "reason": "Bukan cover majalah Ulul Albab"}

HANYA jika gambar ini terbukti adalah cover majalah/buletin Ulul Albab, ekstrak:
1. "is_magazine": true
2. "edition": Nomor edisi (contoh: "05", "51", "10", "48")
3. "year_roman": Angka romawi tahun penerbitan (contoh: "XI", "XII")
4. "date": Bulan dan Tahun penerbitan (contoh: "Mei 2025", "April 2026")
5. "articles": Daftar 3 artikel nyata yang tertulis di cover majalah:
   - "title": Judul lengkap artikel (termasuk penanda Bagian 1 / Bagian 2 jika ada)
   - "author": Nama penulis lengkap (jika penulis ganda gabungkan dengan ' & ')
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


def extract_with_groq(image_path: str, api_key: str = None, model: str = None) -> dict:
    """
    Extracts magazine cover metadata and articles using Groq Cloud Vision LLM (e.g. Qwen 3.8 27B / Llama Vision).
    Runs with ultra-fast Groq LPU inference, consuming zero local RAM and zero local GPU.
    """
    key = api_key or os.environ.get("GROQ_API_KEY") or GROQ_API_KEY
    mod = model or os.environ.get("GROQ_MODEL") or GROQ_MODEL

    if not key:
        return {"status": "error", "message": "Groq API key not provided."}

    if not os.path.exists(image_path):
        return {"status": "error", "message": f"Image not found: {image_path}"}

    try:
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=82, optimize=True)
            img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        return {"status": "error", "message": f"Failed to prepare image: {e}"}

    endpoint = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": mod,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT_TEMPLATE},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                ]
            }
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }

    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=10)
        if resp.status_code != 200:
            return {"status": "error", "http_code": resp.status_code, "message": f"Groq API error: {resp.text}"}

        resp_data = resp.json()
        content = resp_data["choices"][0]["message"]["content"]
        parsed = json.loads(content)

        if parsed.get("is_magazine") is False:
            return {
                "status": "error",
                "message": parsed.get("reason") or "Gambar terdeteksi bukan cover majalah Ulul Albab."
            }

        articles = parsed.get("articles", [])
        clean_articles = []
        for a in articles:
            t_val = clean_title(str(a.get("title", "")).strip())
            t_low = t_val.lower()
            if len(t_val) < 5 or "tidak ditemukan" in t_low or "tidak ada" in t_low:
                continue
            author_val = a.get("author") or a.get("authors") or ""
            if isinstance(author_val, list):
                author_val = " & ".join(author_val)
            surah_val = a.get("surah")
            if not surah_val or surah_val == "null":
                surah_val = "-"
            clean_articles.append({
                "title": t_val,
                "author": clean_author_name(str(author_val).strip()),
                "surah": str(surah_val).strip()
            })

        edition_val = str(parsed.get("edition") or parsed.get("edition_number") or "-").strip()
        if edition_val in ("-", "null", "none", "", "?"):
            edition_val = "-"

        if edition_val == "-" and len(clean_articles) == 0:
            return {
                "status": "error",
                "message": "Bukan cover majalah Ulul Albab / metadata tidak ditemukan."
            }

        cand_roman = str(parsed.get("year_roman") or parsed.get("roman_year") or "-").strip()
        if cand_roman and cand_roman != "-":
            cand_roman = normalize_roman(cand_roman)

        return {
            "status": "success",
            "ocr_engine": f"Groq Cloud VLM ({mod})",
            "edition": edition_val,
            "year_roman": cand_roman or "-",
            "date": str(parsed.get("date", "-")).strip(),
            "articles": clean_articles[:3]
        }

    except Exception as e:
        return {"status": "error", "message": f"Groq extraction failed: {str(e)}"}
