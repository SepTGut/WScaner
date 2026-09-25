"""
WScaner Live Camera Package.
Provides hardware capture, motion detection, HUD rendering, and scan history.
"""

from .scanner import LiveCameraScanner, main, interactive_select_camera
from .hardware.capture import open_capture_device, detect_available_cameras, resolve_target_resolution
from .detection.motion import MotionDetector
from .history.manager import ScanHistoryManager
from .ui.hud import HUDRenderer
from .ui.audio import play_sound

__all__ = [
    "LiveCameraScanner",
    "main",
    "interactive_select_camera",
    "open_capture_device",
    "detect_available_cameras",
    "resolve_target_resolution",
    "MotionDetector",
    "ScanHistoryManager",
    "HUDRenderer",
    "play_sound"
]
