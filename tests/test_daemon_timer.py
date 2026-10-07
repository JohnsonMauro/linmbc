import time

import pytest

gi = pytest.importorskip("gi")
dbus = pytest.importorskip("dbus")

from gi.repository import GLib  # noqa: E402

from linmbc.daemon import TapTimer  # noqa: E402


class FakeService:
    def __init__(self, deadlines):
        self.deadlines = list(deadlines)  # absolute monotonic times
        self.ticks = []

    def next_deadline(self):
        return self.deadlines[0] if self.deadlines else None

    def tick(self):
        self.ticks.append(time.monotonic())
        self.deadlines.pop(0)


def run_loop(seconds):
    loop = GLib.MainLoop()
    GLib.timeout_add(int(seconds * 1000), loop.quit)
    loop.run()


def test_timer_fires_each_deadline_in_order_and_stops():
    start = time.monotonic()
    service = FakeService([start + 0.05, start + 0.10, start + 0.15])
    timer = TapTimer(service)
    timer.rearm()
    run_loop(0.4)
    assert len(service.ticks) == 3
    for tick, deadline in zip(service.ticks, [0.05, 0.10, 0.15], strict=True):
        assert tick - start >= deadline - 0.002  # never early
        assert tick - start < deadline + 0.05


def test_rearm_without_deadline_does_nothing_and_clear_cancels():
    service = FakeService([])
    timer = TapTimer(service)
    timer.rearm()
    service.deadlines.append(time.monotonic() + 0.05)
    timer.rearm()
    timer.clear()
    run_loop(0.15)
    assert service.ticks == []
