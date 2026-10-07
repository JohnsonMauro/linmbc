import random

import pytest
from evdev import ecodes as e

from linmbc.profile import (
    Action,
    Delay,
    Mode,
    Profile,
    ProfileError,
    dumps,
    load,
    loads,
    save,
)

SAMPLE = """
name = "Path of Exile 2"
match = ["steam_app_2694490"]

[buttons]
BTN_SIDE = "KEY_1"
BTN_EXTRA = { keys = "KEY_LEFTCTRL+KEY_2", mode = "repeat", count = 5, delay_ms = [100, 900] }
BTN_MIDDLE = { keys = "KEY_Q", mode = "toggle", delay_ms = 50 }
"""


def test_loads_parses_shorthand_and_full_actions():
    p = loads(SAMPLE)
    assert p.name == "Path of Exile 2"
    assert p.match == ("steam_app_2694490",)
    assert p.buttons[e.BTN_SIDE] == Action((e.KEY_1,))
    assert p.buttons[e.BTN_EXTRA] == Action(
        (e.KEY_LEFTCTRL, e.KEY_2), Mode.REPEAT, count=5, delay=Delay(100, 900)
    )
    assert p.buttons[e.BTN_MIDDLE] == Action((e.KEY_Q,), Mode.TOGGLE, delay=Delay(50, 50))


def test_buttons_and_match_are_optional():
    p = loads('name = "Desktop"')
    assert p.match == ()
    assert p.buttons == {}


def test_dumps_round_trips_including_quotes_unicode_and_modes():
    p = Profile(
        name='Diablo "IV" – ção',
        match=("steam_app_2344520", "diablo iv.exe"),
        buttons={
            e.BTN_SIDE: Action((e.KEY_LEFTSHIFT, e.KEY_A)),
            e.BTN_EXTRA: Action((e.KEY_1,), Mode.ONCE, delay=Delay(80, 80)),
            e.BTN_MIDDLE: Action((e.KEY_2,), Mode.REPEAT, count=3, delay=Delay(100, 900)),
        },
    )
    assert loads(dumps(p)) == p


def test_hold_with_default_delay_is_written_as_shorthand():
    p = Profile(name="x", buttons={e.BTN_SIDE: Action((e.KEY_1,))})
    assert 'BTN_SIDE = "KEY_1"' in dumps(p)


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("name = ", "TOML"),
        ("match = []", "name"),
        ('name = ""', "name"),
        ('name = "x"\nmatch = "notalist"', "match"),
        ('name = "x"\n[buttons]\nKEY_A = "KEY_1"', "KEY_A"),
        ('name = "x"\n[buttons]\nBTN_SIDE = "KEY_NOPE"', "BTN_SIDE"),
        ('name = "x"\n[buttons]\nBTN_SIDE = 3', "BTN_SIDE"),
        ('name = "x"\n[buttons]\nBTN_SIDE = { keys = "KEY_1", mode = "spin" }', "mode"),
        (
            'name = "x"\n[buttons]\nBTN_SIDE = { keys = "KEY_1", mode = "repeat", count = 0 }',
            "count",
        ),
        ('name = "x"\n[buttons]\nBTN_SIDE = { keys = "KEY_1", delay_ms = [900, 100] }', "delay"),
        (
            'name = "x"\n[buttons]\nBTN_SIDE = { keys = "KEY_1", mode = "toggle", delay_ms = 1 }',
            "delay",
        ),
        ('name = "x"\n[buttons]\nBTN_SIDE = { mode = "once" }', "keys"),
        ('name = "x"\n[buttons]\nBTN_SIDE = { keys = "KEY_1", extra = 1 }', "extra"),
    ],
)
def test_invalid_profiles_name_the_problem(text, fragment):
    with pytest.raises(ProfileError, match=fragment):
        loads(text)


def test_only_toggle_and_repeat_send_several_inputs():
    assert not Action((e.KEY_1,)).sends_several_inputs
    assert not Action((e.KEY_1,), Mode.ONCE).sends_several_inputs
    assert Action((e.KEY_1,), Mode.TOGGLE).sends_several_inputs
    assert Action((e.KEY_1,), Mode.REPEAT, count=2).sends_several_inputs


def test_delay_sample_stays_in_range_and_fixed_is_exact():
    rng = random.Random(1)
    assert Delay(50, 50).sample(rng) == 0.05
    samples = [Delay(100, 900).sample(rng) for _ in range(200)]
    assert all(0.1 <= s <= 0.9 for s in samples)
    assert max(samples) - min(samples) > 0.5


def test_save_then_load_from_disk(tmp_path):
    p = Profile(name="Last Epoch", buttons={e.BTN_EXTRA: Action((e.KEY_E,))})
    path = tmp_path / "last-epoch.toml"
    save(p, path)
    assert load(path) == p
    assert not list(tmp_path.glob("*.tmp"))


def test_load_error_mentions_the_file(tmp_path):
    path = tmp_path / "broken.toml"
    path.write_text("name = ")
    with pytest.raises(ProfileError, match="broken.toml"):
        load(path)
