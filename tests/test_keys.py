import pytest
from evdev import ecodes

from linmbc.keys import code_of, format_combo, is_button, name_of, parse_combo


def test_code_of_resolves_key_and_button_names():
    assert code_of("KEY_1") == ecodes.KEY_1
    assert code_of("BTN_SIDE") == ecodes.BTN_SIDE


@pytest.mark.parametrize("bad", ["", "KEY_NOPE", "REL_X", "SYN_REPORT", "key_1"])
def test_code_of_rejects_unknown_or_non_key_names(bad):
    with pytest.raises(ValueError):
        code_of(bad)


def test_name_of_picks_first_alias():
    assert name_of(ecodes.BTN_LEFT) == "BTN_LEFT"  # ecodes lists BTN_LEFT/BTN_MOUSE


def test_parse_combo_keeps_order_and_trims_spaces():
    assert parse_combo(" KEY_LEFTCTRL + KEY_2 ") == (ecodes.KEY_LEFTCTRL, ecodes.KEY_2)


@pytest.mark.parametrize("bad", ["", "+", "KEY_1+", "KEY_1+KEY_1", "KEY_1+KEY_NOPE"])
def test_parse_combo_rejects_malformed(bad):
    with pytest.raises(ValueError):
        parse_combo(bad)


def test_format_combo_round_trips():
    combo = (ecodes.KEY_LEFTSHIFT, ecodes.KEY_A)
    assert parse_combo(format_combo(combo)) == combo


def test_is_button_separates_mouse_buttons_from_keys():
    assert is_button(ecodes.BTN_EXTRA)
    assert not is_button(ecodes.KEY_A)
