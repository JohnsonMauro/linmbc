from evdev import ecodes as e

from linmbc.remap import Remapper

CTRL_2 = (e.KEY_LEFTCTRL, e.KEY_2)


def test_unmapped_button_passes_through():
    r = Remapper({})
    assert r.key(e.BTN_LEFT, 1) == [(e.BTN_LEFT, 1)]
    assert r.key(e.BTN_LEFT, 0) == [(e.BTN_LEFT, 0)]


def test_mapped_button_presses_combo_in_order_and_releases_in_reverse():
    r = Remapper({e.BTN_SIDE: CTRL_2})
    assert r.key(e.BTN_SIDE, 1) == [(e.KEY_LEFTCTRL, 1), (e.KEY_2, 1)]
    assert r.key(e.BTN_SIDE, 0) == [(e.KEY_2, 0), (e.KEY_LEFTCTRL, 0)]


def test_repeat_of_mapped_button_emits_nothing():
    r = Remapper({e.BTN_SIDE: (e.KEY_1,)})
    r.key(e.BTN_SIDE, 1)
    assert r.key(e.BTN_SIDE, 2) == []


def test_release_uses_mapping_active_at_press_time():
    r = Remapper({e.BTN_SIDE: (e.KEY_1,)})
    r.key(e.BTN_SIDE, 1)
    r.set_mapping({e.BTN_SIDE: (e.KEY_9,)})
    assert r.key(e.BTN_SIDE, 0) == [(e.KEY_1, 0)]


def test_button_pressed_before_it_was_mapped_releases_itself():
    r = Remapper({})
    r.key(e.BTN_SIDE, 1)
    r.set_mapping({e.BTN_SIDE: (e.KEY_1,)})
    assert r.key(e.BTN_SIDE, 0) == [(e.BTN_SIDE, 0)]


def test_release_without_press_is_dropped():
    r = Remapper({e.BTN_SIDE: (e.KEY_1,)})
    assert r.key(e.BTN_SIDE, 0) == []


def test_shared_output_key_stays_down_until_last_source_releases():
    r = Remapper({e.BTN_SIDE: (e.KEY_1,), e.BTN_EXTRA: (e.KEY_1,)})
    assert r.key(e.BTN_SIDE, 1) == [(e.KEY_1, 1)]
    assert r.key(e.BTN_EXTRA, 1) == []
    assert r.key(e.BTN_SIDE, 0) == []
    assert r.key(e.BTN_EXTRA, 0) == [(e.KEY_1, 0)]


def test_release_all_lets_go_of_everything_held():
    r = Remapper({e.BTN_SIDE: CTRL_2})
    r.key(e.BTN_SIDE, 1)
    r.key(e.BTN_LEFT, 1)
    released = r.release_all()
    assert sorted(released) == sorted([(e.KEY_2, 0), (e.KEY_LEFTCTRL, 0), (e.BTN_LEFT, 0)])
    assert r.release_all() == []


def test_mapping_is_copied_not_shared():
    mapping = {e.BTN_SIDE: (e.KEY_1,)}
    r = Remapper(mapping)
    mapping[e.BTN_SIDE] = (e.KEY_9,)
    assert r.key(e.BTN_SIDE, 1) == [(e.KEY_1, 1)]
