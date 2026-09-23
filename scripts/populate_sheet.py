import os
import sys
import json
import asyncio
import time

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "src"))
from ocr.ocr_processor import process_image
from ocr.gas_client import send_to_gas

MANIFEST_PATH = os.path.join(ROOT_DIR, "data", "scans", "manifest.json")
GAS_URL = "https://script.google.com/macros/s/AKfycbwlBr2M8ZshWucV5LPhi2cYlWV04w4uKFaQf9ApioIqsB3KVkn0eO9MWOPUtnG5K3mxUA/exec"

async def populate():
    if not os.path.exists(MANIFEST_PATH):
        print(f"Error: Manifest not found at {MANIFEST_PATH}")
        return

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    print(f"Starting to populate Google Sheets with {len(manifest)} verified scans...\n")
    print(f"Target GAS URL: {GAS_URL}\n")

    for item in manifest:
        idx = item['index']
        fname = item['localFile']
        fpath = item['localPath']
        drive_url = item['url']

        print(f"[{idx:02d}/{len(manifest):02d}] Processing {fname}...")
        
        # Run local tuned OCR
        res = await process_image(fpath, include_drive_image=False, send_gas=False)
        
        if res.get("status") != "success":
            print(f"    [ERROR] OCR failed for {fname}: {res.get('message')}")
            continue

        # Attach existing Drive file URL
        res["file_url"] = drive_url
        res["image_name"] = item["name"]

        # Send to Google Sheets
        gas_res = send_to_gas(GAS_URL, res)
        
        if gas_res.get("status") == "success":
            print(f"    [SUCCESS] Sent to Sheets! Edisi: {res.get('edition')} | Tahun: {res.get('year_roman')} | Bulan: {res.get('date')} | {len(res.get('articles', []))} artikel")
        else:
            print(f"    [WARN] GAS response: {gas_res}")

        # Polite throttle
        time.sleep(1.0)

    print("\nAll 13 documents processed and sent to Google Sheets!")

if __name__ == "__main__":
    asyncio.run(populate())
