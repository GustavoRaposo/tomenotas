"""Tests for tomenotas.infra.recorder."""

import signal
import subprocess

import pytest

from tomenotas.domain.errors import RecorderError
from tomenotas.infra.recorder import Recorder


class FakeProcess:
    """Simulates an arecord Popen."""

    def __init__(self, hangs_on_wait=False, already_dead=False):
        self.signals = []
        self.killed = False
        self.finished = False
        self._hangs_on_wait = hangs_on_wait
        self._already_dead = already_dead
        self._waits = 0

    def poll(self):
        return 0 if self.finished else None

    def send_signal(self, sig):
        if self._already_dead:
            raise ProcessLookupError
        self.signals.append(sig)

    def wait(self, timeout=None):
        self._waits += 1
        # hangs only on the first wait (the one with a timeout); after
        # kill, it returns
        if self._hangs_on_wait and self._waits == 1:
            raise subprocess.TimeoutExpired(cmd="arecord", timeout=timeout)
        self.finished = True
        return 0

    def kill(self):
        self.killed = True


def factory(proc, calls=None):
    def popen(cmd):
        if calls is not None:
            calls.append(cmd)
        return proc
    return popen


def test_start_invokes_arecord_and_creates_directory(tmp_path):
    tmp = tmp_path / "sub" / "tmp_recording.wav"
    calls = []
    recorder = Recorder(tmp, popen=factory(FakeProcess(), calls))
    recorder.start()
    assert calls == [["arecord", "-f", "cd", "-t", "wav", str(tmp)]]
    assert tmp.parent.is_dir()
    assert recorder.is_recording


def test_double_start_raises(tmp_path):
    recorder = Recorder(tmp_path / "a.wav", popen=factory(FakeProcess()))
    recorder.start()
    with pytest.raises(RecorderError):
        recorder.start()


def test_start_propagates_missing_arecord(tmp_path):
    def broken_popen(_cmd):
        raise FileNotFoundError

    recorder = Recorder(tmp_path / "a.wav", popen=broken_popen)
    with pytest.raises(FileNotFoundError):
        recorder.start()
    assert not recorder.is_recording


def test_stop_sends_sigint_and_waits(tmp_path):
    proc = FakeProcess()
    recorder = Recorder(tmp_path / "a.wav", popen=factory(proc))
    recorder.start()
    recorder.stop()
    assert proc.signals == [signal.SIGINT]
    assert proc.finished
    assert not recorder.is_recording


def test_stop_without_recording_raises(tmp_path):
    recorder = Recorder(tmp_path / "a.wav", popen=factory(FakeProcess()))
    with pytest.raises(RecorderError):
        recorder.stop()


def test_stop_kills_process_that_wont_exit(tmp_path):
    proc = FakeProcess(hangs_on_wait=True)
    recorder = Recorder(tmp_path / "a.wav", popen=factory(proc))
    recorder.start()
    recorder.stop(timeout=0.01)
    assert proc.killed


def test_stop_tolerates_already_dead_process(tmp_path):
    proc = FakeProcess(already_dead=True)
    recorder = Recorder(tmp_path / "a.wav", popen=factory(proc))
    recorder.start()
    recorder.stop()  # must not raise
    assert not recorder.is_recording


def test_abort_stops_recording_and_removes_tmp(tmp_path):
    tmp = tmp_path / "a.wav"
    tmp.write_bytes(b"RIFF")
    proc = FakeProcess()
    recorder = Recorder(tmp, popen=factory(proc))
    recorder.start()
    recorder.abort()
    assert proc.signals == [signal.SIGINT]
    assert not tmp.exists()


def test_abort_without_recording_only_cleans_tmp(tmp_path):
    tmp = tmp_path / "a.wav"
    tmp.write_bytes(b"RIFF")
    recorder = Recorder(tmp, popen=factory(FakeProcess()))
    recorder.abort()  # must not raise
    assert not tmp.exists()
