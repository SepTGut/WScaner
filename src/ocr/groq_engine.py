import os
import sys
import json
import base64
import requests
from PIL import Image
import io

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ocr.parser import clean_title, clean_author_name, normalize_roman

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

# Load Groq API credentials
GROQ_API_KEY = get_env_var("GROQ_API_KEY", "")
GROQ_MODEL = get_env_var("GROQ_MODEL", "qwen/qwen3.8-27b")


PROMPT_TEMPLATE = """
Analisis cover majalah/buletin 'Ulul Albab' ini.
Tugas Anda adalah mengekstrak metadata dan 3 artikel di kolom sidebar/daftar isi:
1. "edition": Nomor edisi (contoh: "05", "51", "10", "48")
2. "year_roman": Angka romawi tahun penerbitan (contoh: "XI", "XII"). Jika tidak tercetak jelas, simpulkan dari tahun penerbitan (contoh 2025 -> "XI").
3. "date": Bulan dan Tahun penerbitan (contoh: "Mei 2025", "April 2026", "Juli 2026")
4. "articles": Daftar 3 artikel yang masing-masing memiliki:
   - "title": Judul lengkap artikel (termasuk penanda Bagian 1 / Bagian 2 jika ada).
   - "author": Nama penulis lengkap (jika penulis ganda gabungkan dengan ' & ', misal "M. Miftah Farid & Ajeng D.L.").
   - "surah": Referensi surah/ayat jika disebutkan dalam judul (misal "Surah Al-Hasyr Ayat 9"), jika tidak ada isi "-".

Koreksi typo atau keanehan font kamera (misal "Tohun" -> "Tahun", "Edi5i" -> "Edisi", "Bagtan iJ" -> "(Bagian 1)").

Kembalikan HANYA format JSON valid tanpa tanda kutip markdown (```json ... ```), persis dengan struktur:
{
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

    # Compress and resize image to speed up upload
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

        # Parse JSON output
        parsed = json.loads(content)

        # Normalize articles structure if author was returned as list or string
        articles = parsed.get("articles", [])
        clean_articles = []
        for a in articles:
            author_val = a.get("author") or a.get("authors") or ""
            if isinstance(author_val, list):
                author_val = " & ".join(author_val)
            surah_val = a.get("surah")
            if not surah_val or surah_val == "null":
                surah_val = "-"
            clean_articles.append({
                "title": clean_title(str(a.get("title", "")).strip()),
                "author": clean_author_name(str(author_val).strip()),
                "surah": str(surah_val).strip()
            })

        cand_roman = str(parsed.get("year_roman") or parsed.get("roman_year") or "-").strip()
        if cand_roman and cand_roman != "-":
            cand_roman = normalize_roman(cand_roman)

        return {
            "status": "success",
            "ocr_engine": f"Groq Cloud VLM ({mod})",
            "edition": str(parsed.get("edition") or parsed.get("edition_number") or "-").strip(),
            "year_roman": cand_roman or "-",
            "date": str(parsed.get("date", "-")).strip(),
            "articles": clean_articles[:3]
        }

    except Exception as e:
        return {"status": "error", "message": f"Groq extraction failed: {str(e)}"}


if __name__ == "__main__":
    test_file = sys.argv[1] if len(sys.argv) > 1 else os.path.join("Data", "Example0.jpg.jpeg")
    print(f"Testing Groq Vision OCR on: {test_file}")
    res = extract_with_groq(test_file)
    print(json.dumps(res, indent=2))

