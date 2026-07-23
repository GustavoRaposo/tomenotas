"""Reads notes aloud: synthesis with Piper + playback with paplay.

Mirrors the old ler.sh flow: text → piper (writes a temporary .wav) →
paplay. Synthesis is synchronous (blocks) — the glue layer runs play()
in a thread to keep the UI responsive, as it does with transcription.
"""

import subprocess
from pathlib import Path

from ..domain.errors import PlayerError


class Player:
    def __init__(
        self,
        piper_bin: Path,
        piper_model: Path,
        tts_tmp: Path,
        run=subprocess.run,
        popen=subprocess.Popen,
    ):
        self._piper_bin = piper_bin
        self._piper_model = piper_model
        self._tts_tmp = tts_tmp
        self._run = run
        self._popen = popen
        self._proc = None

    @property
    def is_playing(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def set_model(self, piper_model: Path) -> None:
        """Switches the Piper voice; takes effect on the next play()."""
        self._piper_model = piper_model

    def play(self, text: str) -> None:
        """Synthesizes the text and starts playback (stopping any
        previous one). Raises PlayerError with a user-ready message."""
        if not text.strip():
            raise PlayerError("A nota está vazia.")
        if not self._piper_model.exists():
            raise PlayerError(
                f"Voz do Piper não encontrada: {self._piper_model}"
            )
        self.stop()

        cmd = [
            str(self._piper_bin),
            "--model", str(self._piper_model),
            "--output_file", str(self._tts_tmp),
        ]
        try:
            self._run(
                cmd,
                input=text.encode(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except FileNotFoundError:
            raise PlayerError("Binário do Piper não encontrado.")

        if not self._tts_tmp.exists():
            raise PlayerError("Falha ao sintetizar o áudio.")

        try:
            self._proc = self._popen(["paplay", str(self._tts_tmp)])
        except FileNotFoundError:
            self._tts_tmp.unlink(missing_ok=True)
            raise PlayerError(
                "paplay não encontrado. Instale o pacote pulseaudio-utils."
            )

    def stop(self) -> None:
        """Stops the current playback (if any) and cleans the temp .wav."""
        if self.is_playing:
            self._proc.terminate()
            self._proc.wait(timeout=3)
        self._proc = None
        self._tts_tmp.unlink(missing_ok=True)
