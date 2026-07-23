"""Núcleo do daemon: máquina de estados idle → recording → transcribing.

Lógica pura e síncrona, sem GTK/D-Bus/threads — tudo de I/O entra por
injeção (recorder, transcriber, notes, notifier), o que torna o módulo
100% testável. A camada de cola (daemon.py) decide o que roda em thread.
"""

from enum import Enum, auto

from .notes import NoteStore
from .transcriber import TranscriptionError


class State(Enum):
    IDLE = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()


class ToggleAction(Enum):
    """O que o toggle fez — a cola usa isso para decidir o próximo passo
    (STOP_REQUESTED → rodar finish_recording() numa thread)."""

    STARTED = auto()
    STOP_REQUESTED = auto()
    BUSY = auto()
    FAILED = auto()


class DaemonCore:
    def __init__(self, recorder, transcriber, notes, notifier):
        self._recorder = recorder
        self._transcriber = transcriber
        self._notes = notes
        self._notifier = notifier
        self.state = State.IDLE

    def toggle(self) -> ToggleAction:
        if self.state is State.IDLE:
            return self._start()
        if self.state is State.RECORDING:
            self.state = State.TRANSCRIBING
            self._notifier.send("Gravação", "Transcrevendo...")
            return ToggleAction.STOP_REQUESTED
        # TRANSCRIBING: ignora o toque até a transcrição anterior acabar
        self._notifier.send(
            "Gravação", "Aguarde: ainda transcrevendo a nota anterior."
        )
        return ToggleAction.BUSY

    def _start(self) -> ToggleAction:
        try:
            self._recorder.start()
        except FileNotFoundError:
            self._notifier.send(
                "Erro", "arecord não encontrado. Instale o pacote alsa-utils."
            )
            return ToggleAction.FAILED
        self.state = State.RECORDING
        self._notifier.send(
            "Gravação", "Gravando... aperte o atalho de novo para parar."
        )
        return ToggleAction.STARTED

    def finish_recording(self) -> None:
        """Para o arecord, transcreve e salva a nota. Síncrono e lento —
        a cola chama isto numa thread para não travar o main loop."""
        try:
            self._recorder.stop()
            texto = self._transcriber.transcribe(self._recorder.audio_tmp)
        except TranscriptionError as erro:
            self._notifier.send("Erro", str(erro))
        else:
            self._notes.save(texto)
            self._notifier.send("Nota criada", NoteStore.preview(texto))
        finally:
            self._recorder.audio_tmp.unlink(missing_ok=True)
            self.state = State.IDLE

    def shutdown(self) -> None:
        """Encerra limpo: aborta gravação pendente sem transcrever."""
        self._recorder.abort()
        self.state = State.IDLE
