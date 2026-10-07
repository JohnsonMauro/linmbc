"""Profile actions over time: hold, once, toggle loop, repeat N, with (random) delays.

Pure state machine: the caller passes `now` (seconds, monotonic) and asks for
`next_deadline()`; the daemon arms a timer for it and calls `tick()`. Tests use
plain numbers for time and a seeded RNG.
"""

import random
from collections.abc import Mapping
from dataclasses import dataclass

from linmbc.profile import Action, Mode
from linmbc.remap import DOWN, UP, Output, Remapper

TAP_HOLD_S = 0.03  # how long a repeated tap stays down (capped at half the interval)


@dataclass
class _Job:
    action: Action
    remaining: int | None  # None = until stopped (toggle)
    next_at: float
    pressed: bool = False
    tap_started: float = 0.0
    interval: float = 0.0


class ActionRunner:
    def __init__(self, actions: Mapping[int, Action], rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()
        self._hold = Remapper({})
        self._actions: dict[int, Action] = {}
        self._jobs: dict[int, _Job] = {}
        self.set_actions(actions, now=0.0)

    def set_actions(self, actions: Mapping[int, Action], now: float) -> Output:
        """Swap the profile; running loops stop. Held hold-buttons release on their own."""
        out = self._stop_all_jobs()
        self._actions = dict(actions)
        self._hold.set_mapping(
            {code: a.keys for code, a in self._actions.items() if a.mode is Mode.HOLD}
        )
        return out

    def key(self, code: int, value: int, now: float) -> Output:
        action = self._actions.get(code)
        timed = action is not None and action.mode is not Mode.HOLD
        if not timed or (value == UP and self._hold.is_held(code)):
            return self._hold.key(code, value)
        if value != DOWN:
            return []  # timed modes act on the press only
        if code in self._jobs:
            if action.mode is Mode.ONCE:
                return []  # tap still running
            return self._stop_job(code)  # toggle off / cancel repeat
        remaining = None if action.mode is Mode.TOGGLE else 1
        if action.mode is Mode.REPEAT:
            remaining = action.count
        job = _Job(action, remaining, next_at=now)
        self._jobs[code] = job
        return self._step(code, job, now)

    def tick(self, now: float) -> Output:
        out: Output = []
        for code in list(self._jobs):
            job = self._jobs.get(code)
            while job is not None and job.next_at <= now:
                out += self._step(code, job, job.next_at)
                job = self._jobs.get(code)
        return out

    def next_deadline(self) -> float | None:
        return min((job.next_at for job in self._jobs.values()), default=None)

    def release_all(self) -> Output:
        return self._stop_all_jobs() + self._hold.release_all()

    # --- internals ---------------------------------------------------------

    def _step(self, code: int, job: _Job, at: float) -> Output:
        action = job.action
        if not job.pressed:
            job.pressed = True
            job.tap_started = at
            if action.mode is Mode.ONCE:
                job.next_at = at + action.delay.sample(self._rng)
            else:
                job.interval = action.delay.sample(self._rng)
                job.next_at = at + min(TAP_HOLD_S, job.interval / 2)
            return self._hold.acquire(action.keys)
        job.pressed = False
        out = self._hold.release(action.keys)
        if job.remaining is not None:
            job.remaining -= 1
            if job.remaining <= 0:
                del self._jobs[code]
                return out
        job.next_at = job.tap_started + job.interval
        return out

    def _stop_job(self, code: int) -> Output:
        job = self._jobs.pop(code)
        return self._hold.release(job.action.keys) if job.pressed else []

    def _stop_all_jobs(self) -> Output:
        out: Output = []
        for code in list(self._jobs):
            out += self._stop_job(code)
        return out
