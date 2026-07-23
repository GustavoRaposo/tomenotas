"""Janela GTK de notas (Fase 2): listar, buscar, tocar e apagar.

Camada de cola como daemon.py: só widgets e delegação para NoteStore /
Player (testados). Fica fora da métrica de cobertura (pyproject.toml) e é
validada manualmente. Não deixe lógica crescer aqui — ponha nos módulos
do núcleo.
"""

import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from .notes import NoteStore  # noqa: E402
from .player import PlayerError  # noqa: E402


class NotesWindow(Gtk.Window):
    def __init__(self, store, player, notifier):
        super().__init__(title="Tomenotas")
        self._store = store
        self._player = player
        self._notifier = notifier
        self._playing_button = None  # botão da nota tocando agora

        self.set_default_size(640, 520)

        header = Gtk.HeaderBar(title="Tomenotas", subtitle="Suas notas de voz")
        header.set_show_close_button(True)
        self.set_titlebar(header)

        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                        margin=12)
        self.add(caixa)

        self._busca = Gtk.SearchEntry(placeholder_text="Buscar nas notas...")
        self._busca.connect(
            "search-changed", lambda *_: self._lista.invalidate_filter()
        )
        caixa.pack_start(self._busca, False, False, 0)

        rolagem = Gtk.ScrolledWindow()
        rolagem.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        caixa.pack_start(rolagem, True, True, 0)

        self._lista = Gtk.ListBox()
        self._lista.set_selection_mode(Gtk.SelectionMode.NONE)
        self._lista.set_filter_func(self._filtrar)
        rolagem.add(self._lista)

        self._vazio = Gtk.Label(label="Nenhuma nota ainda.\n"
                                      "Aperte Super+R para gravar a primeira.")
        self._vazio.set_justify(Gtk.Justification.CENTER)

        # Fechar a janela só esconde — o daemon continua na bandeja
        self.connect("delete-event", self._on_fechar)

    # ---------------- Lista ----------------

    def refresh(self):
        self._parar_reproducao()
        for filho in self._lista.get_children():
            self._lista.remove(filho)

        notas = self._store.list()
        if not notas:
            linha = Gtk.ListBoxRow(selectable=False)
            linha.note = None
            linha.add(self._vazio)
            self._lista.add(linha)
        for nota in notas:
            self._lista.add(self._monta_linha(nota))
        self._lista.show_all()

    def _monta_linha(self, nota):
        linha = Gtk.ListBoxRow(selectable=False)
        linha.note = nota

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
                       margin=6)
        linha.add(hbox)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        titulo = Gtk.Label(label=nota.title, xalign=0)
        titulo.get_style_context().add_class("dim-label")
        previa = Gtk.Label(label=NoteStore.preview(nota.text), xalign=0)
        previa.set_ellipsize(Pango.EllipsizeMode.END)
        vbox.pack_start(titulo, False, False, 0)
        vbox.pack_start(previa, False, False, 0)
        hbox.pack_start(vbox, True, True, 0)

        botao_tocar = Gtk.Button.new_from_icon_name(
            "media-playback-start-symbolic", Gtk.IconSize.BUTTON
        )
        botao_tocar.set_tooltip_text("Tocar esta nota")
        botao_tocar.connect("clicked", self._on_tocar, nota)
        hbox.pack_start(botao_tocar, False, False, 0)

        botao_apagar = Gtk.Button.new_from_icon_name(
            "user-trash-symbolic", Gtk.IconSize.BUTTON
        )
        botao_apagar.set_tooltip_text("Apagar esta nota")
        botao_apagar.connect("clicked", self._on_apagar, nota)
        hbox.pack_start(botao_apagar, False, False, 0)

        return linha

    def _filtrar(self, linha):
        if linha.note is None:  # o placeholder de lista vazia sempre aparece
            return True
        return linha.note.matches(self._busca.get_text())

    # ---------------- Tocar / parar ----------------

    def _on_tocar(self, botao, nota):
        if botao is self._playing_button:
            self._parar_reproducao()
            return
        self._parar_reproducao()
        botao.set_sensitive(False)  # até a síntese terminar
        # A síntese do Piper bloqueia — roda numa thread, como a transcrição
        threading.Thread(
            target=self._tocar_worker, args=(botao, nota), daemon=True
        ).start()

    def _tocar_worker(self, botao, nota):
        try:
            self._player.play(nota.text)
        except PlayerError as erro:
            GLib.idle_add(self._on_erro_reproducao, botao, str(erro))
        else:
            GLib.idle_add(self._on_reproducao_iniciada, botao)

    def _on_erro_reproducao(self, botao, mensagem):
        botao.set_sensitive(True)
        self._notifier.send("Erro", mensagem)
        return False

    def _on_reproducao_iniciada(self, botao):
        botao.set_sensitive(True)
        self._marca_tocando(botao)
        # indicador de "tocando agora": volta a play quando o áudio acabar
        GLib.timeout_add(300, self._verifica_fim)
        return False

    def _verifica_fim(self):
        if self._player.is_playing:
            return True  # continua verificando
        self._desmarca_tocando()
        return False

    def _marca_tocando(self, botao):
        self._playing_button = botao
        imagem = Gtk.Image.new_from_icon_name(
            "media-playback-pause-symbolic", Gtk.IconSize.BUTTON
        )
        botao.set_image(imagem)
        botao.set_tooltip_text("Parar a reprodução")

    def _desmarca_tocando(self):
        if self._playing_button is not None:
            imagem = Gtk.Image.new_from_icon_name(
                "media-playback-start-symbolic", Gtk.IconSize.BUTTON
            )
            self._playing_button.set_image(imagem)
            self._playing_button.set_tooltip_text("Tocar esta nota")
            self._playing_button = None

    def _parar_reproducao(self):
        self._player.stop()
        self._desmarca_tocando()

    # ---------------- Apagar ----------------

    def _on_apagar(self, _botao, nota):
        dialogo = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Apagar a nota {nota.title}?",
        )
        dialogo.format_secondary_text(NoteStore.preview(nota.text))
        resposta = dialogo.run()
        dialogo.destroy()
        if resposta == Gtk.ResponseType.YES:
            self._store.delete(nota.path)
            self.refresh()

    # ---------------- Fechar ----------------

    def _on_fechar(self, *_args):
        self._parar_reproducao()
        self.hide()
        return True  # não destrói: reabrir pela bandeja é instantâneo
