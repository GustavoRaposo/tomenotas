"""Tests for tomenotas.infra.meeting_recorder — mic + system audio.

Meeting mode (Super+[): mixes the microphone and the computer's output
into a virtual sink via PulseAudio/PipeWire, then records that mix.
"""

import signal
import subprocess

import pytest

from tomenotas.domain.errors import RecorderError
from tomenotas.infra.meeting_recorder import MeetingRecorder


class FakeProc:
    def __init__(self):
        self.signals = []
        self.finished = False
        self.killed = False

    def poll(self):
        return 0 if self.finished else None

    def send_signal(self, sig):
        self.signals.append(sig)

    def wait(self, timeout=None):
        self.finished = True
        return 0

    def kill(self):
        self.killed = True


def make(tmp_path, default_sink="alsa_output.pci.analog-stereo",
         modules_listing=""):
    pactl_calls = []
    capture_calls = []
    ids = iter(["100", "101", "102"])  # load-module returns a module id

    def run(cmd, **kwargs):
        pactl_calls.append(cmd)
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "get-default-sink":
            out = default_sink
        elif sub == "load-module":
            out = next(ids)
        elif cmd[1:4] == ["list", "short", "modules"]:
            out = modules_listing
        else:
            out = ""
        return subprocess.CompletedProcess(cmd, 0, stdout=out + "\n",
                                           stderr="")

    proc = FakeProc()

    def popen(cmd):
        capture_calls.append(cmd)
        return proc

    rec = MeetingRecorder(tmp_path / "tmp_meeting.wav", run=run, popen=popen)
    return rec, pactl_calls, capture_calls, proc


def test_start_sets_up_sink_loopbacks_and_captures_the_mix(tmp_path):
    rec, pactl_calls, capture_calls, _ = make(tmp_path)
    rec.start()

    subs = [c[1] for c in pactl_calls]
    assert subs.count("load-module") == 3  # null-sink + 2 loopbacks
    joined = " ".join(" ".join(c) for c in pactl_calls)
    assert "module-null-sink" in joined
    assert "source=@DEFAULT_SOURCE@" in joined            # microphone
    assert "alsa_output.pci.analog-stereo.monitor" in joined  # system audio
    # the mix (the null sink's monitor) is what gets recorded
    (capture,) = capture_calls
    assert str(tmp_path / "tmp_meeting.wav") in capture
    assert any("tomenotas_meeting.monitor" in a for a in capture)
    assert rec.is_recording


def test_start_twice_raises(tmp_path):
    rec, _, _, _ = make(tmp_path)
    rec.start()
    with pytest.raises(RecorderError):
        rec.start()


def test_stop_ends_capture_and_unloads_modules_in_reverse(tmp_path):
    rec, pactl_calls, _, proc = make(tmp_path)
    rec.start()
    pactl_calls.clear()

    rec.stop()

    assert signal.SIGINT in proc.signals
    unloaded = [c[2] for c in pactl_calls if c[1] == "unload-module"]
    assert unloaded == ["102", "101", "100"]  # reverse of load order
    assert not rec.is_recording


def test_stop_unloads_modules_even_if_capture_never_started(tmp_path):
    # capture binary missing: modules were loaded, must still be freed
    def popen_broken(_cmd):
        raise FileNotFoundError

    rec, pactl_calls, _, _ = make(tmp_path)
    rec._popen = popen_broken
    with pytest.raises(FileNotFoundError):
        rec.start()
    unloaded = [c[2] for c in pactl_calls if c[1] == "unload-module"]
    assert set(unloaded) == {"100", "101", "102"}  # nothing leaked


def test_missing_pactl_raises_and_leaks_nothing(tmp_path):
    def run_broken(cmd, **kwargs):
        raise FileNotFoundError

    rec = MeetingRecorder(tmp_path / "m.wav", run=run_broken,
                          popen=lambda c: FakeProc())
    with pytest.raises(FileNotFoundError):
        rec.start()
    assert not rec.is_recording


def test_abort_stops_and_removes_tmp(tmp_path):
    tmp = tmp_path / "tmp_meeting.wav"
    tmp.write_bytes(b"RIFF")
    rec, pactl_calls, _, proc = make(tmp_path)
    rec.start()
    rec.abort()
    assert signal.SIGINT in proc.signals
    assert not tmp.exists()
    assert not rec.is_recording


def test_stop_tolerates_an_already_dead_capture(tmp_path):
    rec, _, _, proc = make(tmp_path)
    rec.start()

    def dead(_sig):
        raise ProcessLookupError

    proc.send_signal = dead
    rec.stop()  # must not raise
    assert not rec.is_recording


def test_stop_kills_a_capture_that_wont_finish(tmp_path):
    rec, _, _, proc = make(tmp_path)
    rec.start()

    waits = []

    def hang(timeout=None):
        waits.append(timeout)
        if len(waits) == 1:  # only the timed wait hangs; post-kill returns
            raise subprocess.TimeoutExpired(cmd="pw-record", timeout=timeout)
        return 0

    proc.wait = hang
    rec.stop(timeout=0.01)
    assert proc.killed


def test_teardown_tolerates_pactl_vanishing(tmp_path):
    rec, _, _, _ = make(tmp_path)
    rec.start()

    def run_gone(cmd, **kwargs):
        raise FileNotFoundError

    rec._run = run_gone
    rec.stop()  # unload calls now fail, but stop must not raise
    assert not rec.is_recording


def test_cleanup_stale_without_pactl_is_a_noop(tmp_path):
    def run_broken(cmd, **kwargs):
        raise FileNotFoundError

    rec = MeetingRecorder(tmp_path / "m.wav", run=run_broken,
                          popen=lambda c: FakeProc())
    rec.cleanup_stale()  # must not raise


def test_cleanup_stale_unloads_leftover_modules_from_a_crash(tmp_path):
    listing = (
        "50\tmodule-null-sink\tsink_name=tomenotas_meeting\n"
        "51\tmodule-loopback\tsource=@DEFAULT_SOURCE@ sink=tomenotas_meeting\n"
        "52\tmodule-loopback\tsource=x.monitor sink=tomenotas_meeting\n"
        "60\tmodule-something-else\tunrelated\n"
    )
    rec, pactl_calls, _, _ = make(tmp_path, modules_listing=listing)
    rec.cleanup_stale()
    unloaded = [c[2] for c in pactl_calls if c[1] == "unload-module"]
    assert set(unloaded) == {"50", "51", "52"}  # only ours, not module 60
