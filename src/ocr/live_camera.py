"""
WScaner Live Camera Auto-Scanner
Real-time webcam feed with automatic stability detection, deduplication cache,
multi-engine OCR extraction, and background synchronization to Google Sheets & Drive.
"""

import os
import sys
import time
import json
import asyncio
import threading
import argparse
from datetime import datetime

# Configure UTF-8 for Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Suppress noisy OpenCV backend logs
os.environ["OPENCV_LOG_LEVEL"] = "OFF"
os.environ["OPENCV_VIDEOIO_DEBUG"] = "0"

import cv2
import numpy as np

# Audio feedback on Windows
try:
    import winsound
    def play_sound(sound_type: str):
        def _play():
            try:
                if sound_type == "success":
                    winsound.Beep(1200, 100)
                    winsound.Beep(1600, 150)
                elif sound_type == "duplicate":
                    winsound.Beep(650, 120)
                    winsound.Beep(650, 120)
                elif sound_type == "capture":
                    winsound.Beep(1000, 80)
                elif sound_type == "error":
                    winsound.Beep(400, 200)
            except Exception:
                pass
        threading.Thread(target=_play, daemon=True).start()
except ImportError:
    def play_sound(sound_type: str):
        pass

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path, override=False)
except Exception:
    pass

from src.ocr.ocr_processor import process_image
from src.ocr.gas_client import send_to_gas

# Paths
RUNTIME_DIR = os.path.join(PROJECT_ROOT, "runtime")
TEMP_DIR = os.path.join(RUNTIME_DIR, "temp")
HISTORY_FILE = os.path.join(RUNTIME_DIR, "camera_scan_history.json")

os.makedirs(TEMP_DIR, exist_ok=True)


class ScanHistoryManager:
    """Manages persistent LRU deduplication history of past scans."""

    def __init__(self, history_file: str, max_items: int = 20):
        self.history_file = history_file
        self.max_items = max_items
        self.history = self._load()

    def _load(self) -> list:
        if os.path.exists(self.history_file):
            try:
                if os.path.getsize(self.history_file) == 0:
                    return []
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data[-self.max_items:]
            except Exception as e:
                print(f"[WARN] Gagal membaca riwayat pindaian: {e}", file=sys.stderr)
        return []

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[WARN] Gagal menyimpan riwayat pindaian: {e}", file=sys.stderr)

    def clear(self):
        self.history = []
        self.save()

    def generate_signature(self, record: dict) -> dict:
        ed = str(record.get("edition") or "").strip().lower()
        yr = str(record.get("year_roman") or "").strip().lower()
        dt = str(record.get("date") or "").strip().lower()
        raw_articles = record.get("articles") or []
        articles = []
        for a in raw_articles:
            title = ""
            if isinstance(a, dict):
                title = a.get("title") or ""
            elif isinstance(a, str):
                title = a
            title = str(title).strip().lower()
            if len(title) > 3:
                articles.append(title)

        return {
            "edition": ed,
            "year_roman": yr,
            "date": dt,
            "articles": articles[:5]
        }

    def is_duplicate(self, record: dict) -> tuple[bool, dict | None]:
        """
        Checks if a scan matches any record in the recent history.
        Matches by edition & date, or significant article title overlap.
        """
        sig = self.generate_signature(record)
        if not sig["edition"] and not sig["articles"]:
            return False, None

        for item in reversed(self.history):
            item_ed = str(item.get("edition") or "").strip().lower()
            item_dt = str(item.get("date") or "").strip().lower()

            # Check 1: Edition Match
            if sig["edition"] and item_ed and sig["edition"] == item_ed:
                # If date matches or either has empty date
                if not sig["date"] or not item_dt or sig["date"] == item_dt:
                    return True, item

            # Check 2: Article title overlap
            item_articles = set(str(a).strip().lower() for a in item.get("articles", []))
            if item_articles and sig["articles"]:
                common = item_articles.intersection(set(sig["articles"]))
                if len(common) >= 2 or (len(common) == 1 and len(sig["articles"]) <= 2):
                    return True, item

        return False, None

    def add(self, record: dict):
        sig = self.generate_signature(record)
        entry = {
            "edition": record.get("edition") or "-",
            "year_roman": record.get("year_roman") or "-",
            "date": record.get("date") or "-",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "articles_count": len(record.get("articles") or []),
            "articles": sig["articles"],
            "summary": f"Edisi {record.get('edition') or '?'} ({record.get('date') or '?'})"
        }
        self.history.append(entry)
        if len(self.history) > self.max_items:
            self.history = self.history[-self.max_items:]
        self.save()


