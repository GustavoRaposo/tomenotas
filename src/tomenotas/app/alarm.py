"""Periodic alarm for critical notes.

Event-driven by explicit requirement: with no active critical note there
is NO timer running — refresh() arms/disarms based on the store, and it
is called on the events that can change the answer (daemon startup, note
saved, critical toggled, note deleted, interval changed). Never polls.

The timer itself is injected as one-shot schedule/cancel callables (the
glue provides GLib.timeout_add_seconds/source_remove), keeping this
module synchronous and fully testable.
"""

import logging

from ..domain.note import preview

log = logging.getLogger("tomenotas.alarm")


class CriticalAlarm:
    def __init__(self, notes, notifier, sound, schedule, cancel,
                 interval: int):
        self._notes = notes
        self._notifier = notifier
        self._sound = sound
        self._schedule = schedule  # (seconds, callback) -> handle
        self._cancel = cancel      # (handle) -> None
        self._interval = int(interval)
        self._handle = None

    @property
    def armed(self) -> bool:
        return self._handle is not None

    def set_interval(self, seconds: int) -> None:
        """Changes the cycle; an armed timer is re-armed with it."""
        self._interval = int(seconds)
        if self.armed:
            self._disarm()
            self._arm()

    def refresh(self) -> None:
        """Arms when there are active criticals, disarms when there are
        none. Idempotent — safe to call after any store mutation."""
        if self._notes.active_criticals():
            if not self.armed:
                self._arm()
        elif self.armed:
            self._disarm()

    def _arm(self) -> None:
        self._handle = self._schedule(self._interval, self._fire)
        log.info("critical alarm armed (every %ds)", self._interval)

    def _disarm(self) -> None:
        handle, self._handle = self._handle, None
        self._cancel(handle)
        log.info("critical alarm disarmed")

    def _fire(self) -> None:
        self._handle = None  # the one-shot timer just consumed itself
        criticals = self._notes.active_criticals()
        if not criticals:
            # deactivated between cycles: go silent, nothing reschedules
            log.info("critical alarm: no active notes, stopping")
            return
        latest = criticals[0]
        if len(criticals) == 1:
            body = f"1 nota crítica ativa: {preview(latest.text)}"
        else:
            body = (f"{len(criticals)} notas críticas ativas. "
                    f"Mais recente: {preview(latest.text)}")
        self._notifier.send("Nota crítica", body)
        self._sound.play()
        self._arm()  # next cycle
