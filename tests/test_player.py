"""Tests for tomenotas.infra.player — TTS synthesis (Piper) + playback
(paplay)."""

from pathlib import Path

import pytest

from tomenotas.domain.errors import PlayerError
from tomenotas.infra.player import Player


class FakePaplay:
    def __init__(self):
        self.finished = False
        self.terminated = False

    def poll(self):
        return 0 if self.finished else None

    def terminate(self):
        self.terminated = True
        self.finished = True

    def wait(self, timeout=None):
        return 0


def make_player(tmp_path, synthesizes=True, piper_missing=False,
                paplay_missing=False, voice_missing=False):
    tts_tmp = tmp_path / "tmp_tts.wav"
    voice = tmp_path / "voz.onnx"
    if not voice_missing:
        voice.write_bytes(b"onnx")
    runs = []
    spawns = []
    paplay = FakePaplay()

    def fake_run(cmd, **kwargs):
        runs.append((cmd, kwargs))
        if piper_missing:
            raise FileNotFoundError
        if synthesizes:
            tts_tmp.write_bytes(b"RIFFdados")

    def fake_popen(cmd):
        spawns.append(cmd)
        if paplay_missing:
            raise FileNotFoundError
        return paplay

    player = Player(
        Path("/p/piper"), voice, tts_tmp,
        run=fake_run, popen=fake_popen,
    )
    return player, runs, spawns, paplay, tts_tmp


def test_play_synthesizes_and_plays(tmp_path):
    player, runs, spawns, _, tts_tmp = make_player(tmp_path)
    player.play("olá mundo")

    (cmd, kwargs) = runs[0]
    assert cmd == ["/p/piper", "--model", str(tmp_path / "voz.onnx"),
                   "--output_file", str(tts_tmp)]
    assert kwargs["input"] == "olá mundo".encode()
    assert spawns == [["paplay", str(tts_tmp)]]
    assert player.is_playing


def test_play_with_empty_text_raises(tmp_path):
    player, runs, _, _, _ = make_player(tmp_path)
    with pytest.raises(PlayerError, match="nota está vazia"):
        player.play("   \n")
    assert runs == []  # never even called piper


def test_missing_piper_raises(tmp_path):
    player, _, _, _, _ = make_player(tmp_path, piper_missing=True)
    with pytest.raises(PlayerError, match="Piper não encontrado"):
        player.play("texto")
    assert not player.is_playing


def test_missing_voice_has_specific_message(tmp_path):
    player, runs, _, _, _ = make_player(tmp_path, voice_missing=True)
    with pytest.raises(PlayerError, match="Voz do Piper não encontrada"):
        player.play("texto")
    assert runs == []  # never even tried to synthesize


def test_synthesis_without_output_raises(tmp_path):
    player, _, _, _, _ = make_player(tmp_path, synthesizes=False)
    with pytest.raises(PlayerError, match="Falha ao sintetizar"):
        player.play("texto")


def test_missing_paplay_raises_and_cleans_tmp(tmp_path):
    player, _, _, _, tts_tmp = make_player(tmp_path, paplay_missing=True)
    with pytest.raises(PlayerError, match="paplay não encontrado"):
        player.play("texto")
    assert not tts_tmp.exists()
    assert not player.is_playing


def test_stop_ends_playback_and_cleans_tmp(tmp_path):
    player, _, _, paplay, tts_tmp = make_player(tmp_path)
    player.play("texto")
    player.stop()
    assert paplay.terminated
    assert not player.is_playing
    assert not tts_tmp.exists()


def test_stop_without_playback_does_not_raise(tmp_path):
    player, _, _, _, _ = make_player(tmp_path)
    player.stop()  # must not raise


def test_play_during_playback_stops_the_previous_one(tmp_path):
    player, _, spawns, paplay, _ = make_player(tmp_path)
    player.play("primeira")
    player.play("segunda")
    assert paplay.terminated  # the first playback was stopped
    assert len(spawns) == 2


def test_is_playing_reflects_end_of_playback(tmp_path):
    player, _, _, paplay, _ = make_player(tmp_path)
    player.play("texto")
    assert player.is_playing
    paplay.finished = True
    assert not player.is_playing
