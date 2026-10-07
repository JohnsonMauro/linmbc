"""Device I/O: grab physical mice, translate frames, write to two uinput devices.

FrameTranslator is pure (unit-tested). UInputSink and GrabbedMouse touch real
devices and are exercised by hand/in game.
"""

import contextlib
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import evdev
from evdev import ecodes

from linmbc.actions import ActionRunner
from linmbc.devices import MouseNode
from linmbc.keys import is_button
from linmbc.profile import Action
from linmbc.remap import Output

MOUSE, KEYBOARD = "mouse", "keyboard"
SYN_ORDER = (KEYBOARD, MOUSE)
OutEvent = tuple[str, int, int, int]  # (target, type, code, value)

# Static virtual-mouse capabilities, so hotplugged mice never need a new device.
MOUSE_BUTTONS = list(range(ecodes.BTN_LEFT, ecodes.BTN_TASK + 1))
MOUSE_AXES = [
    ecodes.REL_X,
    ecodes.REL_Y,
    ecodes.REL_HWHEEL,
    ecodes.REL_WHEEL,
    ecodes.REL_WHEEL_HI_RES,
    ecodes.REL_HWHEEL_HI_RES,
]


def keyboard_keys() -> list[int]:
    """Every keyboard key code python-evdev knows, excluding buttons."""
    return sorted(code for code in ecodes.KEY if 0 < code < ecodes.KEY_MAX and not is_button(code))


@dataclass(frozen=True)
class ButtonRecord:
    source: int
    value: int
    output: Output
    timestamp: float  # kernel event time


class FrameTranslator:
    """Buffers one evdev frame, runs button actions, and emits a SYN per touched target."""

    def __init__(self, runner: ActionRunner, clock: Callable[[], float] = time.monotonic) -> None:
        self.runner = runner
        self._clock = clock
        self._pending: list[OutEvent] = []
        self._records: list[ButtonRecord] = []

    def feed(self, event: evdev.InputEvent) -> list[OutEvent]:
        if event.type == ecodes.EV_SYN:
            if event.code == ecodes.SYN_REPORT:
                return self._flush()
            return []
        if event.type == ecodes.EV_MSC:
            return []  # scan codes would describe the original button, not the output
        if event.type == ecodes.EV_KEY:
            output = self.runner.key(event.code, event.value, self._clock())
            self._pending += [_route(code, value) for code, value in output]
            if event.value in (0, 1):
                self._records.append(
                    ButtonRecord(event.code, event.value, output, event.timestamp())
                )
            return []
        self._pending.append((MOUSE, event.type, event.code, event.value))
        return []

    def tick(self) -> list[OutEvent]:
        """Timed taps (once/toggle/repeat) that are due now, as their own frames."""
        self._pending += [_route(c, v) for c, v in self.runner.tick(self._clock())]
        return self._flush()

    def next_deadline(self) -> float | None:
        return self.runner.next_deadline()

    def set_actions(self, actions: Mapping[int, Action]) -> list[OutEvent]:
        """Swap the profile; keys of loops that stop are released in this frame."""
        released = self.runner.set_actions(actions, self._clock())
        self._pending += [_route(c, v) for c, v in released]
        return self._flush()

    def release_all(self) -> list[OutEvent]:
        self._pending += [_route(code, value) for code, value in self.runner.release_all()]
        return self._flush()

    def take_button_records(self) -> list[ButtonRecord]:
        records, self._records = self._records, []
        return records

    def _flush(self) -> list[OutEvent]:
        out, self._pending = self._pending, []
        touched = {target for target, *_ in out}
        out += [(t, ecodes.EV_SYN, ecodes.SYN_REPORT, 0) for t in SYN_ORDER if t in touched]
        return out


def _route(code: int, value: int) -> OutEvent:
    target = MOUSE if is_button(code) else KEYBOARD
    return (target, ecodes.EV_KEY, code, value)


def latency_seconds(kernel_ts: float) -> float:
    """Evdev stamps events with REALTIME or MONOTONIC; the right clock is the close one."""
    real = time.time() - kernel_ts
    mono = time.clock_gettime(time.CLOCK_MONOTONIC) - kernel_ts
    return min(real, mono, key=abs)


class UInputSink:
    """The virtual mouse and keyboard every grabbed mouse writes into."""

    def __init__(self) -> None:
        # Note: UInput() blocks ~2 s when the new node is not readable by us
        # (python-evdev retries opening it); writing works regardless.
        self._devices = {
            MOUSE: evdev.UInput(
                events={ecodes.EV_KEY: MOUSE_BUTTONS, ecodes.EV_REL: MOUSE_AXES},
                name="LinMBC virtual mouse",
            ),
            KEYBOARD: evdev.UInput(
                events={ecodes.EV_KEY: keyboard_keys()}, name="LinMBC virtual keyboard"
            ),
        }

    def write(self, events: list[OutEvent]) -> None:
        for target, etype, code, value in events:
            self._devices[target].write(etype, code, value)

    def close(self) -> None:
        for device in self._devices.values():
            device.close()


class GrabbedMouse:
    """One physical mouse, grabbed exclusively; its frames go through its translator."""

    def __init__(self, node: MouseNode, runner: ActionRunner, sink: UInputSink) -> None:
        self.node = node
        self.translator = FrameTranslator(runner)
        self._sink = sink
        self._device = evdev.InputDevice(node.path)
        try:
            self._device.grab()
        except OSError:
            self._device.close()
            raise

    def fileno(self) -> int:
        return self._device.fd

    def pump(self) -> list[ButtonRecord]:
        """Forward every pending event; OSError (e.g. unplugged) propagates.

        The fd is O_NONBLOCK: read() raises BlockingIOError (an OSError) when
        nothing is pending, which must not look like a lost device.
        """
        with contextlib.suppress(BlockingIOError):
            for event in self._device.read():
                self._sink.write(self.translator.feed(event))
        return self.translator.take_button_records()

    def tick(self) -> None:
        self._sink.write(self.translator.tick())

    def next_deadline(self) -> float | None:
        return self.translator.next_deadline()

    def set_actions(self, actions: Mapping[int, Action]) -> None:
        self._sink.write(self.translator.set_actions(actions))

    def close(self) -> None:
        """Release held outputs, then the grab. Safe to call on an unplugged device."""
        try:
            self._sink.write(self.translator.release_all())
        finally:
            with contextlib.suppress(OSError):
                self._device.ungrab()
            self._device.close()
