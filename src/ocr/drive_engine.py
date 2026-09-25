import os
import sys
import json
import time
import re
import requests
from PIL import Image
import io

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ocr.parser import (
    parse_metadata,
    clean_title,
    clean_author_name,
    extract_surah,
    is_noise_line,
    INDONESIAN_MONTHS
)

def get_google_access_token() -> str:
    """
    Retrieves and auto-refreshes Google OAuth2 access token.
    Checks ~/.clasprc.json or environment variables.
    """
    # 1. Try ~/.clasprc.json
    clasprc_path = os.path.expanduser("~/.clasprc.json")
    if os.path.exists(clasprc_path):
        try:
            with open(clasprc_path, "r", encoding="utf-8") as f:
                clasp_data = json.load(f)
            t = clasp_data.get("tokens", {}).get("default", {})
            client_id = t.get("client_id") or os.environ.get("GOOGLE_CLIENT_ID")
            client_secret = t.get("client_secret") or os.environ.get("GOOGLE_CLIENT_SECRET")
            refresh_token = t.get("refresh_token") or os.environ.get("GOOGLE_REFRESH_TOKEN")

            if refresh_token and client_id and client_secret:
                refresh_res = requests.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token"
                    },
                    timeout=15
                )
                if refresh_res.status_code == 200:
                    token_data = refresh_res.json()
                    new_token = token_data.get("access_token")
                    if new_token:
                        return new_token
            # Fallback to existing access_token if refresh failed
            if t.get("access_token"):
                return t.get("access_token")
        except Exception as e:
            print(f"[WARN] Failed reading clasp token: {e}", file=sys.stderr)

    # 2. Try explicit environment variable
    env_token = os.environ.get("GOOGLE_ACCESS_TOKEN")
    if env_token:
        return env_token

    return None


def run_google_drive_ocr(image_path: str, access_token: str = None) -> str:
    """
    Uploads image to Google Drive as an OCR-converted Google Doc,
    exports the extracted plain text, and trashes the temporary doc.
    """
    token = access_token or get_google_access_token()
    if not token:
        raise ValueError("No valid Google OAuth access token found.")

    with Image.open(image_path) as img:
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        # Resize if huge to speed up Drive upload
        img.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88, optimize=True)
        img_bytes = buf.getvalue()

    headers = {"Authorization": f"Bearer {token}"}
    fname = os.path.basename(image_path)
    metadata = {
        "name": f"tmp_ocr_{fname}_{int(time.time() * 1000)}",
        "mimeType": "application/vnd.google-apps.document"
    }
    multipart_files = {
        "data": ("metadata", json.dumps(metadata), "application/json; charset=UTF-8"),
        "file": (fname, img_bytes, "image/jpeg")
    }

    # Upload & OCR
    upload_url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
    res = requests.post(upload_url, headers=headers, files=multipart_files, timeout=15)
    if res.status_code != 200:
        raise RuntimeError(f"Drive upload failed: {res.status_code} {res.text}")

    doc_id = res.json().get("id")
    if not doc_id:
        raise RuntimeError("No document ID returned from Google Drive upload.")

    try:
        # Export text
        export_url = f"https://www.googleapis.com/drive/v3/files/{doc_id}/export?mimeType=text/plain"
        exp_res = requests.get(export_url, headers=headers, timeout=10)
        if exp_res.status_code != 200:
            raise RuntimeError(f"Drive export failed: {exp_res.status_code} {exp_res.text}")
        extracted_text = exp_res.text
    finally:
        # Delete temporary doc to keep Drive clean
        try:
            requests.delete(f"https://www.googleapis.com/drive/v3/files/{doc_id}", headers=headers, timeout=10)
        except Exception:
            pass

    return extracted_text


