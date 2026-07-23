"""Meeting-mode capture: microphone + computer audio at once.

Same duck-typed interface as Recorder (start/stop/abort/audio_tmp/
is_recording), so DaemonCore treats it interchangeably. It mixes two
sources into a virtual PulseAudio/PipeWire sink and records that mix:

  microphone (@DEFAULT_SOURCE@) ─┐
                                 ├─► null sink "tomenotas_meeting"
  output monitor (<sink>.monitor)┘        │
                                          └─► pw-record .monitor → WAV

The modules are torn down on stop/abort/shutdown; cleanup_stale() (called
on daemon startup) removes any left behind by a previous crash.
"""

import logging
import signal
import subprocess
from pathlib import Path

from ..domain.errors import RecorderError

log = logging.getLogger("tomenotas.meeting_recorder")


class MeetingRecorder:
    SINK_NAME = "tomenotas_meeting"

    def __init__(self, audio_tmp: Path, run=subprocess.run,
                 popen=subprocess.Popen, capture_bin: str = "pw-record"):
        self.audio_tmp = Path(audio_tmp)
        self._run = run
        self._popen = popen
        self._capture_bin = capture_bin
        self._proc = None
        self._modules: list[str] = []  # loaded pactl module ids, in order

    @property
    def is_recording(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _pactl(self, *args: str) -> str:
        result = self._run(
            ["pactl", *args], capture_output=True, text=True, check=False
        )
        return (result.stdout or "").strip()

    def start(self) -> None:
        if self.is_recording:
            raise RecorderError("já existe uma gravação em andamento")
        self.audio_tmp.parent.mkdir(parents=True, exist_ok=True)
        try:
            sink = self._pactl("get-default-sink")
            monitor = f"{sink}.monitor"
            # virtual sink that mixes both sources
            self._modules.append(self._pactl(
                "load-module", "module-null-sink",
                f"sink_name={self.SINK_NAME}",
                "sink_properties=device.description=Tomenotas_Reuniao",
            ))
            # microphone → mix
            self._modules.append(self._pactl(
                "load-module", "module-loopback",
                "source=@DEFAULT_SOURCE@", f"sink={self.SINK_NAME}",
                "latency_msec=30",
            ))
            # computer audio (the default sink's monitor) → mix
            self._modules.append(self._pactl(
                "load-module", "module-loopback",
                f"source={monitor}", f"sink={self.SINK_NAME}",
                "latency_msec=30",
            ))
        except FileNotFoundError:
            self._teardown_modules()  # pactl missing: nothing to leak
            raise
        try:
            self._proc = self._popen([
                self._capture_bin, "--target",
                f"{self.SINK_NAME}.monitor", str(self.audio_tmp),
            ])
        except FileNotFoundError:
            self._teardown_modules()  # free the modules we just loaded
            raise

    def stop(self, timeout: float = 5) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            try:
                proc.send_signal(signal.SIGINT)  # pw-record finalizes the WAV
                proc.wait(timeout=timeout)
            except ProcessLookupError:
                pass
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        self._teardown_modules()

    def abort(self) -> None:
        """Ends any pending capture, frees the modules and drops the tmp."""
        if self.is_recording or self._modules:
            self.stop()
        self.audio_tmp.unlink(missing_ok=True)

    def _teardown_modules(self) -> None:
        for module_id in reversed(self._modules):
            if module_id:
                try:
                    self._pactl("unload-module", module_id)
                except FileNotFoundError:
                    pass
        self._modules = []

    def cleanup_stale(self) -> None:
        """Unloads any tomenotas_meeting modules left by a previous crash
        (the daemon calls this on startup). Best-effort."""
        try:
            listing = self._pactl("list", "short", "modules")
        except FileNotFoundError:
            return
        for line in listing.splitlines():
            if self.SINK_NAME not in line:
                continue
            module_id = line.split("\t", 1)[0].strip()
            if module_id:
                self._pactl("unload-module", module_id)
                log.info("removed stale meeting module %s", module_id)
