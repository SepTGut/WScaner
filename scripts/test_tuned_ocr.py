# Forwarder to scripts/benchmarks/test_tuned_ocr.py
import os
import runpy

if __name__ == "__main__":
    target = os.path.join(os.path.dirname(__file__), "benchmarks", "test_tuned_ocr.py")
    runpy.run_path(target, run_name="__main__")
