from evdev import ecodes as e

from linmbc.keycapture import ComboRecorder, evdev_from_scancode

# Measured on KDE Plasma Wayland (2026-10-07): nativeScanCode() = evdev code + 8.


def test_scancode_offset_matches_measured_keys():
    assert evdev_from_scancode(10) == e.KEY_1
    assert evdev_from_scancode(37) == e.KEY_LEFTCTRL
    assert evdev_from_scancode(47) == e.KEY_SEMICOLON


def test_scancode_outside_keyboard_range_is_rejected():
    assert evdev_from_scancode(0) is None
    assert evdev_from_scancode(8 + e.BTN_LEFT) is None


def test_single_key_finishes_on_release():
    r = ComboRecorder()
    assert r.press(e.KEY_1) is None
    assert r.release(e.KEY_1) == (e.KEY_1,)


def test_combo_keeps_press_order_and_finishes_when_all_released():
    r = ComboRecorder()
    r.press(e.KEY_LEFTCTRL)
    r.press(e.KEY_2)
    assert r.release(e.KEY_2) is None
    assert r.release(e.KEY_LEFTCTRL) == (e.KEY_LEFTCTRL, e.KEY_2)


def test_repeated_press_is_ignored_and_recorder_resets():
    r = ComboRecorder()
    r.press(e.KEY_A)
    r.press(e.KEY_A)
    assert r.release(e.KEY_A) == (e.KEY_A,)
    r.press(e.KEY_B)
    assert r.release(e.KEY_B) == (e.KEY_B,)


def test_release_of_key_pressed_before_capture_is_ignored():
    r = ComboRecorder()
    assert r.release(e.KEY_ENTER) is None
    r.press(e.KEY_1)
    assert r.release(e.KEY_1) == (e.KEY_1,)


def test_combo_is_capped():
    r = ComboRecorder(max_keys=2)
    for key in (e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT, e.KEY_A):
        r.press(key)
    for key in (e.KEY_A, e.KEY_LEFTSHIFT):
        r.release(key)
    assert r.release(e.KEY_LEFTCTRL) == (e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT)
