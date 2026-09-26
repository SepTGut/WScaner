"""
Live Camera Auto-Scanner Coordinator.
Coordinates video capture hardware, motion detection, HUD rendering, deduplication history,
and asynchronous multi-engine OCR processing.
"""

import os
import sys
import time
import asyncio
import threading
import argparse
import cv2
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Paths
RUNTIME_DIR = os.path.join(PROJECT_ROOT, "runtime")
TEMP_DIR = os.path.join(RUNTIME_DIR, "temp")
HISTORY_FILE = os.path.join(RUNTIME_DIR, "camera_scan_history.json")
os.makedirs(TEMP_DIR, exist_ok=True)

from src.ocr.camera.hardware.capture import (
    open_capture_device,
    detect_available_cameras,
    resolve_target_resolution,
    interactive_select_camera,
    RESOLUTION_CYCLE,
)
from src.ocr.camera.history.manager import ScanHistoryManager
from src.ocr.camera.ui.hud import HUDRenderer
from src.ocr.camera.ui.audio import play_sound
from src.ocr.camera.detection.motion import MotionDetector
from src.ocr.camera.detection.document import DocumentDetector, QuadTracker, four_point_transform
from src.ocr.pipeline.orientation import auto_orient_cv2
from src.ocr.ocr_processor import process_image
from src.ocr.gas_client import send_to_gas


