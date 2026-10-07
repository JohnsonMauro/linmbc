"""Key and button names <-> evdev codes, and "KEY_A+KEY_B" combos."""

from evdev import ecodes

COMBO_SEPARATOR = "+"


def code_of(name: str) -> int:
    """Return the code of a KEY_* or BTN_* name; ValueError for anything else."""
    if not name.startswith(("KEY_", "BTN_")) or name not in ecodes.ecodes:
        raise ValueError(f"unknown key or button name: {name!r}")
    return ecodes.ecodes[name]


def name_of(code: int) -> str:
    """Return the canonical name of a key/button code (first alias when several)."""
    name = ecodes.BTN.get(code) or ecodes.KEY.get(code)
    if name is None:
        raise ValueError(f"unknown key or button code: {code}")
    return name if isinstance(name, str) else name[0]


def is_button(code: int) -> bool:
    """True for mouse/gamepad buttons (BTN_*), False for keyboard keys."""
    return code in ecodes.BTN


def parse_combo(text: str) -> tuple[int, ...]:
    """Parse "KEY_LEFTCTRL+KEY_2" into codes, keeping the press order."""
    parts = [part.strip() for part in text.split(COMBO_SEPARATOR)]
    if not text.strip() or any(not part for part in parts):
        raise ValueError(f"malformed combo: {text!r}")
    codes = tuple(code_of(part) for part in parts)
    if len(set(codes)) != len(codes):
        raise ValueError(f"repeated key in combo: {text!r}")
    return codes


def format_combo(codes: tuple[int, ...]) -> str:
    return COMBO_SEPARATOR.join(name_of(code) for code in codes)
