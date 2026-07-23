"""Teste de fumaça da UI: monta a janela de verdade (GTK) e exercita o
fluxo de abrir o detalhe de uma nota — o caminho que os testes de unidade
não cobrem porque ui/ fica fora da métrica.

Só roda quando há display (local); em ambientes sem GTK/display é pulado.
Este teste existe porque um refactor removeu o atributo `.note` das linhas
e o clique passou a falhar em silêncio.
"""

import os
from pathlib import Path

import pytest

tem_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
gtk_ok = True
try:  # pragma: no cover - depende do ambiente
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk  # noqa: F401
except Exception:  # pragma: no cover
    gtk_ok = False

pytestmark = pytest.mark.skipif(
    not (tem_display and gtk_ok), reason="requer GTK e display"
)


@pytest.fixture
def janela(tmp_path):
    from tomenotas.infra.notes_db import SqliteNoteStore
    from tomenotas.infra.notify import Notifier
    from tomenotas.infra.player import Player
    from tomenotas.infra.shortcuts import ShortcutManager
    from tomenotas.ui.window import NotesWindow

    store = SqliteNoteStore(tmp_path / "notes.db", tmp_path / "notes")
    store.save("nota de teste para o detalhe")
    janela = NotesWindow(
        store,
        Player(Path("/x/piper"), Path("/x/voz.onnx"), tmp_path / "t.wav"),
        Notifier(spawn=lambda cmd, **kw: None),  # sem notificações reais
        ShortcutManager(Path.home() / "bin"),
    )
    janela.refresh()
    # torna os filhos do stack "visíveis" sem mapear a janela na tela
    # (Gtk.Stack não troca para um filho com visible=False)
    janela._stack_notas.show_all()
    yield janela
    janela.destroy()


def test_linhas_carregam_a_nota_e_ativar_abre_o_detalhe(janela):
    (linha,) = janela._lista.get_children()
    assert getattr(linha, "note", None) is not None
    assert linha.get_activatable()

    janela._on_nota_ativada(janela._lista, linha)

    assert janela._stack_notas.get_visible_child_name() == "detalhe"
    assert janela._texto_do_editor() == "nota de teste para o detalhe"


def test_salvar_edicao_persiste_e_volta_para_a_lista(janela):
    (linha,) = janela._lista.get_children()
    janela._on_nota_ativada(janela._lista, linha)
    janela._editor.get_buffer().set_text("texto editado no teste")

    janela._on_salvar_detalhe(None)

    assert janela._stack_notas.get_visible_child_name() == "lista"
    (nota,) = janela._store.list()
    assert nota.text == "texto editado no teste"
