"""
HUD (Heads-Up Display) overlay renderer for live camera preview.
Uses high-performance ROI alpha blending and responsive text placement.
"""

import cv2
import numpy as np


class HUDRenderer:
    """Renders real-time HUD graphics and telemetry badges on camera frames."""

    COLOR_MAP = {
        "ready": (180, 180, 180),
        "stabilizing": (255, 200, 50),   # Cyan / Light Blue
        "scanning": (0, 215, 255),      # Amber Yellow
        "success": (50, 230, 80),       # Vibrant Green
        "duplicate": (30, 130, 255),    # Warm Orange
        "unclear": (60, 60, 235),       # Soft Red
    }

    @classmethod
    def render(
        cls,
        frame: np.ndarray,
        guide_rect: tuple[int, int, int, int],
        status_type: str,
        status_message: str,
        current_engine: str,
        current_edge_density: float,
        min_edge_density: float,
        fps: float,
        sync_badge: str,
        steady_duration: float,
        stable_time_required: float,
        is_processing: bool,
        history: list[dict],
        detected_quad: np.ndarray = None,
        boundary_mode: str = "auto"
    ):
        """Draws heads-up display overlay using zero-allocation ROI blending."""
        H, W = frame.shape[:2]
        gx1, gy1, gx2, gy2 = guide_rect

        # 1. Semi-transparent Top Header Bar (Fast ROI blend)
        top_h = 46
        roi_top = frame[0:top_h, 0:W]
        overlay_top = np.full_like(roi_top, (18, 18, 24))
        cv2.addWeighted(overlay_top, 0.78, roi_top, 0.22, 0, roi_top)

        # 2. Status Theme Color
        theme_color = cls.COLOR_MAP.get(status_type, (200, 200, 200))

        # 3. Document Boundaries / Overlay Visualization
        if boundary_mode == "box":
            # Legacy Fixed Guide Box
            corner_len = 36
            corner_thickness = 3
            cv2.rectangle(frame, (gx1, gy1), (gx2, gy2), (60, 60, 70), 1)

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

            # Stability Progress Bar (under guide box)
            bar_w = gx2 - gx1
            bar_y = gy2 + 10
            bar_h = 10
            if bar_y + bar_h < H - 55:
                cv2.rectangle(frame, (gx1, bar_y), (gx2, bar_y + bar_h), (35, 35, 45), -1)
                cv2.rectangle(frame, (gx1, bar_y), (gx2, bar_y + bar_h), (70, 70, 85), 1)
                progress = min(1.0, max(0.0, steady_duration / stable_time_required))
                if progress > 0.05 and not is_processing:
                    fill_w = int(bar_w * progress)
                    bar_color = (0, 220, 255) if progress < 0.95 else (50, 230, 80)
                    cv2.rectangle(frame, (gx1, bar_y), (gx1 + fill_w, bar_y + bar_h), bar_color, -1)

        elif boundary_mode == "auto" and detected_quad is not None:
            # Dynamic Glowing Document Quad Outline
            pts_int = np.int32(detected_quad)
            # Outer subtle glow
            cv2.polylines(frame, [pts_int], isClosed=True, color=(40, 40, 50), thickness=3, lineType=cv2.LINE_AA)
            # Active tracking line
            cv2.polylines(frame, [pts_int], isClosed=True, color=theme_color, thickness=2, lineType=cv2.LINE_AA)

            # Corner circles & crosshairs
            for pt in pts_int:
                cv2.circle(frame, (int(pt[0]), int(pt[1])), 5, theme_color, -1, lineType=cv2.LINE_AA)
                cv2.circle(frame, (int(pt[0]), int(pt[1])), 9, (255, 255, 255), 1, lineType=cv2.LINE_AA)

            # Stability Progress Bar (Bottom Centered)
            bar_w = int(min(W * 0.45, 420))
            bar_x1 = (W - bar_w) // 2
            bar_x2 = bar_x1 + bar_w
            bar_y = H - 58
            bar_h = 7
            cv2.rectangle(frame, (bar_x1, bar_y), (bar_x2, bar_y + bar_h), (35, 35, 45), -1)
            cv2.rectangle(frame, (bar_x1, bar_y), (bar_x2, bar_y + bar_h), (70, 70, 85), 1)
            progress = min(1.0, max(0.0, steady_duration / stable_time_required))
            if progress > 0.05 and not is_processing:
                fill_w = int(bar_w * progress)
                bar_color = (0, 220, 255) if progress < 0.95 else (50, 230, 80)
                cv2.rectangle(frame, (bar_x1, bar_y), (bar_x1 + fill_w, bar_y + bar_h), bar_color, -1)

        else:
            # Borderless Full Frame Mode (or Auto with no quad yet)
            # Subtle corner ticks at the 4 screen corners to denote active camera FOV
            tick = 22
            tick_c = (80, 80, 95)
            # Top-left
            cv2.line(frame, (20, 60), (20 + tick, 60), tick_c, 2)
            cv2.line(frame, (20, 60), (20, 60 + tick), tick_c, 2)
            # Top-right
            cv2.line(frame, (W - 20, 60), (W - 20 - tick, 60), tick_c, 2)
            cv2.line(frame, (W - 20, 60), (W - 20, 60 + tick), tick_c, 2)
            # Bottom-left
            cv2.line(frame, (20, H - 65), (20 + tick, H - 65), tick_c, 2)
            cv2.line(frame, (20, H - 65), (20, H - 65 - tick), tick_c, 2)
            # Bottom-right
            cv2.line(frame, (W - 20, H - 65), (W - 20 - tick, H - 65), tick_c, 2)
            cv2.line(frame, (W - 20, H - 65), (W - 20, H - 65 - tick), tick_c, 2)

            # Stability Progress Bar (Bottom Centered)
            bar_w = int(min(W * 0.45, 420))
            bar_x1 = (W - bar_w) // 2
            bar_x2 = bar_x1 + bar_w
            bar_y = H - 58
            bar_h = 7
            cv2.rectangle(frame, (bar_x1, bar_y), (bar_x2, bar_y + bar_h), (35, 35, 45), -1)
            cv2.rectangle(frame, (bar_x1, bar_y), (bar_x2, bar_y + bar_h), (70, 70, 85), 1)
            progress = min(1.0, max(0.0, steady_duration / stable_time_required))
            if progress > 0.05 and not is_processing:
                fill_w = int(bar_w * progress)
                bar_color = (0, 220, 255) if progress < 0.95 else (50, 230, 80)
                cv2.rectangle(frame, (bar_x1, bar_y), (bar_x1 + fill_w, bar_y + bar_h), bar_color, -1)

        # 5. Right Sidebar: Recent History Card (Fast ROI blend)
        card_w = 280
        card_h = 135
        card_x1 = max(0, W - card_w - 15)
        card_y1 = 56
        card_x2 = min(W, card_x1 + card_w)
        card_y2 = min(H, card_y1 + card_h)
        if card_x2 > card_x1 and card_y2 > card_y1:
            roi_card = frame[card_y1:card_y2, card_x1:card_x2]
            overlay_card = np.full_like(roi_card, (20, 20, 26))
            cv2.addWeighted(overlay_card, 0.82, roi_card, 0.18, 0, roi_card)
            cv2.rectangle(frame, (card_x1, card_y1), (card_x2, card_y2), (60, 60, 75), 1)

            hist_count = len(history)
            cv2.putText(frame, f"RIWAYAT SCAN ({hist_count}/20)", (card_x1 + 12, card_y1 + 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 220, 255), 1)

            recent_items = list(reversed(history))[:3]
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

        # 6. Bottom Status Banner (Fast ROI blend)
        banner_h = 50
        roi_bot = frame[H - banner_h:H, 0:W]
        overlay_bot = np.full_like(roi_bot, (15, 15, 20))
        cv2.addWeighted(overlay_bot, 0.80, roi_bot, 0.20, 0, roi_bot)

        # Header Badges (Responsive placement)
        cv2.putText(frame, "WSCANER LIVE", (18, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (255, 255, 255), 2)
        cv2.putText(frame, f"ENGINE: {current_engine.upper()}", (195, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 220, 255), 1)

        mode_badge = f"BATAS: {boundary_mode.upper()}"
        cv2.putText(frame, mode_badge, (365, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (240, 180, 80), 1)

        doc_detected = (detected_quad is not None) if boundary_mode == "auto" else (current_edge_density >= min_edge_density)
        if boundary_mode == "auto" and detected_quad is not None:
            doc_label = "DOC: KONTUR [OK]"
            doc_color = (80, 240, 100)
        elif current_edge_density >= min_edge_density:
            doc_label = "DOC: SIAP [OK]"
            doc_color = (80, 240, 100)
        else:
            doc_label = "DOC: MENCARI..."
            doc_color = (140, 140, 150)

        cv2.putText(frame, doc_label, (515, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.44, doc_color, 1)

        res_badge = f"RES: {W}x{H}"
        cv2.putText(frame, res_badge, (685, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (200, 215, 230), 1)

        fps_color = (80, 240, 100) if fps >= 22.0 else (0, 220, 255) if fps >= 14.0 else (60, 60, 240)
        cv2.putText(frame, f"FPS: {fps:.1f}", (835, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.44, fps_color, 1)

        if W >= 1150:
            cv2.putText(frame, sync_badge, (W - 225, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (180, 240, 180), 1)

        # Bottom Status Text
        status_prefix = {
            "ready": "[SIAP]",
            "stabilizing": "[STABILISASI]",
            "scanning": "[MEMINDAI]",
            "success": "[SUKSES]",
            "duplicate": "[DUPLIKAT]",
            "unclear": "[PERIKSA]"
        }.get(status_type, "")

        full_status = f"{status_prefix} {status_message}"
        controls_hint = "[B] Batas | [SPACE] Foto | [R] Res | [E] OCR | [C] Reset | [Q] Keluar"

        if W >= 1280:
            cv2.putText(frame, full_status, (18, H - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.50, theme_color, 2)
            cv2.putText(frame, controls_hint, (W - 620, H - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (160, 160, 170), 1)
        else:
            cv2.putText(frame, full_status, (18, H - 27), cv2.FONT_HERSHEY_SIMPLEX, 0.46, theme_color, 2)
            cv2.putText(frame, controls_hint, (18, H - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (160, 160, 170), 1)

