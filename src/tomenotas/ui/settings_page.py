"""Settings page, embedded in the main window sidebar, split into
sections:

- Atalhos: keyboard shortcut capture, delegated to the (tested)
  ShortcutManager, which writes to gsettings with immediate effect.
- Voz: Piper voice picker, delegated to the (tested) VoiceManager,
  which applies to the Player and persists in config.json.

Glue layer, outside the coverage metric — do not let logic grow here.

Note (Wayland/GNOME): the combination currently registered as a global
shortcut is captured by the shell before it reaches the window — to
change it, press a different combination.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402


class SettingsPage(Gtk.Box):
    """The main window forwards key-press-event to handle_key() while
    this page is visible."""

    def __init__(self, manager, voices, notifier, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                         margin=16)
        self._manager = manager
        self._voices = voices
        self._notifier = notifier
        self._window = window  # parent of the conflict dialogs
        self._capturing = None  # (action_id, button) while capturing
        self._reloading_voices = False  # suppress "changed" during rebuild

        # ---------------- Section: Atalhos ----------------

        self.pack_start(self._section_label("Atalhos"), False, False, 0)

        grid = Gtk.Grid(row_spacing=8, column_spacing=12)
        self.pack_start(grid, False, False, 0)

        self._buttons = {}
        for i, action in enumerate(self._manager.actions.values()):
            label = Gtk.Label(label=action.title, xalign=0)
            button = Gtk.Button(label=self._button_label(action.id))
            button.set_hexpand(True)
            button.connect("clicked", self._on_assign, action.id)
            grid.attach(label, 0, i, 1, 1)
            grid.attach(button, 1, i, 1, 1)
            self._buttons[action.id] = button

        hint = Gtk.Label(label="Clique num atalho e pressione a nova "
                               "combinação de teclas (Esc cancela).")
        hint.get_style_context().add_class("dim-label")
        hint.set_line_wrap(True)
        hint.set_xalign(0)
        self.pack_start(hint, False, False, 0)

        # ---------------- Section: Voz ----------------

        self.pack_start(self._section_label("Voz"), False, False, 8)

        voice_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                            spacing=12)
        voice_row.pack_start(Gtk.Label(label="Voz do Piper", xalign=0),
                             False, False, 0)
        self._voice_combo = Gtk.ComboBoxText()
        self._voice_combo.set_hexpand(True)
        self._voice_combo.connect("changed", self._on_voice_changed)
        voice_row.pack_start(self._voice_combo, True, True, 0)

        help_button = Gtk.Button(label="?")
        help_button.set_tooltip_text("Como baixar mais vozes")
        help_button.connect("clicked", self._on_voice_help)
        voice_row.pack_start(help_button, False, False, 0)
        self.pack_start(voice_row, False, False, 0)

        voice_hint = Gtk.Label(
            label="A troca vale já para a próxima leitura."
        )
        voice_hint.get_style_context().add_class("dim-label")
        voice_hint.set_line_wrap(True)
        voice_hint.set_xalign(0)
        self.pack_start(voice_hint, False, False, 0)

    @staticmethod
    def _section_label(text):
        label = Gtk.Label(xalign=0)
        label.set_markup(f"<b>{text}</b>")
        return label

    # ---------------- Button state ----------------

    def _button_label(self, action_id):
        return (self._manager.get_binding(action_id)
                or self._manager.actions[action_id].default)

    def refresh(self):
        self._cancel_capture()
        for action_id, button in self._buttons.items():
            button.set_label(self._button_label(action_id))
        self._reload_voices()

    # ---------------- Voice picker ----------------

    def _reload_voices(self):
        self._reloading_voices = True  # rebuild is not a user choice
        try:
            self._voice_combo.remove_all()
            for name in self._voices.list_voices():
                self._voice_combo.append(name, name)
            self._voice_combo.set_active_id(self._voices.current_voice())
        finally:
            self._reloading_voices = False

    def _on_voice_help(self, _button):
        dialog = Gtk.MessageDialog(
            transient_for=self._window,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="Como baixar mais vozes",
        )
        # markup: links are clickable (GtkLabel opens them in the browser)
        voices_dir = GLib.markup_escape_text(str(self._voices.voices_dir))
        dialog.format_secondary_markup(
            "1. Abra o catálogo de vozes do Piper:\n"
            '   <a href="https://huggingface.co/rhasspy/piper-voices">'
            "huggingface.co/rhasspy/piper-voices</a>\n"
            "   (amostras de áudio em "
            '<a href="https://rhasspy.github.io/piper-samples/">'
            "rhasspy.github.io/piper-samples</a>)\n\n"
            "2. Baixe os DOIS arquivos da voz desejada:\n"
            "   &lt;voz&gt;.onnx e &lt;voz&gt;.onnx.json\n"
            "   (ex.: pt_BR-edresson-low.onnx e pt_BR-edresson-low.onnx.json)\n\n"
            "3. Coloque os dois arquivos em:\n"
            f"   {voices_dir}\n\n"
            "4. Volte a esta tela e escolha a voz nova no seletor —\n"
            "   a lista é atualizada ao reabrir a tela de Configurações."
        )
        dialog.run()
        dialog.destroy()

    def _on_voice_changed(self, combo):
        if self._reloading_voices:
            return
        name = combo.get_active_id()
        if not name or name == self._voices.current_voice():
            return
        try:
            self._voices.set_voice(name)
        except ValueError as error:
            self._notifier.send("Erro", str(error))
            self._reload_voices()  # back to the voice that actually works
            return
        self._notifier.send("Voz alterada", name)

    # ---------------- Key capture ----------------

    def _on_assign(self, button, action_id):
        self._cancel_capture()
        self._capturing = (action_id, button)
        button.set_label("Pressione o novo atalho...")

    def handle_key(self, event) -> bool:
        """Called by the main window; True = event consumed."""
        if self._capturing is None:
            return False
        action_id, button = self._capturing

        keyval = Gdk.keyval_to_lower(event.keyval)
        if keyval == Gdk.KEY_Escape:
            self._cancel_capture()
            return True

        mods = event.state & Gtk.accelerator_get_default_mod_mask()
        # A modifier key alone (Super, Ctrl...): wait for the rest
        if not Gtk.accelerator_valid(keyval, mods):
            return True

        binding = Gtk.accelerator_name(keyval, mods)
        conflicts = self._manager.list_conflicts(binding,
                                                 ignore_action=action_id)
        if conflicts and not self._confirm_conflict(binding, conflicts):
            return True  # keep capturing: the user tries another combination

        self._manager.set_binding(action_id, binding)
        self._capturing = None
        button.set_label(binding)
        title = self._manager.actions[action_id].title
        self._notifier.send("Atalho atualizado", f"{title}: {binding}")
        return True

    def _confirm_conflict(self, binding, conflicts):
        dialog = Gtk.MessageDialog(
            transient_for=self._window,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"O atalho {binding} já está em uso.",
        )
        dialog.format_secondary_text(
            "Em uso por: " + ", ".join(conflicts) + ".\nUsar mesmo assim?"
        )
        response = dialog.run()
        dialog.destroy()
        return response == Gtk.ResponseType.YES

    def _cancel_capture(self):
        if self._capturing is not None:
            action_id, button = self._capturing
            self._capturing = None
            button.set_label(self._button_label(action_id))
