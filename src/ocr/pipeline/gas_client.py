import os
import requests
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def get_secret_token() -> str:
    token = os.environ.get("GAS_SECRET_TOKEN")
    if token:
        return token
    env_file = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() == "GAS_SECRET_TOKEN":
                            return v.strip().strip("'").strip('"')
        except Exception:
            pass
    return ""

def send_to_gas(gas_url: str = None, payload: dict = None, max_retries: int = 3) -> dict:
    """Sends extracted OCR payload to Google Apps Script Web App with automatic retries."""
    target_url = (gas_url or os.environ.get("GAS_WEBHOOK_URL") or os.environ.get("GOOGLE_SCRIPT_URL") or "").strip()
    if not target_url:
        return {"status": "skipped", "message": "No GAS URL provided"}

    clean_url = target_url
    last_error = None


    token = get_secret_token()
    if token and isinstance(payload, dict) and "secret" not in payload:
        payload["secret"] = token

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(clean_url, json=payload, timeout=45)
            if resp.status_code == 200:
                # Check if Google returned an HTML sign-in/access prompt instead of JSON
                text_start = resp.text.strip().lower()[:150]
                if "<html" in text_start or "<!doctype" in text_start:
                    return {
                        "status": "error",
                        "http_code": 403,
                        "message": "Google memerlukan izin akses. Pastikan akses Web App disetel ke 'Siapa saja (Anyone)' di Google Apps Script."
                    }
                try:
                    data = resp.json()
                    data["http_code"] = resp.status_code
                    return data
                except Exception:
                    return {"status": "success", "http_code": resp.status_code, "raw_response": resp.text[:200]}
            elif resp.status_code in [429, 500, 502, 503, 504]:
                last_error = f"HTTP {resp.status_code}"
                if attempt < max_retries:
                    time.sleep(1.5 * attempt)
                    continue
                return {"status": "error", "http_code": resp.status_code, "message": last_error}
            else:
                return {"status": "error", "http_code": resp.status_code, "message": f"HTTP {resp.status_code} (Google unauthorized or blocked)"}
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries:
                time.sleep(1.5 * attempt)
                continue
            return {"status": "error", "error": last_error}

    return {"status": "error", "error": last_error or "Max retries exceeded"}
