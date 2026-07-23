"""Alarm ringtone playback via paplay (best-effort).

The critical-notes alarm plays a short sound with each notification. The
file is configurable (Configurações → Notas críticas); the default is
the freedesktop alarm sound shipped by sound-theme-freedesktop.
"""

import logging
import subprocess
from pathlib import Path

log = logging.getLogger("tomenotas.sound")


class AlarmSound:
    def __init__(self, sound_path: Path, spawn=subprocess.Popen):
        self._path = Path(sound_path)
        self._spawn = spawn

    def set_sound(self, path) -> None:
        self._path = Path(path)

    def play(self) -> None:
        """Fire-and-forget: a broken sound must never break the alarm
        notification it accompanies."""
        try:
            self._spawn(["paplay", str(self._path)])
        except (FileNotFoundError, OSError) as error:
            log.warning("could not play alarm sound %s: %s",
                        self._path, error)
