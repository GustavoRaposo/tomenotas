"""Camada de cola do daemon: bandeja (AyatanaAppIndicator3), serviço D-Bus
(com.tomenotas.Daemon) e main loop GTK.

Mantida deliberadamente fina e burra: só constrói os componentes e delega
para o DaemonCore (testado). Fica fora da métrica de cobertura (ver
pyproject.toml) e é validada manualmente — ver "Testing changes" no
CLAUDE.md.
"""

import signal
import sys
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import Gio, GLib, Gtk  # noqa: E402
from gi.repository import AyatanaAppIndicator3 as AppIndicator  # noqa: E402

from .config import Config  # noqa: E402
from .core import DaemonCore, ToggleAction  # noqa: E402
from .notes import NoteStore  # noqa: E402
from .notify import Notifier  # noqa: E402
from .player import Player  # noqa: E402
from .recorder import Recorder  # noqa: E402
from .transcriber import Transcriber  # noqa: E402
from .window import NotesWindow  # noqa: E402

BUS_NAME = "com.tomenotas.Daemon"
OBJECT_PATH = "/com/tomenotas/Daemon"

INTROSPECTION_XML = """
<node>
  <interface name="com.tomenotas.Daemon">
    <method name="ToggleRecording"/>
    <method name="ShowWindow"/>
    <method name="Ping">
      <arg type="s" name="reply" direction="out"/>
    </method>
  </interface>
</node>
"""


class TrayDaemon:
    def __init__(self, core: DaemonCore, config: Config, store: NoteStore,
                 player: Player, notifier: Notifier):
        self._core = core
        self._config = config
        self._store = store
        self._player = player
        self._notifier = notifier
        self._window = None  # criada sob demanda no primeiro "Abrir"
        self._setup_indicator()
        self._setup_dbus()

    # ---------------- Bandeja (AppIndicator) ----------------

    def _setup_indicator(self):
        self.indicator = AppIndicator.Indicator.new(
            "tomenotas",
            "audio-input-microphone-symbolic",
            AppIndicator.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.indicator.set_title("Tomenotas")

        menu = Gtk.Menu()

        item_abrir = Gtk.MenuItem(label="Abrir")
        item_abrir.connect("activate", self.on_abrir)
        menu.append(item_abrir)

        item_sair = Gtk.MenuItem(label="Sair")
        item_sair.connect("activate", self.on_sair)
        menu.append(item_sair)

        menu.show_all()
        self.indicator.set_menu(menu)

    def on_abrir(self, _item):
        self.show_window()

    def show_window(self):
        if self._window is None:
            self._window = NotesWindow(self._store, self._player,
                                       self._notifier)
        self._window.refresh()
        self._window.show_all()
        self._window.present()

    def on_sair(self, _item):
        self.quit()

    def quit(self):
        self._core.shutdown()
        self._player.stop()
        Gtk.main_quit()

    # ---------------- D-Bus (com.tomenotas.Daemon) ----------------

    def _setup_dbus(self):
        self._node_info = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION_XML)
        self._owner_id = Gio.bus_own_name(
            Gio.BusType.SESSION,
            BUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            self._on_bus_acquired,
            None,
            self._on_name_lost,
        )

    def _on_bus_acquired(self, connection, _name):
        connection.register_object(
            OBJECT_PATH,
            self._node_info.interfaces[0],
            self._on_method_call,
            None,
            None,
        )

    def _on_name_lost(self, _connection, _name):
        # Outra instância já é dona do nome (ou perdemos a conexão): não faz
        # sentido continuar rodando duplicado.
        print(f"tomenotas-daemon: nome {BUS_NAME} indisponível "
              "(já existe outra instância rodando?)", file=sys.stderr)
        Gtk.main_quit()

    def _on_method_call(self, _conn, _sender, _path, _iface, method,
                        _params, invocation):
        if method == "ToggleRecording":
            self._handle_toggle()
            invocation.return_value(None)
        elif method == "ShowWindow":
            self.show_window()
            invocation.return_value(None)
        elif method == "Ping":
            invocation.return_value(GLib.Variant("(s)", ("pong",)))

    def _handle_toggle(self):
        acao = self._core.toggle()
        if acao is ToggleAction.STOP_REQUESTED:
            # A transcrição é lenta — roda numa thread para não travar o
            # main loop (bandeja e D-Bus continuam respondendo).
            threading.Thread(
                target=self._core.finish_recording, daemon=True
            ).start()


def main():
    config = Config.load()
    notifier = Notifier()
    store = NoteStore(config.notes_dir)
    player = Player(config.piper_bin, config.piper_model, config.tts_tmp)
    core = DaemonCore(
        recorder=Recorder(config.audio_tmp),
        transcriber=Transcriber(
            config.whisper_bin, config.whisper_model, config.language
        ),
        notes=store,
        notifier=notifier,
    )
    app = TrayDaemon(core, config, store, player, notifier)
    # Ctrl+C no terminal encerra limpo (útil ao rodar o daemon na mão)
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    Gtk.main()


if __name__ == "__main__":
    main()
