import pytest
from evdev import InputEvent
from evdev import ecodes as e

from linmbc.actions import ActionRunner
from linmbc.engine import KEYBOARD, MOUSE, FrameTranslator, keyboard_keys
from linmbc.profile import Action, Delay, Mode


def ev(etype, code, value, t=100.0):
    sec = int(t)
    return InputEvent(sec, int((t - sec) * 1e6), etype, code, value)


def syn(t=100.0):
    return ev(e.EV_SYN, e.SYN_REPORT, 0, t)


def feed_all(tr, events):
    out = []
    for event in events:
        out += tr.feed(event)
    return out


def test_motion_frame_goes_to_virtual_mouse():
    tr = FrameTranslator(ActionRunner({}))
    out = feed_all(tr, [ev(e.EV_REL, e.REL_X, 5), ev(e.EV_REL, e.REL_Y, -2), syn()])
    assert out == [
        (MOUSE, e.EV_REL, e.REL_X, 5),
        (MOUSE, e.EV_REL, e.REL_Y, -2),
        (MOUSE, e.EV_SYN, e.SYN_REPORT, 0),
    ]


def test_remapped_button_goes_to_virtual_keyboard_with_its_own_syn():
    tr = FrameTranslator(ActionRunner({e.BTN_SIDE: Action((e.KEY_1,))}))
    out = feed_all(
        tr,
        [
            ev(e.EV_MSC, e.MSC_SCAN, 0x90004),
            ev(e.EV_KEY, e.BTN_SIDE, 1),
            ev(e.EV_REL, e.REL_X, 1),
            syn(),
        ],
    )
    assert out == [
        (KEYBOARD, e.EV_KEY, e.KEY_1, 1),
        (MOUSE, e.EV_REL, e.REL_X, 1),
        (KEYBOARD, e.EV_SYN, e.SYN_REPORT, 0),
        (MOUSE, e.EV_SYN, e.SYN_REPORT, 0),
    ]


def test_button_to_button_remap_stays_on_mouse():
    tr = FrameTranslator(ActionRunner({e.BTN_SIDE: Action((e.BTN_MIDDLE,))}))
    out = feed_all(tr, [ev(e.EV_KEY, e.BTN_SIDE, 1), syn()])
    assert out == [(MOUSE, e.EV_KEY, e.BTN_MIDDLE, 1), (MOUSE, e.EV_SYN, e.SYN_REPORT, 0)]


def test_wheel_axes_pass_through_unchanged():
    tr = FrameTranslator(ActionRunner({}))
    out = feed_all(tr, [ev(e.EV_REL, e.REL_WHEEL, 1), ev(e.EV_REL, e.REL_WHEEL_HI_RES, 120), syn()])
    assert out[:2] == [
        (MOUSE, e.EV_REL, e.REL_WHEEL, 1),
        (MOUSE, e.EV_REL, e.REL_WHEEL_HI_RES, 120),
    ]


def test_empty_frame_emits_nothing():
    tr = FrameTranslator(ActionRunner({e.BTN_SIDE: Action((e.KEY_1,))}))
    tr.feed(ev(e.EV_KEY, e.BTN_SIDE, 0))  # release without press: dropped
    assert tr.feed(syn()) == []


def test_button_events_are_reported_with_latency():
    tr = FrameTranslator(ActionRunner({e.BTN_SIDE: Action((e.KEY_1,))}))
    feed_all(tr, [ev(e.EV_KEY, e.BTN_SIDE, 1, t=100.0), syn(t=100.0)])
    (record,) = tr.take_button_records()
    assert record.source == e.BTN_SIDE
    assert record.value == 1
    assert record.output == [(e.KEY_1, 1)]
    assert record.timestamp == 100.0
    assert tr.take_button_records() == []


def test_release_all_flushes_held_keys_as_frames():
    tr = FrameTranslator(ActionRunner({e.BTN_SIDE: Action((e.KEY_1,))}))
    feed_all(tr, [ev(e.EV_KEY, e.BTN_SIDE, 1), ev(e.EV_KEY, e.BTN_LEFT, 1), syn()])
    out = tr.release_all()
    assert (KEYBOARD, e.EV_KEY, e.KEY_1, 0) in out
    assert (MOUSE, e.EV_KEY, e.BTN_LEFT, 0) in out
    assert out[-2:] == [(KEYBOARD, e.EV_SYN, e.SYN_REPORT, 0), (MOUSE, e.EV_SYN, e.SYN_REPORT, 0)]


