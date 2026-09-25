"""
Camera hardware discovery, capture device opening, and resolution management.
Prioritizes Windows Media Foundation (MSMF) for fluid 30 FPS HD streaming.
"""

import sys
import cv2

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


def resolve_target_resolution(preset_or_str: str, custom_w: int = None, custom_h: int = None) -> tuple[int, int]:
    """Resolves target width and height from preset names or dimensions."""
    if custom_w and custom_h:
        return (custom_w, custom_h)
    val = (preset_or_str or "1080p").lower().strip()
    if val in RESOLUTION_PRESETS:
        return RESOLUTION_PRESETS[val]
    if "x" in val:
        try:
            parts = val.split("x")
            return (int(parts[0]), int(parts[1]))
        except Exception:
            pass
    return (1920, 1080)


def open_capture_device(camera_index: int, target_w: int, target_h: int, fps: int = 30) -> cv2.VideoCapture:
    """
    Opens camera with optimal backend (MSMF on Windows for 30 FPS HD)
    with robust DirectShow and generic fallbacks.
    """
    try:
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
    except Exception:
        pass

    if sys.platform == "win32":
        # 1. Try Windows Media Foundation (cv2.CAP_MSMF) - delivers true 30 FPS at 1080p/1440p
        cap = cv2.VideoCapture(camera_index, cv2.CAP_MSMF)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_h)
            cap.set(cv2.CAP_PROP_FPS, fps)
            ret, test_frame = cap.read()
            if ret and test_frame is not None:
                return cap
            cap.release()

        # 2. Fallback to DirectShow if MSMF fails
        cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        if cap.isOpened():
            try:
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            except Exception:
                pass
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_h)
            cap.set(cv2.CAP_PROP_FPS, fps)
            return cap

    # Linux / macOS / generic
    cap = cv2.VideoCapture(camera_index, cv2.CAP_ANY)
    try:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    except Exception:
        pass
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_h)
    cap.set(cv2.CAP_PROP_FPS, fps)
    return cap


def detect_available_cameras(max_probe: int = 5) -> list[int]:
    """Detects available camera indices without crashing or hanging."""
    try:
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
    except Exception:
        pass

    available = []
    backend = cv2.CAP_MSMF if sys.platform == "win32" else cv2.CAP_ANY
    for idx in range(max_probe):
        cap = cv2.VideoCapture(idx, backend)
        if not cap.isOpened() and sys.platform == "win32":
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                available.append(idx)
            cap.release()
    return available


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
        print(f"[WARN] Index {val} tidak valid. Menggunakan index {cameras[0]}.")
        return cameras[0]
    except Exception:
        return cameras[0]
