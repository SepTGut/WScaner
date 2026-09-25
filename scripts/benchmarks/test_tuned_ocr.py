import os
import sys
import json
import asyncio

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT_DIR, "src"))
from ocr.ocr_processor import process_image

SCANS_DIR = os.path.join(ROOT_DIR, "data", "scans")

async def test_all():
    files = sorted([f for f in os.listdir(SCANS_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
    
    print(f"Testing Tuned OCR on {len(files)} files...\n")
    
    for idx, fname in enumerate(files):
        fpath = os.path.join(SCANS_DIR, fname)
        res = await process_image(fpath, include_drive_image=False, send_gas=False)
        
        ed = res.get('edition') or 'MISSING'
        yr = res.get('year_roman') or 'MISSING'
        dt = res.get('date') or 'MISSING'
        arts = res.get('articles') or []
        
        print(f"[{idx+1:02d}] {fname}")
        print(f"     EDISI: {ed} | TAHUN: {yr} | BULAN: {dt} | ARTIKEL ({len(arts)}):")
        for a_idx, a in enumerate(arts):
            print(f"       {a_idx+1}. {a['title']}")
            print(f"          Author: {a['author']}")
            if a.get('surah') and a['surah'] != '-':
                print(f"          Surah:  {a['surah']}")
        print()

if __name__ == "__main__":
    asyncio.run(test_all())
