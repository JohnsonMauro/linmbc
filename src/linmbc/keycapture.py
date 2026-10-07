"""Turn key presses seen by the GUI window into evdev combos (no Qt here).

On KDE Plasma Wayland QKeyEvent.nativeScanCode() is the XKB keycode, i.e. the
evdev code + 8, independent of the keyboard layout (measured 2026-10-07 with
layout us/alt-intl: KEY_1, KEY_Q, KEY_LEFTCTRL, KEY_LEFTSHIFT, KEY_SPACE,
KEY_SEMICOLON). Keys taken by global shortcuts never reach the window, so the
GUI also offers a plain list of key names.
"""

from linmbc.engine import keyboard_keys

SCANCODE_OFFSET = 8
_KEYBOARD_KEYS = frozenset(keyboard_keys())


def evdev_from_scancode(native_scancode: int) -> int | None:
    code = native_scancode - SCANCODE_OFFSET
    return code if code in _KEYBOARD_KEYS else None


class ComboRecorder:
    """Collects keys in press order; the combo is done when every key is released."""

    def __init__(self, max_keys: int = 4) -> None:
        self._max_keys = max_keys
        self._order: list[int] = []
        self._down: set[int] = set()

    def press(self, code: int) -> None:
        if code in self._down:
            return None  # auto-repeat
        self._down.add(code)
        if code not in self._order and len(self._order) < self._max_keys:
            self._order.append(code)
        return None

    def release(self, code: int) -> tuple[int, ...] | None:
        if code not in self._down:
            return None  # pressed before capture started
        self._down.discard(code)
        if self._down or not self._order:
            return None
        combo, self._order = tuple(self._order), []
        return combo
