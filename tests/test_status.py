"""Tests for tomenotas.domain.state — state → icon/tooltip mapping and pulse."""

from tomenotas.domain.state import Pulser, State, icon, pulses, tooltip


def test_icons_per_state():
    assert icon(State.IDLE) == "tomenotas-idle"
    assert icon(State.RECORDING) == "tomenotas-recording"
    assert icon(State.TRANSCRIBING) == "tomenotas-transcribing"


def test_tooltips_per_state():
    assert tooltip(State.IDLE) == "Ocioso"
    assert tooltip(State.RECORDING) == "Gravando..."
    assert tooltip(State.TRANSCRIBING) == "Transcrevendo..."


def test_pulses_only_while_active():
    assert not pulses(State.IDLE)
    assert pulses(State.RECORDING)
    assert pulses(State.TRANSCRIBING)


def test_pulser_alternates_between_strong_and_dim():
    p = Pulser()
    assert p.next_icon(State.RECORDING) == "tomenotas-recording-dim"
    assert p.next_icon(State.RECORDING) == "tomenotas-recording"
    assert p.next_icon(State.RECORDING) == "tomenotas-recording-dim"


def test_pulser_resets_on_non_pulsing_state_and_returns_the_main_icon():
    p = Pulser()
    p.next_icon(State.TRANSCRIBING)  # enters the dim variant
    assert p.next_icon(State.IDLE) == "tomenotas-idle"
    # reset: the next alternation starts again at the dim variant
    assert p.next_icon(State.RECORDING) == "tomenotas-recording-dim"
