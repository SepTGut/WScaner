"""
Motion analysis and document presence detection.
Distinguishes printed documents from faces and empty backgrounds using Canny edge density.
"""

import time
import cv2
import numpy as np


class MotionDetector:
    """Detects movement, stability, and printed document presence."""

    def __init__(
        self,
        motion_threshold: float = 4.0,
        min_edge_density: float = 3.8,
        stable_time_required: float = 1.0,
        cooldown_duration: float = 3.5
    ):
        self.motion_threshold = motion_threshold
        self.min_edge_density = min_edge_density
        self.stable_time_required = stable_time_required
        self.cooldown_duration = cooldown_duration

        self.steady_duration = 0.0
        self.last_capture_time = 0.0
        self.prev_gray_crop = None
        self.current_motion_score = 0.0
        self.current_edge_density = 0.0
        self.waiting_for_next_item = False

        self.status_message = "Arahkan kamera ke cover majalah (Deteksi Otomatis)."
        self.status_type = "ready"
        self.last_status_change = time.time()


    def set_status(self, message: str, status_type: str = "ready"):
        self.status_message = message
        self.status_type = status_type
        self.last_status_change = time.time()

    def reset_history_buffer(self):
        self.prev_gray_crop = None

    def analyze(self, crop: np.ndarray, dt: float, now: float, is_processing: bool) -> bool:
        """
        Analyzes the guide box crop.
        Returns True if the document has been held steady long enough to trigger auto-capture.
        """
        if is_processing:
            return False

        # Fast downscale to 240x320 for ultra-fast motion diff & Canny edge detection (<1ms)
        small_crop = cv2.resize(crop, (240, 320))
        gray = cv2.cvtColor(small_crop, cv2.COLOR_BGR2GRAY)
        gray_blur = cv2.GaussianBlur(gray, (7, 7), 0)

        # 1. Edge Density Content Check (Distinguishes printed text/covers from faces and blank walls)
        edges = cv2.Canny(gray, 50, 150)
        edge_density = float(np.mean(edges))
        self.current_edge_density = edge_density
        has_document = edge_density >= self.min_edge_density

        trigger_capture = False

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
                    self.set_status("Arahkan kamera ke cover majalah (Deteksi Otomatis).", "ready")

            # Case B: Already captured this document and holding it still -> Wait for swap
            elif self.waiting_for_next_item:
                self.steady_duration = 0.0
                if (now - self.last_status_change) > 2.5:
                    self.set_status("Selesai. Ganti atau geser majalah untuk memindai berikutnya.", "ready")

            # Case C: Real document present & held steady -> Count down to auto-capture!
            elif is_steady and not in_cooldown:
                self.steady_duration += dt
                if self.status_type != "scanning":
                    self.set_status("Tahan posisi majalah... Menstabilkan untuk pindaian otomatis.", "stabilizing")

                # If steady duration meets threshold, trigger auto-scan!
                if self.steady_duration >= self.stable_time_required:
                    self.steady_duration = 0.0
                    self.waiting_for_next_item = True
                    trigger_capture = True

            # Case D: Real document is moving or adjusting
            else:
                self.steady_duration = max(0.0, self.steady_duration - (dt * 1.5))
                if not in_cooldown and (now - self.last_status_change) > 2.5:
                    self.set_status("Arahkan cover majalah ke kamera. Tahan stabil 1 detik.", "ready")


        self.prev_gray_crop = gray_blur
        return trigger_capture