class LiveCameraScanner:
    """Live camera controller with motion detection, HUD, and OCR pipeline."""

    SUPPORTED_ENGINES = ["auto", "windows", "groq", "gemini", "drive"]
    BOUNDARY_MODES = ["auto", "full", "box"]

    def __init__(
        self,
        camera_index: int = 0,
        engine: str = None,
        gas_url: str = None,
        resolution: str = "1080p",
        width: int = None,
        height: int = None,
        boundary_mode: str = "auto"
    ):
        self.camera_index = camera_index
        self.current_engine = (engine or os.environ.get("OCR_ENGINE", "auto")).lower()
        if self.current_engine not in self.SUPPORTED_ENGINES:
            self.current_engine = "auto"

        self.boundary_mode = (boundary_mode or "auto").lower()
        if self.boundary_mode not in self.BOUNDARY_MODES:
            self.boundary_mode = "auto"

        self.gas_url = gas_url or os.environ.get("GAS_WEBHOOK_URL") or os.environ.get("GOOGLE_SCRIPT_URL")
        self.history_mgr = ScanHistoryManager(HISTORY_FILE, max_items=20)
        self.detector = MotionDetector(
            motion_threshold=4.0,
            min_edge_density=3.8,
            stable_time_required=1.0,
            cooldown_duration=3.5
        )
        self.doc_detector = DocumentDetector(target_downscale_w=480)
        self.quad_tracker = QuadTracker(alpha=0.40, max_snap_distance=75.0, hold_frames=4)

        # Resolution settings (Default: 1080p Full HD)
        self.current_res_preset = (resolution or "1080p").lower()
        self.req_width = width
        self.req_height = height
        self.actual_w = 0
        self.actual_h = 0
        self.fps = 0.0

        # State tracking
        self.is_running = False
        self.is_processing = False
        self.sync_badge = "GAS: TERHUBUNG" if self.gas_url else "GAS: TIDAK AKTIF"
        self.last_extracted = None

    def cycle_boundary_mode(self):
        """Cycles boundary modes: Auto Quad -> Full Frame -> Guide Box."""
        idx = self.BOUNDARY_MODES.index(self.boundary_mode)
        self.boundary_mode = self.BOUNDARY_MODES[(idx + 1) % len(self.BOUNDARY_MODES)]
        labels = {
            "auto": "AUTO-DETECT (Tanpa Batas)",
            "full": "FULL FRAME (Seluruh Layar)",
            "box": "GUIDE BOX (Kotak Panduan)"
        }
        name = labels.get(self.boundary_mode, self.boundary_mode.upper())
        self.detector.set_status(f"Mode Batas: {name}", "ready")
        play_sound("capture")
        print(f"\n[INFO] Mode Batas Diubah: {name}")

    def cycle_engine(self):
        """Cycles through available OCR engines."""
        idx = self.SUPPORTED_ENGINES.index(self.current_engine)
        self.current_engine = self.SUPPORTED_ENGINES[(idx + 1) % len(self.SUPPORTED_ENGINES)]
        self.detector.set_status(f"Mesin OCR diganti ke: {self.current_engine.upper()}", "ready")
        play_sound("capture")


    def cycle_resolution(self, cap: cv2.VideoCapture):
        """Cycles resolution presets on the fly (1080p -> 1440p -> 720p)."""
        idx = 0
        if self.current_res_preset in RESOLUTION_CYCLE:
            idx = (RESOLUTION_CYCLE.index(self.current_res_preset) + 1) % len(RESOLUTION_CYCLE)
        self.current_res_preset = RESOLUTION_CYCLE[idx]
        target_w, target_h = resolve_target_resolution(self.current_res_preset)

        try:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        except Exception:
            pass
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_h)
        cap.set(cv2.CAP_PROP_FPS, 30)
        self.actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.detector.reset_history_buffer()
        self.detector.set_status(f"Resolusi diubah ke: {self.actual_w}x{self.actual_h} ({self.current_res_preset.upper()})", "ready")
        play_sound("capture")
        print(f"\n[INFO] Resolusi Kamera Diubah: {self.actual_w}x{self.actual_h} ({self.current_res_preset.upper()})")

    def process_capture_async(self, frame_to_process: np.ndarray):
        """Dispatches OCR & Upload to a background worker thread."""
        if self.is_processing:
            return

        self.is_processing = True
        self.detector.set_status("Memindai teks cover dengan OCR...", "scanning")
        play_sound("capture")

        def worker():
            temp_path = os.path.join(TEMP_DIR, f"capture_{int(time.time())}.jpg")
            try:
                # 0. Auto-detect orientation and rotate upright before OCR
                oriented_frame, rot_angle = auto_orient_cv2(frame_to_process)
                if rot_angle != 0:
                    print(f"\n[INFO] Auto-orient: Frame pindaian diputar {rot_angle}° ke posisi tegak (upright).")

                cv2.imwrite(temp_path, oriented_frame, [cv2.IMWRITE_JPEG_QUALITY, 95])

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
                    self.detector.set_status(f"BUKAN COVER: {err_msg[:45]}", "unclear")
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

                if not edition and len(valid_articles) < 2:
                    self.detector.set_status("BUKAN COVER: Teks edisi & artikel majalah tidak ditemukan.", "unclear")
                    play_sound("error")
                    return

                # 2. Check Deduplication
                is_dup, matched_item = self.history_mgr.is_duplicate(result)
                if is_dup:
                    dup_ed = matched_item.get("edition") or "?"
                    dup_dt = matched_item.get("date") or ""
                    self.detector.set_status(f"DUPLIKAT: Edisi {dup_ed} ({dup_dt}) sudah pernah dipindai!", "duplicate")
                    play_sound("duplicate")
                    return

                # 3. Valid Unique Scan! Add to history
                self.history_mgr.add(result)
                self.last_extracted = result
                self.detector.set_status(f"SUKSES: Edisi {edition or '?'} ({date_str}) - {len(valid_articles)} artikel", "success")
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
                self.detector.set_status(f"Error OCR: {e}", "unclear")
                play_sound("error")
            finally:
                self.is_processing = False
                self.detector.last_capture_time = time.time()
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    def run(self) -> bool:
        """Main camera execution loop."""
        print(f"\n[INFO] Membuka kamera (Index: {self.camera_index})...")
        target_w, target_h = resolve_target_resolution(self.current_res_preset, self.req_width, self.req_height)
        cap = open_capture_device(self.camera_index, target_w, target_h, fps=30)

        if not cap or not cap.isOpened():
            print(f"[ERROR] Gagal membuka kamera pada index {self.camera_index}.", file=sys.stderr)
            return False

        self.actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[INFO] Resolusi Kamera Aktif: {self.actual_w}x{self.actual_h} ({self.current_res_preset.upper()})")
        print(f"[INFO] Mesin OCR Aktif: {self.current_engine.upper()}")
        print(f"[INFO] Mode Batas: {self.boundary_mode.upper()} (Auto-Detect Kontur)")
        print(f"[INFO] Riwayat Tersimpan: {len(self.history_mgr.history)} entri")
        print("\n=== KONTROL KEYBOARD ===")
        print(" [SPACE] : Pindai manual seketika")
        print(" [B]     : Ganti mode batas (Auto Kontur -> Full Frame -> Kotak Panduan)")
        print(" [R]     : Ganti resolusi kamera (1080p -> 1440p/2K -> 720p)")
        print(" [E]     : Ganti mesin OCR (Auto / Windows / Groq / Gemini / Drive)")
        print(" [C]     : Hapus riwayat pindaian")
        print(" [Q/ESC] : Keluar")
        print("========================\n")

        window_name = "WScaner - Live Camera Auto-Scanner"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        init_win_w = min(self.actual_w, 1600)
        init_win_h = int(init_win_w * (self.actual_h / self.actual_w)) if self.actual_w > 0 else 900
        cv2.resizeWindow(window_name, init_win_w, init_win_h)

        self.is_running = True
        last_frame_time = time.time()
        fps_frame_count = 0
        fps_last_time = time.time()
        self.fps = 0.0

        try:
            while self.is_running:
                ret, frame = cap.read()
                if not ret or frame is None:
                    time.sleep(0.01)
                    continue

                now = time.time()
                dt = now - last_frame_time
                last_frame_time = now

                # Live FPS calculation
                fps_frame_count += 1
                if now - fps_last_time >= 0.5:
                    self.fps = fps_frame_count / (now - fps_last_time)
                    fps_frame_count = 0
                    fps_last_time = now

                H, W = frame.shape[:2]

                # Compute magazine guide box (fallback area for 'box' mode)
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

                # 1. Document Detection & Active Analysis Region Selection
                tracked_quad = None
                active_region = frame

                if self.boundary_mode == "auto":
                    detected_quad = self.doc_detector.detect_quad(frame)
                    tracked_quad = self.quad_tracker.update(detected_quad)
                    if tracked_quad is not None:
                        active_region = four_point_transform(frame, tracked_quad)
                    else:
                        active_region = frame
                elif self.boundary_mode == "box":
                    self.quad_tracker.reset()
                    tracked_quad = None
                    active_region = frame[gy1:gy2, gx1:gx2]
                else:  # "full" mode
                    self.quad_tracker.reset()
                    tracked_quad = None
                    active_region = frame

                # 2. Motion & Content Analysis on Active Region
                should_capture = self.detector.analyze(active_region, dt, now, self.is_processing)
                if should_capture:
                    if self.boundary_mode == "auto" and tracked_quad is not None:
                        capture_img = four_point_transform(frame, tracked_quad)
                    elif self.boundary_mode == "box":
                        capture_img = frame[gy1:gy2, gx1:gx2].copy()
                    else:
                        capture_img = frame.copy()
                    self.process_capture_async(capture_img)

                # 3. Render UI HUD Overlay
                HUDRenderer.render(
                    frame=frame,
                    guide_rect=guide_rect,
                    status_type=self.detector.status_type,
                    status_message=self.detector.status_message,
                    current_engine=self.current_engine,
                    current_edge_density=self.detector.current_edge_density,
                    min_edge_density=self.detector.min_edge_density,
                    fps=self.fps,
                    sync_badge=self.sync_badge,
                    steady_duration=self.detector.steady_duration,
                    stable_time_required=self.detector.stable_time_required,
                    is_processing=self.is_processing,
                    history=self.history_mgr.history,
                    detected_quad=tracked_quad,
                    boundary_mode=self.boundary_mode
                )
                cv2.imshow(window_name, frame)

                # 4. Key controls
                key = cv2.waitKey(1) & 0xFF
                if key in (ord('q'), ord('Q'), 27):  # 27 = ESC
                    print("\n[INFO] Menutup kamera...")
                    break
                elif key in (ord('b'), ord('B')):  # Cycle boundary mode
                    self.cycle_boundary_mode()
                elif key == 32:  # SPACE: Manual capture
                    if not self.is_processing:
                        print("\n[INFO] Manual capture dipicu via [SPACE]!")
                        if self.boundary_mode == "auto" and tracked_quad is not None:
                            capture_img = four_point_transform(frame, tracked_quad)
                        elif self.boundary_mode == "box":
                            capture_img = frame[gy1:gy2, gx1:gx2].copy()
                        else:
                            capture_img = frame.copy()
                        self.process_capture_async(capture_img)
                elif key in (ord('r'), ord('R')):  # Cycle resolution
                    self.cycle_resolution(cap)
                elif key in (ord('c'), ord('C')):  # Clear history
                    self.history_mgr.clear()
                    self.detector.set_status("Riwayat pindaian berhasil dibersihkan! [0/20]", "ready")
                    play_sound("capture")
                    print("\n[INFO] Riwayat pindaian dibersihkan.")
                elif key in (ord('e'), ord('E')):  # Cycle engine
                    self.cycle_engine()
                    print(f"\n[INFO] Mesin OCR diubah ke: {self.current_engine.upper()}")

        finally:
            cap.release()
            cv2.destroyAllWindows()

        return True


