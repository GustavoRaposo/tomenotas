"""Daemon states and the state → tray icon/tooltip mapping.

Icon names refer to the SVGs in assets/icons/ (installed by install.sh
into ~/.local/share/tomenotas/icons/). AppIndicator cannot animate
icons, so the "pulse" effect is simulated by alternating between the
strong and the dim variant on every tick (GLib.timeout_add in the glue).
"""

from enum import Enum, auto


class State(Enum):
    IDLE = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()


class ToggleAction(Enum):
    """What the toggle did — the glue uses this to decide the next step
    (STOP_REQUESTED → run finish_recording() in a thread)."""

    STARTED = auto()
    STOP_REQUESTED = auto()
    BUSY = auto()
    FAILED = auto()


# state -> (main icon, dim pulse variant or None, tooltip)
_INFO = {
    State.IDLE: ("tomenotas-idle", None, "Ocioso"),
    State.RECORDING: (
        "tomenotas-recording", "tomenotas-recording-dim", "Gravando...",
    ),
    State.TRANSCRIBING: (
        "tomenotas-transcribing", "tomenotas-transcribing-dim",
        "Transcrevendo...",
    ),
}


def icon(state: State) -> str:
    return _INFO[state][0]


def tooltip(state: State) -> str:
    return _INFO[state][2]


def pulses(state: State) -> bool:
    return _INFO[state][1] is not None


class Pulser:
    """Alternates strong/dim on each call; non-pulsing states reset it."""

    def __init__(self):
        self._dim = False

    def next_icon(self, state: State) -> str:
        main, dim, _ = _INFO[state]
        if dim is None:
            self._dim = False
            return main
        self._dim = not self._dim
        return dim if self._dim else main
