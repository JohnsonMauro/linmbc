import pytest
from evdev import ecodes as e

from linmbc.keynames import format_keys, parse_keys


@pytest.mark.parametrize(
    ("text", "codes"),
    [
        ("Ctrl+2", (e.KEY_LEFTCTRL, e.KEY_2)),
        ("ctrl + shift + a", (e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT, e.KEY_A)),
        ("F1", (e.KEY_F1,)),
        ("space", (e.KEY_SPACE,)),
        ("Alt+Tab", (e.KEY_LEFTALT, e.KEY_TAB)),
        ("Super+E", (e.KEY_LEFTMETA, e.KEY_E)),
        ("Right Ctrl+Enter", (e.KEY_RIGHTCTRL, e.KEY_ENTER)),
        ("KEY_LEFTCTRL+KEY_2", (e.KEY_LEFTCTRL, e.KEY_2)),
        ("Num 5", (e.KEY_KP5,)),
        ("Up", (e.KEY_UP,)),
        ("Esc", (e.KEY_ESC,)),
        (";", (e.KEY_SEMICOLON,)),
        ("Q", (e.KEY_Q,)),
        # typed letters with no "+" are pressed together, like the other macro tool
        ("er", (e.KEY_E, e.KEY_R)),
        ("ER", (e.KEY_E, e.KEY_R)),
        ("Ctrl+er", (e.KEY_LEFTCTRL, e.KEY_E, e.KEY_R)),
        ("12", (e.KEY_1, e.KEY_2)),
        ("e r", (e.KEY_E, e.KEY_R)),
        # a key name wins over its letters
        ("end", (e.KEY_END,)),
        ("up", (e.KEY_UP,)),
        ("U+P", (e.KEY_U, e.KEY_P)),
    ],
)
def test_parse_friendly_and_raw_names(text, codes):
    assert parse_keys(text) == codes


@pytest.mark.parametrize("bad", ["", "+", "Ctrl+", "Ctrl+Ctrl", "ee", "Ctrl+e!", "BTN_LEFT", "é"])
def test_parse_rejects_garbage(bad):
    with pytest.raises(ValueError):
        parse_keys(bad)


@pytest.mark.parametrize(
    ("codes", "text"),
    [
        ((e.KEY_LEFTCTRL, e.KEY_2), "Ctrl+2"),
        ((e.KEY_RIGHTALT, e.KEY_F12), "Right Alt+F12"),
        ((e.KEY_SPACE,), "Space"),
        ((e.KEY_KP5,), "Num 5"),
        ((e.KEY_SEMICOLON,), ";"),
        ((e.KEY_VOLUMEUP,), "VOLUMEUP"),
    ],
)
def test_format_is_friendly(codes, text):
    assert format_keys(codes) == text


def test_every_keyboard_key_round_trips():
    from linmbc.engine import keyboard_keys

    for code in keyboard_keys():
        assert parse_keys(format_keys((code,))) == (code,), code
