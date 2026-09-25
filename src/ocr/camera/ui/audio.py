"""Audio feedback utilities for live camera scanning."""

import sys
import threading

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
