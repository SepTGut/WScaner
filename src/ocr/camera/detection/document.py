"""
Real-time document boundary detection, quadrilateral tracking, and perspective unwarping.
Enables borderless live camera scanning by automatically detecting paper/magazine corners
and deskewing the document from any angle in the camera feed.
"""

import time
import cv2
import numpy as np


def order_points(pts: np.ndarray) -> np.ndarray:
    """
    Orders 4 points in clockwise order:
    [top-left, top-right, bottom-right, bottom-left].
    """
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]   # Top-left has smallest sum (x + y)
    rect[2] = pts[np.argmax(s)]   # Bottom-right has largest sum (x + y)

    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # Top-right has smallest difference (y - x)
    rect[3] = pts[np.argmax(diff)]  # Bottom-left has largest difference (y - x)
    return rect


def four_point_transform(image: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """
    Performs perspective unwarp on the quadrilateral region specified by pts.
    Straightens and deskews the document into a flat rectangular image.
    """
    rect = order_points(pts)
    (tl, tr, br, bl) = rect

    # Calculate width of the unwarped image
    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_w = max(int(width_a), int(width_b))

    # Calculate height of the unwarped image
    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_h = max(int(height_a), int(height_b))

    if max_w < 10 or max_h < 10:
        return image

    dst = np.array([
        [0, 0],
        [max_w - 1, 0],
        [max_w - 1, max_h - 1],
        [0, max_h - 1]
    ], dtype="float32")

    transform_matrix = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, transform_matrix, (max_w, max_h), flags=cv2.INTER_LINEAR)
    return warped


class DocumentDetector:
    """
    Fast real-time document contour finder.
    Operates on a downscaled frame to maintain 30 FPS with negligible CPU impact (<8ms).
    """

    def __init__(self, target_downscale_w: int = 480, min_area_ratio: float = 0.08, max_area_ratio: float = 0.95):
        self.target_w = target_downscale_w
        self.min_area_ratio = min_area_ratio
        self.max_area_ratio = max_area_ratio

    def detect_quad(self, frame: np.ndarray) -> np.ndarray | None:
        """
        Detects document quadrilateral corners in the camera frame.
        Returns 4 ordered (x, y) coordinates scaled to the original frame, or None if no clear document found.
        """
        H, W = frame.shape[:2]
        if W == 0 or H == 0:
            return None

        scale = W / self.target_w
        target_h = int(H / scale)

        # Fast downscale
        small = cv2.resize(frame, (self.target_w, target_h), interpolation=cv2.INTER_LINEAR)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Edge detection with slight dilation to close perimeter gaps
        edges = cv2.Canny(blurred, 35, 120)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        dilated = cv2.dilate(edges, kernel, iterations=1)

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        frame_area = self.target_w * target_h

        for c in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
            area = cv2.contourArea(c)
            if area < (frame_area * self.min_area_ratio):
                continue
            if area > (frame_area * self.max_area_ratio):
                continue

            hull = cv2.convexHull(c)
            peri = cv2.arcLength(hull, True)

            # Try varying polygon approximations on the convex hull
            found_quad = False
            quad_pts = None

            for eps_factor in (0.02, 0.025, 0.03, 0.04):
                approx = cv2.approxPolyDP(hull, eps_factor * peri, True)
                if len(approx) == 4 and cv2.isContourConvex(approx):
                    quad_pts = approx.reshape(4, 2).astype("float32")
                    found_quad = True
                    break

            # Fallback to minimum area bounding box
            if not found_quad and area >= (frame_area * self.min_area_ratio):
                rect = cv2.minAreaRect(c)
                box = cv2.boxPoints(rect)
                quad_pts = box.astype("float32")
                found_quad = True

            if found_quad and quad_pts is not None:
                # Scale back to original frame dimensions
                orig_pts = quad_pts * scale
                return order_points(orig_pts)

        return None



class QuadTracker:
    """
    Smooths detected quadrilateral corners across frames using Exponential Moving Average (EMA).
    Eliminates jitter in the HUD overlay while responding instantly to movements.
    """

    def __init__(self, alpha: float = 0.40, max_snap_distance: float = 75.0, hold_frames: int = 4):
        self.alpha = alpha
        self.max_snap_dist = max_snap_distance
        self.hold_frames = hold_frames

        self.current_quad: np.ndarray | None = None
        self.missing_count: int = 0

    def update(self, detected_quad: np.ndarray | None) -> np.ndarray | None:
        """
        Updates the tracker with a newly detected quad.
        Returns the smoothed quadrilateral coordinates, or None if no document is present.
        """
        if detected_quad is None:
            self.missing_count += 1
            if self.missing_count > self.hold_frames:
                self.current_quad = None
            return self.current_quad

        self.missing_count = 0

        if self.current_quad is None:
            self.current_quad = detected_quad.copy()
            return self.current_quad

        # Check movement distance
        displacement = float(np.linalg.norm(detected_quad - self.current_quad))
        if displacement > self.max_snap_dist:
            # Document moved quickly or changed: snap immediately
            self.current_quad = detected_quad.copy()
        else:
            # Smooth using EMA
            self.current_quad = (self.alpha * detected_quad) + ((1.0 - self.alpha) * self.current_quad)

        return self.current_quad

    def reset(self):
        self.current_quad = None
        self.missing_count = 0
