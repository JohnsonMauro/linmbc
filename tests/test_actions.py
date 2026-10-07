import random

from evdev import ecodes as e

from linmbc.actions import ActionRunner
from linmbc.profile import Action, Delay, Mode

K1 = (e.KEY_1,)


def runner(actions):
    return ActionRunner(actions, rng=random.Random(7))


def drain(r, until):
    """Run every deadline up to `until`; return [(time, code, value)]."""
    out = []
    while (t := r.next_deadline()) is not None and t <= until:
        out += [(round(t, 3), c, v) for c, v in r.tick(t)]
    return out


def test_hold_follows_the_button():
    r = runner({e.BTN_SIDE: Action(K1)})
    assert r.key(e.BTN_SIDE, 1, now=0.0) == [(e.KEY_1, 1)]
    assert r.key(e.BTN_SIDE, 0, now=0.5) == [(e.KEY_1, 0)]
    assert r.next_deadline() is None


def test_unmapped_button_passes_through():
    r = runner({})
    assert r.key(e.BTN_LEFT, 1, now=0.0) == [(e.BTN_LEFT, 1)]
    assert r.key(e.BTN_LEFT, 0, now=0.1) == [(e.BTN_LEFT, 0)]


def test_once_taps_for_delay_and_ignores_release():
    r = runner({e.BTN_SIDE: Action(K1, Mode.ONCE, delay=Delay(80, 80))})
    assert r.key(e.BTN_SIDE, 1, now=1.0) == [(e.KEY_1, 1)]
    assert r.key(e.BTN_SIDE, 0, now=1.01) == []
    assert drain(r, until=5) == [(1.08, e.KEY_1, 0)]


def test_repeat_sends_count_taps_spaced_by_delay():
    r = runner({e.BTN_SIDE: Action(K1, Mode.REPEAT, count=3, delay=Delay(100, 100))})
    first = r.key(e.BTN_SIDE, 1, now=0.0)
    events = [(0.0, c, v) for c, v in first] + drain(r, until=5)
    downs = [t for t, _, v in events if v == 1]
    ups = [t for t, _, v in events if v == 0]
    assert downs == [0.0, 0.1, 0.2]
    assert len(ups) == 3 and all(u - d < 0.1 for d, u in zip(downs, ups, strict=True))
    assert r.next_deadline() is None


def test_clicking_again_cancels_a_running_repeat():
    r = runner({e.BTN_SIDE: Action(K1, Mode.REPEAT, count=100, delay=Delay(100, 100))})
    r.key(e.BTN_SIDE, 1, now=0.0)
    drain(r, until=0.25)
    r.key(e.BTN_SIDE, 0, now=0.26)
    out = r.key(e.BTN_SIDE, 1, now=0.3)
    assert (e.KEY_1, 1) not in out
    assert all(value == 0 for _, _, value in drain(r, until=10))
    assert r.next_deadline() is None


def test_toggle_loops_until_clicked_again_and_releases_held_key():
    r = runner({e.BTN_SIDE: Action(K1, Mode.TOGGLE, delay=Delay(100, 100))})
    r.key(e.BTN_SIDE, 1, now=0.0)
    r.key(e.BTN_SIDE, 0, now=0.05)
    taps = [t for t, _, v in drain(r, until=1.0) if v == 1]
    assert taps == [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    stop = r.key(e.BTN_SIDE, 1, now=1.01)  # key is down at this moment
    assert stop == [(e.KEY_1, 0)]
    assert r.next_deadline() is None


def test_random_delay_spaces_taps_inside_the_range():
    r = runner({e.BTN_SIDE: Action(K1, Mode.TOGGLE, delay=Delay(100, 900))})
    r.key(e.BTN_SIDE, 1, now=0.0)
    taps = [0.0] + [t for t, _, v in drain(r, until=60) if v == 1]
    gaps = [b - a for a, b in zip(taps, taps[1:], strict=False)]
    assert len(gaps) > 50
    assert all(0.099 <= g <= 0.901 for g in gaps)
    assert len({round(g, 3) for g in gaps}) > 10  # really random, not fixed


def test_shared_key_between_hold_and_timed_job_is_not_released_early():
    r = runner(
        {
            e.BTN_SIDE: Action(K1),
            e.BTN_EXTRA: Action(K1, Mode.ONCE, delay=Delay(50, 50)),
        }
    )
    r.key(e.BTN_SIDE, 1, now=0.0)
    assert r.key(e.BTN_EXTRA, 1, now=0.1) == []  # KEY_1 already down
    assert drain(r, until=1) == []  # tap ends, hold still owns KEY_1
    assert r.key(e.BTN_SIDE, 0, now=2.0) == [(e.KEY_1, 0)]


def test_changing_actions_stops_jobs_and_releases_keys():
    r = runner({e.BTN_SIDE: Action(K1, Mode.TOGGLE, delay=Delay(100, 100))})
    r.key(e.BTN_SIDE, 1, now=0.0)
    out = r.set_actions({}, now=0.01)
    assert out == [(e.KEY_1, 0)]
    assert r.next_deadline() is None


def test_release_all_stops_everything():
    r = runner({e.BTN_SIDE: Action(K1, Mode.TOGGLE), e.BTN_EXTRA: Action((e.KEY_2,))})
    r.key(e.BTN_SIDE, 1, now=0.0)
    r.key(e.BTN_EXTRA, 1, now=0.0)
    assert sorted(r.release_all()) == sorted([(e.KEY_1, 0), (e.KEY_2, 0)])
    assert r.next_deadline() is None


def test_button_held_as_hold_then_remapped_to_timed_releases_its_hold():
    r = runner({e.BTN_SIDE: Action(K1)})
    r.key(e.BTN_SIDE, 1, now=0.0)
    r.set_actions({e.BTN_SIDE: Action((e.KEY_2,), Mode.TOGGLE)}, now=0.1)
    assert r.key(e.BTN_SIDE, 0, now=0.2) == [(e.KEY_1, 0)]