def detect_available_cameras(max_probe: int = 5) -> list[int]:
    """Detects available camera indices without crashing or hanging."""
    try:
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
    except Exception:
        pass

    available = []
    for idx in range(max_probe):
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                available.append(idx)
            cap.release()
    return available


class LiveCameraScanner:
    """Live camera controller with motion detection, HUD, and OCR pipeline."""

    SUPPORTED_ENGINES = ["auto", "windows", "groq", "gemini", "drive"]
    RESOLUTION_PRESETS = {
        "480p": (640, 480),
        "720p": (1280, 720),
        "hd": (1280, 720),
        "1080p": (1920, 1080),
        "fhd": (1920, 1080),
        "1440p": (2560, 1440),
        "2k": (2560, 1440),
        "4k": (3840, 2160),
        "max": (3840, 2160),
    }
    RESOLUTION_CYCLE = ["1080p", "1440p", "720p"]

    @classmethod
    def _resolve_target_resolution(cls, preset_or_str: str, custom_w: int = None, custom_h: int = None) -> tuple[int, int]:
        if custom_w and custom_h:
            return (custom_w, custom_h)
        val = (preset_or_str or "1080p").lower().strip()
        if val in cls.RESOLUTION_PRESETS:
            return cls.RESOLUTION_PRESETS[val]
        if "x" in val:
            try:
                parts = val.split("x")
                return (int(parts[0]), int(parts[1]))
            except Exception:
                pass
        return (1920, 1080)

    def __init__(
        self,
        camera_index: int = 0,
        engine: str = None,
        gas_url: str = None,
        resolution: str = "1080p",
        width: int = None,
        height: int = None
    ):
        self.camera_index = camera_index
        self.current_engine = (engine or os.environ.get("OCR_ENGINE", "auto")).lower()
        if self.current_engine not in self.SUPPORTED_ENGINES:
            self.current_engine = "auto"

        self.gas_url = gas_url or os.environ.get("GAS_WEBHOOK_URL") or os.environ.get("GOOGLE_SCRIPT_URL")
        self.history_mgr = ScanHistoryManager(HISTORY_FILE, max_items=20)

        # Resolution settings (Default: 1080p Full HD)
        self.current_res_preset = (resolution or "1080p").lower()
        self.req_width = width
        self.req_height = height
        self.actual_w = 0
        self.actual_h = 0

        # State tracking
        self.is_running = False
        self.is_processing = False
        self.status_message = "Arahkan cover majalah ke dalam kotak panduan."
        self.status_type = "ready"  # ready | stabilizing | scanning | success | duplicate | unclear
        self.last_status_change = time.time()
        self.sync_badge = "GAS: TERHUBUNG" if self.gas_url else "GAS: TIDAK AKTIF"

        # Stability & Motion settings
        self.motion_threshold = 4.0        # Motion sensitivity
        self.min_edge_density = 3.8        # Minimum edge density to confirm printed document (rejects faces/walls)
        self.stable_time_required = 1.0     # Must hold steady for 1.0s to trigger
        self.cooldown_duration = 3.5        # Seconds to wait after capture before next auto-trigger
        self.steady_duration = 0.0
        self.last_capture_time = 0.0
        self.prev_gray_crop = None
        self.current_motion_score = 0.0
        self.current_edge_density = 0.0
        self.waiting_for_next_item = False  # Requires motion/swap before auto-triggering again

        # Last scan result
        self.last_extracted = None

    def cycle_engine(self):
        """Cycles through available OCR engines."""
        idx = self.SUPPORTED_ENGINES.index(self.current_engine)
        self.current_engine = self.SUPPORTED_ENGINES[(idx + 1) % len(self.SUPPORTED_ENGINES)]
        self.set_status(f"Mesin OCR diganti ke: {self.current_engine.upper()}", "ready")
        play_sound("capture")

    def cycle_resolution(self, cap):
        """Cycles resolution presets on the fly (1080p -> 1440p -> 720p)."""
        idx = 0
        if self.current_res_preset in self.RESOLUTION_CYCLE:
            idx = (self.RESOLUTION_CYCLE.index(self.current_res_preset) + 1) % len(self.RESOLUTION_CYCLE)
        self.current_res_preset = self.RESOLUTION_CYCLE[idx]
        target_w, target_h = self._resolve_target_resolution(self.current_res_preset)

        try:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        except Exception:
            pass
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_h)
        self.actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.prev_gray_crop = None  # Reset motion crop buffer for size change
        self.set_status(f"Resolusi diubah ke: {self.actual_w}x{self.actual_h} ({self.current_res_preset.upper()})", "ready")
        play_sound("capture")
        print(f"\n[INFO] Resolusi Kamera Diubah: {self.actual_w}x{self.actual_h} ({self.current_res_preset.upper()})")

    def set_status(self, message: str, status_type: str = "ready"):
        self.status_message = message
        self.status_type = status_type
        self.last_status_change = time.time()

    def process_capture_async(self, frame_to_process: np.ndarray):
        """Dispatches OCR & Upload to a background worker thread."""
        if self.is_processing:
            return

        self.is_processing = True
        self.set_status("Memindai teks cover dengan OCR...", "scanning")
        play_sound("capture")

        def worker():
            temp_path = os.path.join(TEMP_DIR, f"capture_{int(time.time())}.jpg")
            try:
                # Save frame
                cv2.imwrite(temp_path, frame_to_process, [cv2.IMWRITE_JPEG_QUALITY, 95])

                # 1. Run OCR (send_gas=False so we can deduplicate first!)
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(
                    process_image(
                        temp_path,
                        gas_url=None,
                        include_drive_image=True,
                        send_gas=False,
                        engine=self.current_engine
                    )
                )
                loop.close()

                if not result or result.get("status") != "success":
                    err_msg = result.get("message") if result else "Cover tidak terdeteksi."
                    self.set_status(f"BUKAN COVER: {err_msg[:45]}", "unclear")
                    play_sound("error")
                    return

                valid_articles = [
                    a for a in (result.get("articles") or [])
                    if isinstance(a, dict) and len(str(a.get("title") or "").strip()) >= 5
                ]
                edition = str(result.get("edition") or "").strip()
                if edition in ("-", "null", "none", "", "?"):
                    edition = ""
                date_str = result.get("date") or ""

                # Real magazine cover MUST have a recognized edition OR at least 2 valid articles
                if not edition and len(valid_articles) < 2:
                    self.set_status("BUKAN COVER: Teks edisi & artikel majalah tidak ditemukan.", "unclear")
                    play_sound("error")
                    return

                # 2. Check Deduplication
                is_dup, matched_item = self.history_mgr.is_duplicate(result)
                if is_dup:
                    dup_ed = matched_item.get("edition") or "?"
                    dup_dt = matched_item.get("date") or ""
                    self.set_status(f"DUPLIKAT: Edisi {dup_ed} ({dup_dt}) sudah pernah dipindai!", "duplicate")
                    play_sound("duplicate")
                    return

                # 3. Valid Unique Scan! Add to history
                self.history_mgr.add(result)
                self.last_extracted = result
                self.set_status(f"SUKSES: Edisi {edition or '?'} ({date_str}) - {len(valid_articles)} artikel", "success")
                play_sound("success")

                # 4. Asynchronous Sync to Google Sheets & Drive
                if self.gas_url:
                    self.sync_badge = "MENGUNGGAH KE SHEETS..."
                    gas_resp = send_to_gas(self.gas_url, result)
                    if gas_resp.get("status") == "success" or gas_resp.get("http_code") == 200:
                        self.sync_badge = "SYNC: SUKSES [OK]"
                    else:
                        err_msg = gas_resp.get("message") or gas_resp.get("error") or "Gagal"
                        self.sync_badge = f"SYNC: ERROR [{err_msg[:12]}]"
                else:
                    self.sync_badge = "GAS: TIDAK AKTIF"

            except Exception as e:
                self.set_status(f"Error OCR: {e}", "unclear")
                play_sound("error")
            finally:
                self.is_processing = False
                self.last_capture_time = time.time()
                # Clean up temporary capture file
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    def draw_hud(self, frame: np.ndarray, guide_rect: tuple[int, int, int, int]):
        """Draws modern, rich heads-up display overlay on the camera frame."""
        H, W = frame.shape[:2]
        gx1, gy1, gx2, gy2 = guide_rect

        overlay = frame.copy()

        # 1. Semi-transparent Top Header Bar
        cv2.rectangle(overlay, (0, 0), (W, 46), (18, 18, 24), -1)

        # 2. Status Color Palette
        color_map = {
            "ready": (180, 180, 180),
            "stabilizing": (255, 200, 50),   # Cyan / Light Blue (BGR: 50, 200, 255)
            "scanning": (0, 215, 255),      # Amber Yellow
            "success": (50, 230, 80),       # Vibrant Green
            "duplicate": (30, 130, 255),    # Warm Orange
            "unclear": (60, 60, 235),       # Soft Red
        }
        theme_color = color_map.get(self.status_type, (200, 200, 200))

        # 3. Magazine Guide Box with glowing corner brackets
        corner_len = 36
        corner_thickness = 3
        # Main dashed/dim bounding box
        cv2.rectangle(overlay, (gx1, gy1), (gx2, gy2), (60, 60, 70), 1)

        # Top-Left Bracket
        cv2.line(frame, (gx1, gy1), (gx1 + corner_len, gy1), theme_color, corner_thickness)
        cv2.line(frame, (gx1, gy1), (gx1, gy1 + corner_len), theme_color, corner_thickness)
        # Top-Right Bracket
        cv2.line(frame, (gx2, gy1), (gx2 - corner_len, gy1), theme_color, corner_thickness)
        cv2.line(frame, (gx2, gy1), (gx2, gy1 + corner_len), theme_color, corner_thickness)
        # Bottom-Left Bracket
        cv2.line(frame, (gx1, gy2), (gx1 + corner_len, gy2), theme_color, corner_thickness)
        cv2.line(frame, (gx1, gy2), (gx1, gy2 - corner_len), theme_color, corner_thickness)
        # Bottom-Right Bracket
        cv2.line(frame, (gx2, gy2), (gx2 - corner_len, gy2), theme_color, corner_thickness)
        cv2.line(frame, (gx2, gy2), (gx2, gy2 - corner_len), theme_color, corner_thickness)

        # 4. Stability Progress Bar (under guide box)
        bar_w = gx2 - gx1
        bar_y = gy2 + 10
        bar_h = 10
        if bar_y + bar_h < H - 55:
            # Bar background
            cv2.rectangle(overlay, (gx1, bar_y), (gx2, bar_y + bar_h), (35, 35, 45), -1)
            cv2.rectangle(frame, (gx1, bar_y), (gx2, bar_y + bar_h), (70, 70, 85), 1)

            # Fill bar based on stability
            progress = min(1.0, max(0.0, self.steady_duration / self.stable_time_required))
            if progress > 0.05 and not self.is_processing:
                fill_w = int(bar_w * progress)
                bar_color = (0, 220, 255) if progress < 0.95 else (50, 230, 80)
                cv2.rectangle(frame, (gx1, bar_y), (gx1 + fill_w, bar_y + bar_h), bar_color, -1)

        # 5. Right Sidebar: Recent History Card
        card_w = 280
        card_h = 135
        card_x1 = W - card_w - 15
        card_y1 = 56
        card_x2 = W - 15
        card_y2 = card_y1 + card_h

        cv2.rectangle(overlay, (card_x1, card_y1), (card_x2, card_y2), (20, 20, 26), -1)

        # 6. Bottom Status Banner
        banner_h = 50
        cv2.rectangle(overlay, (0, H - banner_h), (W, H), (15, 15, 20), -1)

        # Blend overlays for smooth transparency
        cv2.addWeighted(overlay, 0.78, frame, 0.22, 0, frame)

        # Draw Text / Badges over blended frame
        # Header text
        cv2.putText(frame, "WSCANER LIVE CAMERA", (18, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
        cv2.putText(frame, f"ENGINE: {self.current_engine.upper()}", (275, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 220, 255), 1)

        doc_detected = self.current_edge_density >= self.min_edge_density
        doc_label = "DOC: SIAP [OK]" if doc_detected else "DOC: MENCARI COVER..."
        doc_color = (80, 240, 100) if doc_detected else (140, 140, 150)
        cv2.putText(frame, doc_label, (470, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.46, doc_color, 1)

        # Resolution Badge
        res_badge = f"RES: {W}x{H}"
        cv2.putText(frame, res_badge, (675, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (200, 215, 230), 1)

        cv2.putText(frame, self.sync_badge, (W - 230, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (180, 240, 180), 1)

        # Sidebar text (History)
        cv2.rectangle(frame, (card_x1, card_y1), (card_x2, card_y2), (60, 60, 75), 1)
        hist_count = len(self.history_mgr.history)
        cv2.putText(frame, f"RIWAYAT SCAN ({hist_count}/20)", (card_x1 + 12, card_y1 + 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 220, 255), 1)

        recent_items = list(reversed(self.history_mgr.history))[:3]
        if not recent_items:
            cv2.putText(frame, "Belum ada riwayat", (card_x1 + 12, card_y1 + 55),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (130, 130, 140), 1)
        else:
            y_offset = card_y1 + 50
            for idx, item in enumerate(recent_items):
                ed_val = item.get("edition") or "?"
                dt_val = item.get("date") or ""
                time_str = item.get("timestamp", "").split(" ")[-1][:5]
                text_item = f"#{idx + 1} Edisi {ed_val} ({dt_val}) [{time_str}]"
                if len(text_item) > 28:
                    text_item = text_item[:27] + ".."
                cv2.putText(frame, text_item, (card_x1 + 12, y_offset),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, (230, 230, 230), 1)
                y_offset += 24

        # Status Banner Text
        status_prefix = {
            "ready": "[SIAP]",
            "stabilizing": "[STABILISASI]",
            "scanning": "[MEMINDAI]",
            "success": "[SUKSES]",
            "duplicate": "[DUPLIKAT]",
            "unclear": "[PERIKSA]"
        }.get(self.status_type, "")

        full_status = f"{status_prefix} {self.status_message}"
        cv2.putText(frame, full_status, (18, H - 24), cv2.FONT_HERSHEY_SIMPLEX, 0.54, theme_color, 2)

        # Controls Hint
        controls_hint = "[SPACE] Foto | [R] Resolusi | [E] Mesin OCR | [C] Reset | [Q] Keluar"
        cv2.putText(frame, controls_hint, (W - 570, H - 24), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (160, 160, 170), 1)

    def run(self):
        """Main camera loop."""
        print(f"\n[INFO] Membuka kamera (Index: {self.camera_index})...")
        cap = cv2.VideoCapture(
            self.camera_index,
            cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        )

        if not cap.isOpened():
            print(f"[ERROR] Gagal membuka kamera pada index {self.camera_index}.", file=sys.stderr)
            return False

        # Configure High-Definition Resolution (Default: 1080p Full HD)
        target_w, target_h = self._resolve_target_resolution(self.current_res_preset, self.req_width, self.req_height)
        try:
            # Set MJPG for fluid 30 FPS at 1080p/1440p across USB & integrated webcams
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        except Exception:
            pass

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_h)
        self.actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[INFO] Resolusi Kamera Aktif: {self.actual_w}x{self.actual_h} ({self.current_res_preset.upper()})")
        print(f"[INFO] Mesin OCR Aktif: {self.current_engine.upper()}")
        print(f"[INFO] Riwayat Tersimpan: {len(self.history_mgr.history)} entri")
        print("\n=== KONTROL KEYBOARD ===")
        print(" [SPACE] : Pindai manual seketika")
        print(" [R]     : Ganti resolusi kamera (1080p -> 1440p/2K -> 720p)")
        print(" [E]     : Ganti mesin OCR (Auto / Windows / Groq / Gemini / Drive)")
        print(" [C]     : Hapus riwayat pindaian")
        print(" [Q/ESC] : Keluar")
        print("========================\n")

        window_name = "WScaner - Live Camera Auto-Scanner"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        # Create a spacious, sharp preview window that fits desktop displays comfortably
        init_win_w = min(self.actual_w, 1600)
        init_win_h = int(init_win_w * (self.actual_h / self.actual_w)) if self.actual_w > 0 else 900
        cv2.resizeWindow(window_name, init_win_w, init_win_h)

        self.is_running = True
        last_frame_time = time.time()

        try:
            while self.is_running:
                ret, frame = cap.read()
                if not ret or frame is None:
                    time.sleep(0.01)
                    continue

                now = time.time()
                dt = now - last_frame_time
                last_frame_time = now

                H, W = frame.shape[:2]

                # Compute magazine guide box (centered 4:3 area)
                box_w = int(min(W * 0.72, H * 0.95 * (3 / 4)))
                box_h = int(box_w * (4 / 3))
                if box_h > int(H * 0.82):
                    box_h = int(H * 0.82)
                    box_w = int(box_h * (3 / 4))

                gx1 = (W - box_w) // 2
                gy1 = (H - box_h) // 2 - 10
                gx2 = gx1 + box_w
                gy2 = gy1 + box_h
                guide_rect = (gx1, gy1, gx2, gy2)

                # Motion & Stability Analysis
                if not self.is_processing:
                    # Crop guide region for motion and content detection
                    crop = frame[gy1:gy2, gx1:gx2]
                    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                    gray_blur = cv2.GaussianBlur(gray, (21, 21), 0)

                    # 1. Edge Density Content Check (Distinguishes printed text/covers from faces and blank walls)
                    edges = cv2.Canny(gray, 50, 150)
                    edge_density = float(np.mean(edges))
                    self.current_edge_density = edge_density
                    has_document = edge_density >= self.min_edge_density

                    if self.prev_gray_crop is not None and self.prev_gray_crop.shape == gray_blur.shape:
                        frame_diff = cv2.absdiff(self.prev_gray_crop, gray_blur)
                        motion_val = float(np.mean(frame_diff))
                        self.current_motion_score = motion_val

                        # Movement resets the "waiting for next item" lock
                        if motion_val > 8.0 or not has_document:
                            self.waiting_for_next_item = False

                        # Steady check
                        is_steady = motion_val < self.motion_threshold
                        in_cooldown = (now - self.last_capture_time) < self.cooldown_duration

                        # Case A: No document in frame (Face, wall, empty desk) -> DO NOT TRIGGER
                        if not has_document:
                            self.steady_duration = 0.0
                            if not in_cooldown and (now - self.last_status_change) > 2.0:
                                self.status_type = "ready"
                                self.status_message = "Arahkan cover majalah ke dalam kotak panduan."

                        # Case B: Already captured this document and holding it still -> Wait for swap
                        elif self.waiting_for_next_item:
                            self.steady_duration = 0.0
                            if (now - self.last_status_change) > 2.5:
                                self.status_type = "ready"
                                self.status_message = "Selesai. Ganti atau geser majalah untuk memindai berikutnya."

                        # Case C: Real document present & held steady -> Count down to auto-capture!
                        elif is_steady and not in_cooldown:
                            self.steady_duration += dt
                            if self.status_type != "scanning":
                                self.status_type = "stabilizing"
                                self.status_message = "Tahan posisi majalah... Menstabilkan untuk pindaian otomatis."

                            # If steady duration meets threshold, trigger auto-scan!
                            if self.steady_duration >= self.stable_time_required:
                                self.steady_duration = 0.0
                                self.waiting_for_next_item = True
                                # Capture the high-res crop of the guide box
                                capture_img = crop.copy()
                                self.process_capture_async(capture_img)

                        # Case D: Real document is moving or adjusting
                        else:
                            self.steady_duration = max(0.0, self.steady_duration - (dt * 1.5))
                            if not in_cooldown and (now - self.last_status_change) > 2.5:
                                self.status_type = "ready"
                                self.status_message = "Arahkan cover majalah ke dalam kotak panduan. Tahan stabil 1 detik."
                    else:
                        self.prev_gray_crop = gray_blur

                    self.prev_gray_crop = gray_blur

                # Draw UI HUD
                self.draw_hud(frame, guide_rect)
                cv2.imshow(window_name, frame)

                # Key controls
                key = cv2.waitKey(1) & 0xFF
                if key in (ord('q'), ord('Q'), 27):  # 27 = ESC
                    print("\n[INFO] Menutup kamera...")
                    break
                elif key == 32:  # SPACE: Manual capture
                    if not self.is_processing:
                        print("\n[INFO] Manual capture dipicu via [SPACE]!")
                        crop = frame[gy1:gy2, gx1:gx2]
                        self.process_capture_async(crop.copy())
                elif key in (ord('r'), ord('R')):  # Cycle resolution
                    self.cycle_resolution(cap)
                elif key in (ord('c'), ord('C')):  # Clear history
                    self.history_mgr.clear()
                    self.set_status("Riwayat pindaian berhasil dibersihkan! [0/20]", "ready")
                    play_sound("capture")
                    print("\n[INFO] Riwayat pindaian dibersihkan.")
                elif key in (ord('e'), ord('E')):  # Cycle engine
                    self.cycle_engine()
                    print(f"\n[INFO] Mesin OCR diubah ke: {self.current_engine.upper()}")

        finally:
            cap.release()
            cv2.destroyAllWindows()

        return True


def interactive_select_camera() -> int:
    """Interactively prompts user to choose camera if multiple available."""
    print("Mendeteksi kamera yang terhubung...")
    cameras = detect_available_cameras(max_probe=5)

    if not cameras:
        print("[WARN] Tidak ada kamera terdeteksi otomatis. Mencoba index 0 secara default.")
        return 0

    if len(cameras) == 1:
        print(f"[INFO] 1 Kamera terdeteksi: Index {cameras[0]}")
        return cameras[0]

    print("\nBeberapa kamera terdeteksi:")
    for idx in cameras:
        print(f"  [{idx}] Kamera #{idx}")

    try:
        choice = input(f"Pilih nomor index kamera [{cameras[0]}]: ").strip()
        if not choice:
            return cameras[0]
        val = int(choice)
        if val in cameras:
            return val
        print(f"[WARN] Pilihan {val} tidak valid. Menggunakan {cameras[0]}.")
        return cameras[0]
    except Exception:
        return cameras[0]


def main():
    parser = argparse.ArgumentParser(description="WScaner Live Camera Auto-Scanner")
    parser.add_argument("--camera", "-c", type=int, default=None, help="Index kamera (0, 1, 2, ...)")
    parser.add_argument("--res", "--resolution", "-r", default="1080p",
                        help="Resolusi kamera: 1080p (default), 720p, 1440p, 2k, 4k, max, atau WxH")
    parser.add_argument("--width", type=int, default=None, help="Lebar frame kustom (e.g. 1920)")
    parser.add_argument("--height", type=int, default=None, help="Tinggi frame kustom (e.g. 1080)")
    parser.add_argument("--engine", "-e", choices=LiveCameraScanner.SUPPORTED_ENGINES, default=None,
                        help="Pilih mesin OCR (auto, windows, groq, gemini, drive)")
    parser.add_argument("--gas-url", help="URL Google Apps Script Webhook")
    parser.add_argument("--clear-history", action="store_true", help="Hapus riwayat duplikasi sebelum mulai")

    args = parser.parse_args()

    if args.clear_history:
        mgr = ScanHistoryManager(HISTORY_FILE)
        mgr.clear()
        print("[INFO] Riwayat pindaian dibersihkan.")

    cam_idx = args.camera
    if cam_idx is None:
        cam_idx = interactive_select_camera()

    scanner = LiveCameraScanner(
        camera_index=cam_idx,
        engine=args.engine,
        gas_url=args.gas_url,
        resolution=args.res,
        width=args.width,
        height=args.height
    )
    scanner.run()


if __name__ == "__main__":
    main()
