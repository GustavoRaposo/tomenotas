"""Tests for tomenotas.infra.config."""

import json
from pathlib import Path

from tomenotas.infra.config import Config


def test_defaults_derive_from_base_dir():
    cfg = Config(base_dir=Path("/x/dados"))
    assert cfg.notes_dir == Path("/x/dados/notes")
    assert cfg.audio_tmp == Path("/x/dados/tmp_recording.wav")
    assert cfg.tts_tmp == Path("/x/dados/tmp_tts.wav")
    assert cfg.icons_dir == Path("/x/dados/icons")
    assert cfg.db_path == Path("/x/dados/notes.db")
    assert cfg.language == "pt"


def test_piper_defaults():
    cfg = Config()
    assert cfg.piper_bin == Path.home() / "piper/piper"
    assert cfg.piper_model == Path.home() / "piper/pt_BR-faber-medium.onnx"


def test_bin_dir_default_and_override(tmp_path, monkeypatch):
    assert Config().bin_dir == Path.home() / "bin"
    monkeypatch.setenv("TOMENOTAS_BIN_DIR", "/opt/bin")
    assert Config.load(tmp_path / "nada.json").bin_dir == Path("/opt/bin")


def test_load_without_file_uses_defaults(tmp_path):
    cfg = Config.load(tmp_path / "inexistente.json")
    assert cfg == Config()


def test_load_reads_paths_from_json(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({
        "whisper_bin": "/opt/whisper/main",
        "whisper_model": "/opt/whisper/ggml-small.bin",
        "piper_bin": "/opt/piper/piper",
        "piper_model": "/opt/piper/voz.onnx",
        "base_dir": str(tmp_path / "dados"),
        "language": "en",
    }))
    cfg = Config.load(config_file)
    assert cfg.whisper_bin == Path("/opt/whisper/main")
    assert cfg.whisper_model == Path("/opt/whisper/ggml-small.bin")
    assert cfg.piper_bin == Path("/opt/piper/piper")
    assert cfg.piper_model == Path("/opt/piper/voz.onnx")
    assert cfg.base_dir == tmp_path / "dados"
    assert cfg.language == "en"


def test_load_expands_tilde_in_json(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"whisper_bin": "~/w/main"}))
    cfg = Config.load(config_file)
    assert cfg.whisper_bin == Path.home() / "w/main"


def test_env_takes_precedence_over_json(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({
        "whisper_bin": "/do/json",
        "language": "en",
    }))
    monkeypatch.setenv("TOMENOTAS_WHISPER_BIN", "/do/env")
    monkeypatch.setenv("TOMENOTAS_PIPER_BIN", "/do/env/piper")
    monkeypatch.setenv("TOMENOTAS_LANGUAGE", "es")
    cfg = Config.load(config_file)
    assert cfg.whisper_bin == Path("/do/env")
    assert cfg.piper_bin == Path("/do/env/piper")
    assert cfg.language == "es"


def test_invalid_json_warns_and_uses_defaults(tmp_path, caplog):
    config_file = tmp_path / "config.json"
    config_file.write_text("{ nada a ver")
    cfg = Config.load(config_file)
    assert cfg == Config()
    assert "invalid config" in caplog.text
