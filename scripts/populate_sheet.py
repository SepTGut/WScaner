# Forwarder to scripts/data/populate_sheet.py
import os
import runpy

if __name__ == "__main__":
    target = os.path.join(os.path.dirname(__file__), "data", "populate_sheet.py")
    runpy.run_path(target, run_name="__main__")
