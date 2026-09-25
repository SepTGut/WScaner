"""Camera hardware and video capture abstractions."""

from .capture import open_capture_device, detect_available_cameras, resolve_target_resolution, RESOLUTION_PRESETS, RESOLUTION_CYCLE

__all__ = [
    "open_capture_device",
    "detect_available_cameras",
    "resolve_target_resolution",
    "RESOLUTION_PRESETS",
    "RESOLUTION_CYCLE"
]
