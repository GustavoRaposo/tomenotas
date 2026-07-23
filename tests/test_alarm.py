"""Tests for tomenotas.app.alarm — the critical-notes periodic alarm.

The explicit requirement: with no active critical note, NO timer may be
running (event-driven arm/disarm, never polling).
"""

from datetime import datetime

from tomenotas.app.alarm import CriticalAlarm
from tomenotas.infra.notes_db import SqliteNoteStore

CLOCK = lambda: datetime(2026, 7, 23, 15, 0, 38)  # noqa: E731


class FakeTimer:
    """Injected scheduler: collects one-shot timers and fires on demand."""

    def __init__(self):
        self.scheduled = []  # list of (seconds, callback)
        self.cancelled = []
        self._next_handle = 0

    def schedule(self, seconds, callback):
        self._next_handle += 1
        self.scheduled.append([self._next_handle, seconds, callback])
        return self._next_handle

    def cancel(self, handle):
        self.cancelled.append(handle)
        self.scheduled = [s for s in self.scheduled if s[0] != handle]

    def fire(self):
        (handle, _, callback) = self.scheduled.pop(0)
        callback()


class FakeNotifier:
    def __init__(self):
        self.messages = []

    def send(self, title, body):
        self.messages.append((title, body))


class FakeSound:
    def __init__(self):
        self.plays = 0

    def play(self):
        self.plays += 1


def make(tmp_path, interval=300):
    store = SqliteNoteStore(tmp_path / "notes.db", tmp_path / "notes",
                            now=CLOCK)
    timer = FakeTimer()
    notifier = FakeNotifier()
    sound = FakeSound()
    alarm = CriticalAlarm(store, notifier, sound,
                          schedule=timer.schedule, cancel=timer.cancel,
                          interval=interval)
    return alarm, store, timer, notifier, sound


def test_no_active_criticals_means_no_timer(tmp_path):
    alarm, store, timer, _, _ = make(tmp_path)
    store.save("nota normal")
    alarm.refresh()
    assert not alarm.armed
    assert timer.scheduled == []  # explicit requirement: zero polling


def test_refresh_arms_once_when_a_critical_exists(tmp_path):
    alarm, store, timer, _, _ = make(tmp_path, interval=120)
    store.save("urgente", critical=True)
    alarm.refresh()
    alarm.refresh()  # idempotent: still a single timer
    assert alarm.armed
    assert len(timer.scheduled) == 1
    assert timer.scheduled[0][1] == 120


def test_fire_notifies_with_sound_and_reschedules(tmp_path):
    alarm, store, timer, notifier, sound = make(tmp_path)
    store.save("pagar aluguel hoje sem falta", critical=True)
    alarm.refresh()

    timer.fire()

    (title, body) = notifier.messages[-1]
    assert title == "Nota crítica"
    assert "pagar aluguel" in body
    assert sound.plays == 1
    assert alarm.armed and len(timer.scheduled) == 1  # next cycle armed


def test_fire_with_many_criticals_mentions_the_count(tmp_path):
    alarm, store, timer, notifier, _ = make(tmp_path)
    store.save("primeira", critical=True)
    store.save("segunda urgência", critical=True)
    alarm.refresh()
    timer.fire()
    (_, body) = notifier.messages[-1]
    assert "2" in body
    assert "segunda urgência" in body  # most recent one previewed


def test_deactivating_the_last_critical_disarms(tmp_path):
    alarm, store, timer, _, _ = make(tmp_path)
    note = store.save("urgente", critical=True)
    alarm.refresh()
    assert alarm.armed

    store.set_critical(note.id, False)
    alarm.refresh()

    assert not alarm.armed
    assert timer.scheduled == []  # timer cancelled, nothing keeps polling


def test_fire_after_criticals_vanished_goes_silent_and_disarms(tmp_path):
    # the timer was armed, but the notes were deactivated without a
    # refresh (e.g. race): firing must not notify and must not reschedule
    alarm, store, timer, notifier, sound = make(tmp_path)
    note = store.save("urgente", critical=True)
    alarm.refresh()
    store.set_critical(note.id, False)

    timer.fire()

    assert notifier.messages == []
    assert sound.plays == 0
    assert not alarm.armed
    assert timer.scheduled == []


def test_set_interval_rearms_a_running_timer(tmp_path):
    alarm, store, timer, _, _ = make(tmp_path, interval=300)
    store.save("urgente", critical=True)
    alarm.refresh()

    alarm.set_interval(60)

    assert len(timer.scheduled) == 1
    assert timer.scheduled[0][1] == 60


def test_set_interval_without_timer_stays_disarmed(tmp_path):
    alarm, _, timer, _, _ = make(tmp_path)
    alarm.set_interval(60)
    assert not alarm.armed
    assert timer.scheduled == []
