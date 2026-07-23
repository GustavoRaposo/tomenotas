"""Audio recording control via arecord (ALSA)."""

import signal
import subprocess
from pathlib import Path

from ..domain.errors import RecorderError


class Recorder:
    def __init__(self, audio_tmp: Path, popen=subprocess.Popen):
        self.audio_tmp = audio_tmp
        self._popen = popen
        self._proc = None

    @property
    def is_recording(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        if self.is_recording:
            raise RecorderError("já existe uma gravação em andamento")
        self.audio_tmp.parent.mkdir(parents=True, exist_ok=True)
        # FileNotFoundError (arecord missing) propagates — the caller
        # decides how to inform the user.
        self._proc = self._popen(
            ["arecord", "-f", "cd", "-t", "wav", str(self.audio_tmp)]
        )

    def stop(self, timeout: float = 5) -> None:
        proc = self._proc
        if proc is None:
            raise RecorderError("não há gravação em andamento")
        self._proc = None
        try:
            # SIGINT makes arecord close the .wav properly before exiting
            proc.send_signal(signal.SIGINT)
        except ProcessLookupError:
            return  # the process already died on its own (e.g. mic vanished)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    def abort(self) -> None:
        """Ends any pending recording without transcribing and cleans the tmp."""
        if self.is_recording:
            self.stop()
        self.audio_tmp.unlink(missing_ok=True)
