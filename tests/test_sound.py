"""Tests for tomenotas.infra.sound — the alarm ringtone via paplay."""

from pathlib import Path

from tomenotas.infra.sound import AlarmSound


def test_play_spawns_paplay_with_the_sound(tmp_path):
    spawns = []
    sound = AlarmSound(tmp_path / "toque.oga",
                       spawn=lambda cmd: spawns.append(cmd))
    sound.play()
    assert spawns == [["paplay", str(tmp_path / "toque.oga")]]


def test_set_sound_switches_the_file(tmp_path):
    spawns = []
    sound = AlarmSound(tmp_path / "a.oga",
                       spawn=lambda cmd: spawns.append(cmd))
    sound.set_sound(tmp_path / "b.wav")
    sound.play()
    assert spawns == [["paplay", str(tmp_path / "b.wav")]]


def test_missing_paplay_does_not_raise(tmp_path):
    def broken_spawn(_cmd):
        raise FileNotFoundError

    sound = AlarmSound(Path("/x/toque.oga"), spawn=broken_spawn)
    sound.play()  # must not raise — an alarm sound is best-effort
