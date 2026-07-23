"""Testes de tomenotas.transcriber."""

from pathlib import Path

import pytest

from tomenotas.transcriber import Transcriber, TranscriptionError


def test_transcricao_com_sucesso(tmp_path):
    wav = tmp_path / "tmp_recording.wav"
    chamadas = []

    def run_falso(cmd, **kwargs):
        chamadas.append(cmd)
        # o whisper.cpp escreve <out_base>.txt (flag -of + -otxt)
        (tmp_path / "tmp_transcricao.txt").write_text(
            "  olá mundo \n", encoding="utf-8"
        )

    t = Transcriber(
        Path("/w/bin"), Path("/w/model.bin"), language="pt", run=run_falso
    )
    texto = t.transcribe(wav)

    assert texto == "olá mundo"
    assert not (tmp_path / "tmp_transcricao.txt").exists()  # limpou o tmp
    (cmd,) = chamadas
    assert cmd[0] == "/w/bin"
    assert ["-m", "/w/model.bin"] == cmd[1:3]
    assert ["-l", "pt"] == cmd[3:5]
    assert ["-f", str(wav)] == cmd[5:7]
    assert ["-nt", "-otxt", "-of", str(tmp_path / "tmp_transcricao")] == cmd[7:]


def test_whisper_sem_saida_levanta_erro(tmp_path):
    t = Transcriber(
        Path("/w/bin"), Path("/w/model.bin"), run=lambda cmd, **kw: None
    )
    with pytest.raises(TranscriptionError, match="Falha ao transcrever"):
        t.transcribe(tmp_path / "a.wav")


def test_binario_ausente_levanta_erro(tmp_path):
    def run_quebrado(cmd, **kwargs):
        raise FileNotFoundError

    t = Transcriber(Path("/nao/existe"), Path("/w/model.bin"), run=run_quebrado)
    with pytest.raises(TranscriptionError, match="whisper.cpp não encontrado"):
        t.transcribe(tmp_path / "a.wav")
