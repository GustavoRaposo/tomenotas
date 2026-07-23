"""Tomenotas configuration.

Replaces the old sed-patching done by install.sh: paths come from
~/.config/tomenotas/config.json (written by the installer), with
overrides via environment variables (TOMENOTAS_*) — handy in tests and
debugging.
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("tomenotas.config")

CONFIG_PATH = Path("~/.config/tomenotas/config.json").expanduser()


@dataclass(frozen=True)
class Config:
    whisper_bin: Path = Path.home() / "whisper.cpp/build/bin/whisper-cli"
    whisper_model: Path = Path.home() / "whisper.cpp/models/ggml-medium.bin"
    piper_bin: Path = Path.home() / "piper/piper"
    piper_model: Path = Path.home() / "piper/pt_BR-faber-medium.onnx"
    base_dir: Path = Path.home() / ".local/share/tomenotas"
    bin_dir: Path = Path.home() / "bin"
    language: str = "pt"

    @property
    def notes_dir(self) -> Path:
        return self.base_dir / "notes"

    @property
    def audio_tmp(self) -> Path:
        return self.base_dir / "tmp_recording.wav"

    @property
    def tts_tmp(self) -> Path:
        return self.base_dir / "tmp_tts.wav"

    @property
    def icons_dir(self) -> Path:
        return self.base_dir / "icons"

    @property
    def db_path(self) -> Path:
        return self.base_dir / "notes.db"

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        """Loads the config from json (if present), with env var overrides.

        An invalid json does not take the daemon down: it warns and falls
        back to the defaults (the user can still record).
        """
        path = path or CONFIG_PATH
        data: dict = {}
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                log.warning("invalid config at %s, using defaults", path)
                data = {}

        default = cls()

        def path_for(key: str, env_var: str, default_value: Path) -> Path:
            raw = os.environ.get(env_var) or data.get(key)
            return Path(raw).expanduser() if raw else default_value

        return cls(
            whisper_bin=path_for(
                "whisper_bin", "TOMENOTAS_WHISPER_BIN", default.whisper_bin
            ),
            whisper_model=path_for(
                "whisper_model", "TOMENOTAS_WHISPER_MODEL", default.whisper_model
            ),
            piper_bin=path_for("piper_bin", "TOMENOTAS_PIPER_BIN", default.piper_bin),
            piper_model=path_for(
                "piper_model", "TOMENOTAS_PIPER_MODEL", default.piper_model
            ),
            base_dir=path_for("base_dir", "TOMENOTAS_BASE_DIR", default.base_dir),
            bin_dir=path_for("bin_dir", "TOMENOTAS_BIN_DIR", default.bin_dir),
            language=os.environ.get("TOMENOTAS_LANGUAGE")
            or data.get("language")
            or default.language,
        )