def test_keyboard_capabilities_exclude_buttons():
    keys = keyboard_keys()
    assert e.KEY_A in keys and e.KEY_LEFTCTRL in keys and e.KEY_F12 in keys
    assert e.BTN_LEFT not in keys and e.KEY_RESERVED not in keys


class FakeInputDevice:
    def __init__(self, path):
        self.path, self.fd = path, 42
        self.grabbed = self.closed = False
        self.batches = []
        self.held = []

    def active_keys(self):
        return list(self.held)

    def grab(self):
        self.grabbed = True

    def ungrab(self):
        self.grabbed = False

    def close(self):
        self.closed = True

    def read(self):
        if not self.batches:
            raise BlockingIOError(11, "Resource temporarily unavailable")
        yield from self.batches.pop(0)


class FakeSink:
    def __init__(self):
        self.written = []

    def write(self, events):
        self.written += events


def make_grab(monkeypatch):
    from linmbc import engine
    from linmbc.devices import MouseNode

    monkeypatch.setattr(engine.evdev, "InputDevice", FakeInputDevice)
    node = MouseNode("/dev/input/event8", "WL MOUSE", "36a7", "a868", frozenset())
    sink = FakeSink()
    return engine.GrabbedMouse(node, ActionRunner({e.BTN_SIDE: Action((e.KEY_1,))}), sink), sink


def test_grab_is_refused_while_a_button_is_held(monkeypatch):
    # The press already reached the compositor through the physical node; if
    # the release is grabbed, the desktop keeps that button down (stuck click).
    from linmbc import engine

    devices = []

    def opened(path):
        device = FakeInputDevice(path)
        device.held = [e.BTN_LEFT]
        devices.append(device)
        return device

    monkeypatch.setattr(engine.evdev, "InputDevice", opened)
    node = engine.MouseNode("/dev/input/event8", "WL MOUSE", "36a7", "a868", frozenset())
    with pytest.raises(engine.ButtonsHeld):
        engine.GrabbedMouse(node, ActionRunner({}), FakeSink())
    assert devices[0].closed and not devices[0].grabbed


def test_pump_with_no_pending_events_is_not_a_lost_device(monkeypatch):
    grab, sink = make_grab(monkeypatch)
    assert grab.pump() == []
    assert sink.written == []


def test_pump_forwards_frames_and_close_releases_held_keys(monkeypatch):
    grab, sink = make_grab(monkeypatch)
    grab._device.batches.append([ev(e.EV_KEY, e.BTN_SIDE, 1), syn()])
    (record,) = grab.pump()
    assert record.output == [(e.KEY_1, 1)]
    grab.close()
    assert (KEYBOARD, e.EV_KEY, e.KEY_1, 0) in sink.written
    assert grab._device.closed and not grab._device.grabbed


def test_timed_taps_come_out_of_tick_as_keyboard_frames():
    now = [0.0]
    action = Action((e.KEY_1,), Mode.ONCE, delay=Delay(80, 80))
    tr = FrameTranslator(ActionRunner({e.BTN_SIDE: action}), clock=lambda: now[0])
    out = feed_all(tr, [ev(e.EV_KEY, e.BTN_SIDE, 1), syn()])
    assert out == [(KEYBOARD, e.EV_KEY, e.KEY_1, 1), (KEYBOARD, e.EV_SYN, e.SYN_REPORT, 0)]
    assert tr.next_deadline() == 0.08
    now[0] = 0.05
    assert tr.tick() == []
    now[0] = 0.08
    assert tr.tick() == [(KEYBOARD, e.EV_KEY, e.KEY_1, 0), (KEYBOARD, e.EV_SYN, e.SYN_REPORT, 0)]
    assert tr.next_deadline() is None


def test_switching_actions_releases_a_running_loop_as_a_frame():
    now = [0.0]
    loop = Action((e.KEY_1,), Mode.TOGGLE, delay=Delay(100, 100))
    tr = FrameTranslator(ActionRunner({e.BTN_SIDE: loop}), clock=lambda: now[0])
    feed_all(tr, [ev(e.EV_KEY, e.BTN_SIDE, 1), syn()])  # loop on, KEY_1 down
    assert tr.set_actions({}) == [
        (KEYBOARD, e.EV_KEY, e.KEY_1, 0),
        (KEYBOARD, e.EV_SYN, e.SYN_REPORT, 0),
    ]
    assert tr.next_deadline() is None
