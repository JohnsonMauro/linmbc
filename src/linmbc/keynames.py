"""Keys as people type them ("Ctrl+2", "Shift+A", "F1") <-> evdev codes.

Names are the physical US-layout positions evdev uses; the compositor applies
the user's layout to what LinMBC sends, exactly as for a real keyboard.
Raw evdev names ("KEY_LEFTCTRL") are accepted too.
"""

from evdev import ecodes

from linmbc.keys import is_button

# Friendly name for codes whose evdev name reads badly; everything else shows
# its evdev name without the KEY_ prefix ("F1", "A", "2", "VOLUMEUP").
_FRIENDLY = {
    ecodes.KEY_LEFTCTRL: "Ctrl",
    ecodes.KEY_RIGHTCTRL: "Right Ctrl",
    ecodes.KEY_LEFTSHIFT: "Shift",
    ecodes.KEY_RIGHTSHIFT: "Right Shift",
    ecodes.KEY_LEFTALT: "Alt",
    ecodes.KEY_RIGHTALT: "Right Alt",
    ecodes.KEY_LEFTMETA: "Super",
    ecodes.KEY_RIGHTMETA: "Right Super",
    ecodes.KEY_SPACE: "Space",
    ecodes.KEY_ENTER: "Enter",
    ecodes.KEY_ESC: "Esc",
    ecodes.KEY_TAB: "Tab",
    ecodes.KEY_BACKSPACE: "Backspace",
    ecodes.KEY_CAPSLOCK: "Caps Lock",
    ecodes.KEY_PAGEUP: "Page Up",
    ecodes.KEY_PAGEDOWN: "Page Down",
    ecodes.KEY_UP: "Up",
    ecodes.KEY_DOWN: "Down",
    ecodes.KEY_LEFT: "Left",
    ecodes.KEY_RIGHT: "Right",
    ecodes.KEY_MINUS: "-",
    ecodes.KEY_EQUAL: "=",
    ecodes.KEY_LEFTBRACE: "[",
    ecodes.KEY_RIGHTBRACE: "]",
    ecodes.KEY_SEMICOLON: ";",
    ecodes.KEY_APOSTROPHE: "'",
    ecodes.KEY_GRAVE: "`",
    ecodes.KEY_BACKSLASH: "\\",
    ecodes.KEY_COMMA: ",",
    ecodes.KEY_DOT: ".",
    ecodes.KEY_SLASH: "/",
    ecodes.KEY_KPENTER: "Num Enter",
    ecodes.KEY_KPPLUS: "Num +",
    ecodes.KEY_KPMINUS: "Num -",
    ecodes.KEY_KPASTERISK: "Num *",
    ecodes.KEY_KPSLASH: "Num /",
    ecodes.KEY_KPDOT: "Num .",
    **{getattr(ecodes, f"KEY_KP{n}"): f"Num {n}" for n in range(10)},
}
# Extra spellings accepted when parsing.
_ALIASES = {
    "control": ecodes.KEY_LEFTCTRL,
    "left ctrl": ecodes.KEY_LEFTCTRL,
    "left shift": ecodes.KEY_LEFTSHIFT,
    "left alt": ecodes.KEY_LEFTALT,
    "altgr": ecodes.KEY_RIGHTALT,
    "win": ecodes.KEY_LEFTMETA,
    "meta": ecodes.KEY_LEFTMETA,
    "cmd": ecodes.KEY_LEFTMETA,
    "return": ecodes.KEY_ENTER,
    "escape": ecodes.KEY_ESC,
    "del": ecodes.KEY_DELETE,
    "ins": ecodes.KEY_INSERT,
    "pgup": ecodes.KEY_PAGEUP,
    "pgdn": ecodes.KEY_PAGEDOWN,
}


def _keyboard_codes() -> list[int]:
    return [c for c in ecodes.KEY if 0 < c < ecodes.KEY_MAX and not is_button(c)]


def _evdev_name(code: int) -> str:
    name = ecodes.KEY[code]
    return name if isinstance(name, str) else name[0]


def key_name(code: int) -> str:
    return _FRIENDLY.get(code) or _evdev_name(code).removeprefix("KEY_")


def _lookup() -> dict[str, int]:
    table: dict[str, int] = {}
    for code in _keyboard_codes():
        names = ecodes.KEY[code]
        for name in [names] if isinstance(names, str) else names:
            table[name.lower()] = code
            table[name.lower().removeprefix("key_")] = code
    table.update({name.lower(): code for code, name in _FRIENDLY.items()})
    table.update(_ALIASES)
    return table


_LOOKUP = _lookup()


def parse_keys(text: str) -> tuple[int, ...]:
    """'Ctrl+Shift+A' or 'Ctrl+er' -> codes in press order; ValueError naming the bad part."""
    parts = [" ".join(p.split()).lower() for p in _split(text)]
    if not parts or any(not p for p in parts):
        raise ValueError(f"empty key in {text!r}")
    codes: list[int] = []
    for part in parts:
        codes += _part_codes(part)
    if len(set(codes)) != len(codes):
        raise ValueError(f"repeated key in {text!r}")
    return tuple(codes)


def _part_codes(part: str) -> list[int]:
    """A key name ("end", "num 5"), or else its characters as keys pressed together
    ("er" = E+R, like X-Mouse Button Control). A name always wins over its letters."""
    code = _LOOKUP.get(part)
    if code is not None:
        return [code]
    chars = [ch for ch in part if not ch.isspace()]
    codes = [_LOOKUP.get(ch) for ch in chars]
    if len(chars) > 1 and all(c is not None for c in codes):
        return codes
    raise ValueError(f"unknown key: {part!r}")


def _split(text: str) -> list[str]:
    """Split on '+' but keep a literal '+' key ("Num +", "Ctrl++")."""
    parts, current = [], ""
    for ch in text:
        if ch == "+" and current.strip() and not current.rstrip().lower().endswith("num"):
            parts.append(current)
            current = ""
        else:
            current += ch
    parts.append(current)
    return [p.strip() for p in parts]


def format_keys(codes: tuple[int, ...]) -> str:
    return "+".join(key_name(code) for code in codes)
