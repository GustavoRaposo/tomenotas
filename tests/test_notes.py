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


def test_list_vazio_sem_diretorio(tmp_path):
    store = NoteStore(tmp_path / "nao_existe")
    assert store.list() == []


def test_list_ordena_mais_recente_primeiro(tmp_path):
    store = NoteStore(tmp_path / "notes")
    store.notes_dir.mkdir(parents=True)
    (store.notes_dir / "2026-07-20_10-00-00.txt").write_text("antiga")
    (store.notes_dir / "2026-07-22_09-00-00.txt").write_text("do meio")
    (store.notes_dir / "2026-07-22_15-00-38.txt").write_text("recente")
    (store.notes_dir / "alheio.wav").write_bytes(b"x")  # ignora não-.txt

    notas = store.list()
    assert [n.text for n in notas] == ["recente", "do meio", "antiga"]
    assert notas[0].title == "2026-07-22_15-00-38"


def test_delete_remove_a_nota(tmp_path):
    store = NoteStore(tmp_path / "notes", now=RELOGIO_FIXO)
    caminho = store.save("descartável")
    store.delete(caminho)
    assert store.list() == []


def test_delete_de_nota_inexistente_nao_levanta_erro(tmp_path):
    store = NoteStore(tmp_path / "notes")
    store.delete(tmp_path / "notes" / "nada.txt")  # não deve levantar


def test_matches_busca_no_texto_sem_diferenciar_caixa(tmp_path):
    store = NoteStore(tmp_path / "notes", now=RELOGIO_FIXO)
    caminho = store.save("Comprar PÃO na padaria")
    (nota,) = store.list()
    assert nota.matches("pão")
    assert nota.matches("PADARIA")
    assert nota.matches("")  # consulta vazia casa com tudo
    assert nota.matches("2026-07-22")  # busca também no nome/timestamp
    assert not nota.matches("leite")
    assert caminho == nota.path
