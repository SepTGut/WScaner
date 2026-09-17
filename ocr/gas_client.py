import requests
import time

def send_to_gas(gas_url: str, payload: dict, max_retries: int = 3) -> dict:
    """Sends extracted OCR payload to Google Apps Script Web App with automatic retries."""
    if not gas_url or not gas_url.strip():
        return {"status": "skipped", "message": "No GAS URL provided"}
    
    clean_url = gas_url.strip()
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(clean_url, json=payload, timeout=45)
            if resp.status_code == 200:
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
