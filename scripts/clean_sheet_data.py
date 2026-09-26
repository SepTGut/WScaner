import os
import sys
import re
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Import cleaning functions from existing pipeline
from src.ocr.pipeline.parser import clean_title, clean_author_name, extract_surah, normalize_roman

def normalize_date_str(date_val: str) -> str:
    """Normalizes ISO or text dates to 'Month YYYY' in Indonesian."""
    if not date_val or date_val.strip() in ["-", ""]:
        return "-"
    v = date_val.strip()
    
    # Check if format like '2026-04-01 00:00' or '2026-04-01'
    m_iso = re.match(r'^(\d{4})-(\d{2})-(\d{2})', v)
    if m_iso:
        year = m_iso.group(1)
        month_num = int(m_iso.group(2))
        month_names = [
            "Januari", "Februari", "Maret", "April", "Mei", "Juni",
            "Juli", "Agustus", "September", "Oktober", "November", "Desember"
        ]
        if 1 <= month_num <= 12:
            return f"{month_names[month_num - 1]} {year}"
    
    # Already Indonesian month, e.g. 'April 2026', 'Mei 2025'
    m_txt = re.match(r'^([A-Za-z]+)\s*(\d{4})$', v)
    if m_txt:
        month = m_txt.group(1).capitalize()
        year = m_txt.group(2)
        # normalize month spelling if needed
        eng_to_id = {
            "May": "Mei", "March": "Maret", "June": "Juni", "July": "Juli",
            "August": "Agustus", "October": "Oktober", "December": "Desember"
        }
        month = eng_to_id.get(month, month)
        return f"{month} {year}"
        
    return v