def main():
    parser = argparse.ArgumentParser(description="WScaner Live Camera Auto-Scanner")
    parser.add_argument("--camera", "-c", type=int, default=None, help="Index kamera (0, 1, 2, ...)")
    parser.add_argument("--res", "--resolution", "-r", type=str, default="1080p",
                        help="Resolusi kamera: 1080p (default), 720p, 1440p, 2k, 4k, max, atau WxH")
    parser.add_argument("--boundary", "-b", choices=["auto", "full", "box"], default="auto",
                        help="Mode batas: 'auto' (deteksi kontur otomatis & deskew), 'full' (seluruh layar), atau 'box' (kotak panduan)")
    parser.add_argument("--width", type=int, default=None, help="Lebar frame kustom (e.g. 1920)")
    parser.add_argument("--height", type=int, default=None, help="Tinggi frame kustom (e.g. 1080)")
    parser.add_argument("--engine", "-e", choices=["auto", "windows", "groq", "gemini", "drive"],
                        default=None, help="Pilih mesin OCR (auto, windows, groq, gemini, drive)")
    parser.add_argument("--gas-url", type=str, default=None, help="URL Google Apps Script Webhook")
    parser.add_argument("--clear-history", action="store_true", help="Hapus riwayat duplikasi sebelum mulai")

    args = parser.parse_args()

    if args.clear_history:
        history_mgr = ScanHistoryManager(HISTORY_FILE)
        history_mgr.clear()
        print("[INFO] Riwayat scan dibersihkan.")

    cam_idx = args.camera
    if cam_idx is None:
        cam_idx = interactive_select_camera()

    scanner = LiveCameraScanner(
        camera_index=cam_idx,
        engine=args.engine,
        gas_url=args.gas_url,
        resolution=args.res,
        width=args.width,
        height=args.height,
        boundary_mode=args.boundary
    )
    scanner.run()


if __name__ == "__main__":
    main()

