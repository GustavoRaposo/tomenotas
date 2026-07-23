"""Testes de tomenotas.notes."""

from datetime import datetime

from tomenotas.notes import NoteStore


RELOGIO_FIXO = lambda: datetime(2026, 7, 22, 15, 0, 38)  # noqa: E731


def test_save_cria_arquivo_com_timestamp(tmp_path):
    store = NoteStore(tmp_path / "notes", now=RELOGIO_FIXO)
    caminho = store.save("minha nota")
    assert caminho == tmp_path / "notes" / "2026-07-22_15-00-38.txt"
    assert caminho.read_text(encoding="utf-8") == "minha nota"


def test_save_nao_sobrescreve_no_mesmo_segundo(tmp_path):
    store = NoteStore(tmp_path / "notes", now=RELOGIO_FIXO)
    primeiro = store.save("primeira")
    segundo = store.save("segunda")
    terceiro = store.save("terceira")
    assert primeiro.name == "2026-07-22_15-00-38.txt"
    assert segundo.name == "2026-07-22_15-00-38-2.txt"
    assert terceiro.name == "2026-07-22_15-00-38-3.txt"
    assert primeiro.read_text(encoding="utf-8") == "primeira"


def test_preview_trunca_em_60_caracteres():
    assert NoteStore.preview("a" * 100) == "a" * 60
    assert NoteStore.preview("curta") == "curta"
