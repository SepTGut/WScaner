import os
import sys
import json
import asyncio
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ocr.ocr_processor import process_image
from ocr.engine import get_ocr_engine_name
from ocr.gas_client import send_to_gas

HOST = "127.0.0.1"
PORT = int(os.environ.get("OCR_PORT", 5005))


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class OCRRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence default request logging to avoid terminal clutter
        pass

    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {
                "status": "ok",
                "engine": get_ocr_engine_name(),
                "time": time.time()
            })
        else:
            self._send_json(404, {"status": "error", "message": "Not found"})

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len) if content_len > 0 else b"{}"
        
        try:
            req_data = json.loads(post_body.decode("utf-8"))
        except Exception as e:
            self._send_json(400, {"status": "error", "message": f"Invalid JSON body: {str(e)}"})
            return

        if self.path == "/ocr":
            image_path = req_data.get("image_path")
            if not image_path or not os.path.exists(image_path):
                self._send_json(400, {"status": "error", "message": f"Invalid or missing image_path: {image_path}"})
                return

            include_drive_img = req_data.get("include_drive_image", True)
            engine_req = req_data.get("engine", os.environ.get("OCR_ENGINE", "windows"))
            try:
                t0 = time.perf_counter()
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                res = loop.run_until_complete(
                    process_image(image_path, gas_url=None, include_drive_image=include_drive_img, send_gas=False, engine=engine_req)
                )
                loop.close()
                t1 = time.perf_counter()
                res["ocr_duration_ms"] = int((t1 - t0) * 1000)
                self._send_json(200, res)
            except Exception as e:
                self._send_json(500, {"status": "error", "message": str(e)})

        elif self.path == "/sync-gas":
            gas_url = req_data.get("gas_url")
            payload = req_data.get("payload")
            if not gas_url or not payload:
                self._send_json(400, {"status": "error", "message": "gas_url and payload are required"})
                return

            try:
                t0 = time.perf_counter()
                gas_res = send_to_gas(gas_url, payload)
                t1 = time.perf_counter()
                gas_res["gas_duration_ms"] = int((t1 - t0) * 1000)
                self._send_json(200, gas_res)
            except Exception as e:
                self._send_json(500, {"status": "error", "message": str(e)})

        elif self.path == "/shutdown":
            self._send_json(200, {"status": "shutting_down"})
            def kill():
                time.sleep(0.5)
                os._exit(0)
            import threading
            threading.Thread(target=kill, daemon=True).start()

        else:
            self._send_json(404, {"status": "error", "message": "Not found"})


def run_server():
    server = ThreadedHTTPServer((HOST, PORT), OCRRequestHandler)
    print(f"[OCR SERVER] Started on http://{HOST}:{PORT} (Engine: {get_ocr_engine_name()})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[OCR SERVER] Stopping...", flush=True)
        server.shutdown()


if __name__ == "__main__":
    run_server()
