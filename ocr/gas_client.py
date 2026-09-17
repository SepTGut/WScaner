import requests

def send_to_gas(gas_url: str, payload: dict) -> dict:
    """Sends extracted OCR payload to Google Apps Script Web App."""
    if not gas_url or not gas_url.strip():
        return {"status": "skipped", "message": "No GAS URL provided"}
    
    try:
        resp = requests.post(gas_url.strip(), json=payload, timeout=45)
        if resp.status_code == 200:
            try:
                data = resp.json()
                data["http_code"] = resp.status_code
                return data
            except Exception:
                return {"status": "success", "http_code": resp.status_code, "raw_response": resp.text[:200]}
        else:
            return {"status": "error", "http_code": resp.status_code, "message": f"HTTP {resp.status_code} (Google blocked or unauthorized)"}
    except Exception as e:
        return {"status": "error", "error": str(e)}
