"""Settings page (keyboard shortcuts), embedded in the main window
sidebar.

Glue layer: key capture with GTK and delegation to the (tested)
ShortcutManager, which writes to gsettings with immediate effect.
Outside the coverage metric — do not let logic grow here.

Note (Wayland/GNOME): the combination currently registered as a global
shortcut is captured by the shell before it reaches the window — to
change it, press a different combination.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402


class SettingsPage(Gtk.Box):
    """The main window forwards key-press-event to handle_key() while
    this page is visible."""

    def __init__(self, manager, notifier, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                         margin=16)
        self._manager = manager
        self._notifier = notifier
        self._window = window  # parent of the conflict dialogs
        self._capturing = None  # (action_id, button) while capturing

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
        self.pack_start(hint, False, False, 0)

    # ---------------- Button state ----------------

    def _button_label(self, action_id):
        return (self._manager.get_binding(action_id)
                or self._manager.actions[action_id].default)

    def refresh(self):
        self._cancel_capture()
        for action_id, button in self._buttons.items():
            button.set_label(self._button_label(action_id))

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