def clean_row_data(row_idx, original_cells):
    """
    Cleans a single row while strictly preserving row identity and link formulas.
    original_cells format: [No, TimeStamp, Date, Tahun, Edition, Article, Author, Surah, LinkFoto]
    """
    # 1. No (Sequential 1-based index)
    no = str(row_idx)
    
    # 2. TimeStamp
    ts = original_cells[1]["value"].strip()
    # Normalize timestamp format (YYYY-MM-DD HH:MM)
    m_ts = re.match(r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', ts)
    if m_ts:
        ts = m_ts.group(1)
        
    # 3. Date
    raw_date = original_cells[2]["value"]
    date_val = normalize_date_str(raw_date)
    
    # 4. Tahun (Roman Numeral)
    raw_th = original_cells[3]["value"].strip()
    raw_ed = original_cells[4]["value"].strip()
    
    # Infer or normalize Roman numeral
    if raw_th in ["-", ""] or not raw_th:
        if raw_ed in ["48", "49", "50", "51", "1", "2", "3", "4", "5"]:
            th_val = "XI"
        elif raw_ed == "10":
            th_val = "XII"
        else:
            th_val = "-"
    else:
        th_val = normalize_roman(raw_th)
        
    # 5. Edition
    ed_val = raw_ed
    
    # 6. Article (Title) & 8. Surah
    raw_art = original_cells[5]["value"].strip()
    raw_surah = original_cells[7]["value"].strip()
    
    # Specific known OCR fixes
    art_val = raw_art
    art_val = art_val.replace('•.', ':').replace('•', ':')
    art_val = re.sub(r'\bQur[\'’`\s]+an\b', "Qur'an", art_val, flags=re.I)
    art_val = re.sub(r'\bdalam\s+islam\b', "dalam Islam", art_val, flags=re.I)
    art_val = re.sub(r'\bNalar\s+slam\b', "Nalar Islam", art_val, flags=re.I)
    art_val = re.sub(r'\bMemaknai\s+Aakikat\b', "Memaknai Hakikat", art_val, flags=re.I)
    art_val = re.sub(r'\bHadis\.\s+Rida\b', "Hadis: Rida", art_val, flags=re.I)
    art_val = re.sub(r'^[iI]nvestasi\s+Akhirat,', "Investasi Akhirat:", art_val, flags=re.I)
    art_val = re.sub(r'\bVeganisme\s+v\s+Gizi\s+Seimba\s+Menemuka\b', "Veganisme vs Gizi Seimbang: Menemukan", art_val, flags=re.I)
    art_val = re.sub(r'\bPrediksi\s+Kiamat,\s+Sains\b', "Prediksi Kiamat: Sains", art_val, flags=re.I)
    
    # Extract Surah if embedded in title
    cleaned_art, extracted_s = extract_surah(art_val)
    surah_val = raw_surah if raw_surah not in ["-", ""] else extracted_s
    
    # Further standard cleaning
    cleaned_art = clean_title(cleaned_art)
    
    # Ensure title starts with uppercase if alphabetic
    if cleaned_art and cleaned_art[0].islower():
        cleaned_art = cleaned_art[0].upper() + cleaned_art[1:]
        
    # 7. Author
    raw_auth = original_cells[6]["value"].strip()
    if re.match(r'^Penulis\s*\d+$', raw_auth, re.I):
        cleaned_auth = raw_auth
    else:
        cleaned_auth = clean_author_name(raw_auth)
    if not cleaned_auth:
        cleaned_auth = "-"
        
    # 9. Link Foto (Preserve exact formula or value)
    raw_link_f = original_cells[8]["formula"].strip()
    raw_link_v = original_cells[8]["value"].strip()
    link_final = raw_link_f if raw_link_f else (raw_link_v if raw_link_v else "-")
    
    return [
        no,
        ts,
        date_val,
        th_val,
        ed_val,
        cleaned_art,
        cleaned_auth,
        surah_val,
        link_final
    ]

def fetch_sheet_data():
    gas_url = os.getenv("GAS_WEBHOOK_URL")
    gas_token = os.getenv("GAS_SECRET_TOKEN")
    for attempt in range(5):
        try:
            res = requests.post(gas_url, json={"action": "get_sheet_data", "secret": gas_token}, timeout=45)
            if res.status_code == 200:
                data = res.json()
                if data.get("status") == "success":
                    return data
        except Exception as e:
            print(f"Fetch attempt {attempt+1} failed: {e}")
            time.sleep(2)
    raise RuntimeError("Failed to fetch sheet data after 5 retries.")

def update_sheet_data(rows):
    gas_url = os.getenv("GAS_WEBHOOK_URL")
    gas_token = os.getenv("GAS_SECRET_TOKEN")
    payload = {
        "action": "update_sheet_clean",
        "secret": gas_token,
        "start_row": 5,
        "rows": rows
    }
    for attempt in range(5):
        try:
            res = requests.post(gas_url, json=payload, timeout=60)
            if res.status_code == 200:
                return res.json()
        except Exception as e:
            print(f"Update attempt {attempt+1} failed: {e}")
            time.sleep(3)
    raise RuntimeError("Failed to update sheet data after 5 retries.")

def is_dummy_scan_row(cells):
    art = cells[5]["value"].strip().lower()
    auth = cells[6]["value"].strip().lower()
    if "tidak terbaca" in art:
        return True
    if art in ["artikel 1", "artikel 2", "artikel 3"] and any(p in auth for p in ["penulis 1", "penulis 2", "penulis 3", "1", "2", "3", "-"]):
        return True
    return False

def main():
    dry_run = "--apply" not in sys.argv
    print(f"--- Google Sheet Data Cleaning --- [Mode: {'DRY RUN' if dry_run else 'LIVE APPLY'}]")
    
    data = fetch_sheet_data()
    raw_rows = data.get("rows", [])
    total_raw = len(raw_rows)
    print(f"Fetched {total_raw} rows from Google Sheet.")
    
    kept_raw_rows = []
    removed_count = 0
    
    for r in raw_rows:
        cells = r["cells"]
        if is_dummy_scan_row(cells):
            removed_count += 1
            print(f"[REMOVING DUMMY ROW]: No={cells[0]['value']} | Ed={cells[4]['value']} | Date={cells[2]['value']} | Art='{cells[5]['value']}' | Auth='{cells[6]['value']}'")
        else:
            kept_raw_rows.append(r)
            
    if removed_count > 0:
        print(f"\nTotal dummy rows removed: {removed_count}")
    print(f"Total rows to preserve & clean: {len(kept_raw_rows)}")
    
    cleaned_rows = []
    diff_count = 0
    
    for idx, r in enumerate(kept_raw_rows, start=1):
        cells = r["cells"]
        new_row = clean_row_data(idx, cells)
        cleaned_rows.append(new_row)
        
        # Compare with old values
        old_vals = [cells[i]["value"] for i in range(9)]
        # For link formula comparison
        old_link = cells[8]["formula"] if cells[8]["formula"] else cells[8]["value"]
        old_vals[8] = old_link
        
        diffs = []
        col_names = ["No", "TimeStamp", "Date", "Tahun", "Edition", "Article", "Author", "Surah", "Link"]
        for c_idx in range(9):
            if str(old_vals[c_idx]).strip() != str(new_row[c_idx]).strip():
                diffs.append(f"{col_names[c_idx]}: '{old_vals[c_idx]}' -> '{new_row[c_idx]}'")
                
        if diffs:
            diff_count += 1
            print(f"\n[Row {idx:02d} (Old No {cells[0]['value']}) Changes]:")
            for d in diffs:
                print(f"   • {d}")
        else:
            print(f"[Row {idx:02d}] Unchanged: {new_row[5][:40]}...")

    print(f"\nTotal rows evaluated: {len(cleaned_rows)}")
    print(f"Rows modified: {diff_count}")
    print(f"Dummy rows filtered: {removed_count}")
    
    if dry_run:
        print("\n[DRY RUN COMPLETE] To write these changes back to Google Sheets, run with --apply")
    else:
        print("\nSending cleaned data to Google Apps Script...")
        res = update_sheet_data(cleaned_rows)
        print("Update response:", json.dumps(res, indent=2))
        print("Successfully updated Google Sheet in-place!")

if __name__ == "__main__":
    main()

