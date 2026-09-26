import os
import sys
import time
import requests
from dotenv import load_dotenv

load_dotenv()

gas_url = os.getenv("GAS_WEBHOOK_URL")
gas_token = os.getenv("GAS_SECRET_TOKEN")

for attempt in range(5):
    try:
        res = requests.post(gas_url, json={"action": "get_sheet_data", "secret": gas_token}, timeout=45)
        if res.status_code == 200:
            data = res.json()
            break
    except Exception as e:
        print(f"Attempt {attempt+1} failed: {e}")
        time.sleep(2)
else:
    print("Failed to fetch sheet data after retries")
    sys.exit(1)

print(f"Total rows fetched: {data.get('total_rows')}")
rows = data.get("rows", [])

with open("scratch/sheet_raw_dump.txt", "w", encoding="utf-8") as out:
    for idx, r in enumerate(rows, start=1):
        c = r["cells"]
        no = c[0]["value"]
        ts = c[1]["value"]
        date_val = c[2]["value"]
        th = c[3]["value"]
        ed = c[4]["value"]
        art = c[5]["value"]
        auth = c[6]["value"]
        surah = c[7]["value"]
        link_f = c[8]["formula"]
        link_v = c[8]["value"]
        line = f"[{idx:02d}] Row {r['row_index']}: No={no} | Ed={ed} | Th={th} | Date={date_val} | Surah={surah} | Art='{art}' | Auth='{auth}' | Link='{link_f or link_v}'"
        print(line)
        out.write(line + "\n")

print(f"\nDumped {len(rows)} rows to scratch/sheet_raw_dump.txt")