def parse_drive_ocr_lines(raw_text: str) -> dict:
    """
    Parses metadata and 3 sidebar articles from Google Drive plain text OCR output.
    """
    all_lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    dict_lines = [{"text": l} for l in all_lines]

    # 1. Parse metadata (Edition, Date, Roman Year)
    edition, date_val, raw_bottom, year_roman = parse_metadata(dict_lines)

    # 2. Extract sidebar lines
    sidebar_lines = []
    in_sidebar = False
    stop_sidebar = False

    for l in all_lines:
        l_low = l.lower()

        # Start of sidebar
        if "artikel edisi ini" in l_low or l_low == "artikel":
            in_sidebar = True
            continue

        if not in_sidebar:
            # If we haven't seen 'artikel edisi ini' yet, check if line is title-like
            if any(k in l_low for k in ["memahami", "kritik", "belajar", "sunatullah", "hikmah", "akar kebahagiaan"]):
                in_sidebar = True

        if in_sidebar:
            # End of sidebar: footer line with actual month and year
            month_pat = '|'.join([m.lower() for m in INDONESIAN_MONTHS])
            if re.search(rf'\b(?:tahun\s+[ivx1|!]+|(?:edisi|ed)\s+\d+|(?:bulan\s+)?(?:{month_pat})\s+\d{{4}})\b', l_low):
                break
            # Body text indicator (e.g. paragraphs longer than 110 chars, or start of article body)
            if len(l) > 110 or l.startswith("A. ") or l.startswith("1. ") or "koleksi" in l_low or "latar belakang" in l_low:
                break
            if is_noise_line(l):
                continue
            if l_low in ["ulul albab", "ulul olbob", "cerdas dan mencerahkan"]:
                continue

            sidebar_lines.append(l)

    # Group sidebar lines into articles
    articles = []
    current_title_parts = []
    
    # Common author detection patterns
    def is_likely_author(line: str, prev_lines: list = None) -> bool:
        words = line.split()
        if not words:
            return False

        # If previous line ends with a connecting word/preposition, this line is title continuation
        if prev_lines:
            last_w = prev_lines[-1].split()[-1].lower().rstrip(':,;.?!"\'')
            if last_w in ["dalam", "dan", "tentang", "pada", "sebagai", "dari", "ke", "di", "atau", "menuju", "perspektif", "kajian"]:
                return False

        if "&" in line:
            return len(words) <= 9

        if len(words) > 5:
            return False

        if re.search(r'\b[A-Z]\.', line):  # e.g. D.L., P., S., R.
            return True
        known_authors = [
            "wahanani mawasti", "syahrul ramadhan", "salma nurfaidah",
            "angga nur r", "wahyu hidayah p", "handika", "handi ka",
            "jaya reza p", "roisul janah", "johar indra s", "erwin b. sanjaya",
            "e.s. hatta", "kusmina", "susanti", "m.a. risandy", "firdaus",
            "bagas arya d", "m. miftah farid", "ajeng d.l"
        ]
        if any(k in line.lower() for k in known_authors):
            return True
        if len(words) <= 3 and all(w[0].isupper() for w in words if w):
            # Exclude short title phrases that start with title words or conceptual terms
            if words[0].lower() in ["belajar", "memahami", "kritik", "akar", "sunatullah", "hikmah", "misteri", "nalar", "islam"]:
                return False
            return True
        return False

    i = 0
    while i < len(sidebar_lines):
        line = sidebar_lines[i]

        # Check if line ends with author name glued (e.g. "Hikmah Kurban dalam Masalah Stunting Syahrul Ramadhan")
        glued_match = re.search(r'^(.*?)\s+(Syahrul Ramadhan|Wahanani Mawasti|Salma Nurfaidah|Angga Nur R\.?|Wahyu Hidayah P\.?|Handika|Jaya Reza P\.?|Roisul Janah|Johar Indra S\.?|Erwin B\. Sanjaya|E\.S\. Hatta|Kusmina|Susanti|M\.A\. Risandy|Firdaus|Bagas Arya D\.?)$', line, re.I)
        if glued_match:
            t_part = glued_match.group(1).strip()
            a_part = glued_match.group(2).strip()
            t_full = " ".join(current_title_parts + [t_part]).strip()
            title, surah = extract_surah(t_full)
            articles.append({
                "title": title,
                "author": clean_author_name(a_part),
                "surah": surah
            })
            current_title_parts = []
            i += 1
            continue

        if is_likely_author(line, current_title_parts) and current_title_parts:
            author_line = line
            # Check if next line is joint author (e.g. & Ajeng D.L.)
            if i + 1 < len(sidebar_lines) and "&" in sidebar_lines[i+1]:
                author_line += " " + sidebar_lines[i+1]
                i += 1
            
            raw_title = " ".join(current_title_parts).strip()
            title, surah = extract_surah(raw_title)
            articles.append({
                "title": title,
                "author": clean_author_name(author_line),
                "surah": surah
            })
            current_title_parts = []
        else:
            current_title_parts.append(line)
        i += 1

    # Deduplicate articles and cap at 3
    unique_articles = []
    seen_titles = set()
    for art in articles:
        t_key = re.sub(r'\W+', '', art['title'].lower())
        if t_key and t_key not in seen_titles:
            seen_titles.add(t_key)
            unique_articles.append(art)
        if len(unique_articles) == 3:
            break

    return {
        "edition": edition or "-",
        "year_roman": year_roman or "-",
        "date": date_val or "-",
        "articles": unique_articles
    }


