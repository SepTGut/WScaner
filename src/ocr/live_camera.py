"""
WScaner Live Camera Auto-Scanner Entry Point
Delegates to the modular src.ocr.camera package.
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.ocr.camera.scanner import LiveCameraScanner, main, interactive_select_camera
from src.ocr.camera.hardware.capture import open_capture_device, detect_available_cameras, resolve_target_resolution
from src.ocr.camera.history.manager import ScanHistoryManager
from src.ocr.camera.detection.motion import MotionDetector
from src.ocr.camera.ui.hud import HUDRenderer
from src.ocr.camera.ui.audio import play_sound

__all__ = [
    "LiveCameraScanner",
    "main",
    "interactive_select_camera",
    "open_capture_device",
    "detect_available_cameras",
    "resolve_target_resolution",
    "ScanHistoryManager",
    "MotionDetector",
    "HUDRenderer",
    "play_sound"
]

if __name__ == "__main__":
    main()
