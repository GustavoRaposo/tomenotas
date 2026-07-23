"""Transcrição de áudio via whisper.cpp (subprocess)."""

import subprocess
from pathlib import Path


class TranscriptionError(Exception):
    pass


class Transcriber:
    def __init__(
        self,
        whisper_bin: Path,
        whisper_model: Path,
        language: str = "pt",
        run=subprocess.run,
    ):
        self._whisper_bin = whisper_bin
        self._whisper_model = whisper_model
        self._language = language
        self._run = run

    def transcribe(self, wav_path: Path) -> str:
        """Transcreve o .wav e devolve o texto. Levanta TranscriptionError
        (com mensagem pronta para o usuário) em qualquer falha."""
        out_base = wav_path.with_name("tmp_transcricao")
        cmd = [
            str(self._whisper_bin),
            "-m", str(self._whisper_model),
            "-l", self._language,
            "-f", str(wav_path),
            "-nt", "-otxt",
            "-of", str(out_base),
        ]
        try:
            self._run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except FileNotFoundError:
            raise TranscriptionError("Binário do whisper.cpp não encontrado.")

        out_file = out_base.with_suffix(".txt")
        if not out_file.exists():
            raise TranscriptionError("Falha ao transcrever o áudio.")

        texto = out_file.read_text(encoding="utf-8", errors="replace").strip()
        out_file.unlink()
        return texto