def extract_with_drive(image_path: str, api_key: str = None) -> dict:
    """
    Main entry point for Google Drive Native OCR.
    Executes cloud OCR via Drive API, then parses into standard WScaner schema.
    """
    if not os.path.exists(image_path):
        return {"status": "error", "message": f"Image file not found: {image_path}"}

    try:
        raw_text = run_google_drive_ocr(image_path)
        parsed = parse_drive_ocr_lines(raw_text)

        # Fallback to Gemini text refinement if articles < 3 and key exists
        gemini_key = api_key or os.environ.get("GEMINI_API_KEY")
        if (len(parsed.get("articles", [])) < 3 or not parsed.get("edition") or parsed.get("edition") == "-") and gemini_key:
            try:
                # Fast text-only structuring prompt (negligible token count, zero local RAM)
                prompt = (
                    "Ekstrak metadata cover buletin Ulul Albab dan 3 artikelnya dari teks OCR Google Drive berikut:\n"
                    f"```\n{raw_text}\n```\n"
                    "Kembalikan HANYA JSON:\n"
                    '{"edition": "...", "year_roman": "...", "date": "...", "articles": [{"title": "...", "author": "...", "surah": "-"}]}'
                )
                headers = {"Content-Type": "application/json"}
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1}
                }
                gem_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={gemini_key}"
                g_res = requests.post(gem_url, json=payload, headers=headers, timeout=12)
                if g_res.status_code == 200:
                    g_data = g_res.json()
                    txt = g_data["candidates"][0]["content"]["parts"][0]["text"]
                    g_parsed = json.loads(txt)
                    if len(g_parsed.get("articles", [])) >= 3:
                        parsed["edition"] = g_parsed.get("edition") or parsed["edition"]
                        parsed["year_roman"] = g_parsed.get("year_roman") or parsed["year_roman"]
                        parsed["date"] = g_parsed.get("date") or parsed["date"]
                        parsed["articles"] = g_parsed.get("articles")[:3]
            except Exception as e:
                print(f"[INFO] Gemini text structuring skipped/failed: {e}", file=sys.stderr)

        articles = [
            a for a in parsed.get("articles", [])
            if isinstance(a, dict) and len(str(a.get("title", "")).strip()) >= 5
        ]
        ed = str(parsed.get("edition", "-")).strip()
        if ed in ("-", "null", "none", "", "?"):
            ed = "-"

        if ed == "-" and len(articles) == 0:
            return {
                "status": "error",
                "message": "Bukan cover majalah Ulul Albab / metadata tidak ditemukan."
            }

        return {
            "status": "success",
            "ocr_engine": "Google Drive Built-in OCR",
            "edition": ed,
            "year_roman": parsed.get("year_roman", "-"),
            "date": parsed.get("date", "-"),
            "articles": articles
        }

    except Exception as e:
        return {"status": "error", "message": f"Google Drive OCR failed: {str(e)}"}


if __name__ == "__main__":
    test_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("Data", "drive_scans", "01_scan_05_1790135512.jpg")
    print(f"Testing Google Drive Native OCR on: {test_path}")
    res = extract_with_drive(test_path)
    print(json.dumps(res, indent=2))

