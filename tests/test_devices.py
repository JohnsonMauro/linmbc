from pathlib import Path

from linmbc.devices import find_mice

MOUSE_KEYS = "1f0000 1000000000000 0 0 0"  # BTN_LEFT..BTN_EXTRA + KEY_UNKNOWN
KEYBOARD_KEYS = "1000000000007 ff980000000007ff febeffdfffefffff fffffffffffffffe"
POINTER_REL = "1943"  # X, Y, HWHEEL, WHEEL, WHEEL_HI_RES, HWHEEL_HI_RES


def add_node(
    root: Path,
    event: str,
    *,
    name,
    keys,
    rel="0",
    vendor="36a7",
    product="a868",
    virtual=False,
    hid=None,
) -> None:
    """Fake /sys/class/input/<event>; nodes with the same `hid` share one HID device."""
    parent = "virtual/input" if virtual else f"pci0000:00/usb1/1-1/{hid or event}/input"
    dev = root / "devices" / parent / f"input_{event}"
    (dev / "capabilities").mkdir(parents=True)
    (dev / "id").mkdir()
    (dev / "name").write_text(name + "\n")
    (dev / "capabilities/key").write_text(keys + "\n")
    (dev / "capabilities/rel").write_text(rel + "\n")
    (dev / "id/vendor").write_text(vendor + "\n")
    (dev / "id/product").write_text(product + "\n")
    node = root / "class/input" / event
    node.mkdir(parents=True)
    (node / "device").symlink_to(dev)


def test_finds_mouse_and_skips_keyboard_and_virtual(tmp_path):
    add_node(tmp_path, "event8", name="WL MOUSE", keys=MOUSE_KEYS, rel=POINTER_REL)
    add_node(tmp_path, "event11", name="WL MOUSE Keyboard", keys=KEYBOARD_KEYS)
    add_node(
        tmp_path,
        "event30",
        name="LinMBC virtual mouse",
        keys=MOUSE_KEYS,
        rel=POINTER_REL,
        virtual=True,
    )

    mice = find_mice(sysfs_root=tmp_path)

    assert [m.path for m in mice] == ["/dev/input/event8"]
    assert mice[0].usb_id == "36a7:a868"
    assert mice[0].name == "WL MOUSE"


def test_node_with_pointer_and_keyboard_keys_is_refused(tmp_path):
    combo = "1f0000 0 0 0 fffffffffffffffe"
    add_node(tmp_path, "event4", name="Combo receiver", keys=combo, rel=POINTER_REL)
    assert find_mice(sysfs_root=tmp_path) == []


def test_buttons_without_pointer_axes_are_not_a_mouse(tmp_path):
    add_node(tmp_path, "event5", name="Buttons only", keys=MOUSE_KEYS)
    assert find_mice(sysfs_root=tmp_path) == []


def test_match_by_usb_id_or_name_substring(tmp_path):
    add_node(
        tmp_path,
        "event3",
        name="Keychron Mouse",
        keys=MOUSE_KEYS,
        rel=POINTER_REL,
        vendor="3434",
        product="0d80",
    )
    add_node(tmp_path, "event8", name="WL MOUSE", keys=MOUSE_KEYS, rel=POINTER_REL)

    assert [m.path for m in find_mice("3434:0d80", sysfs_root=tmp_path)] == ["/dev/input/event3"]
    assert [m.path for m in find_mice("wl mouse", sysfs_root=tmp_path)] == ["/dev/input/event8"]


def test_device_key_is_stable_across_event_numbers(tmp_path):
    add_node(tmp_path, "event8", name="WL MOUSE", keys=MOUSE_KEYS, rel=POINTER_REL)
    assert find_mice(sysfs_root=tmp_path)[0].key == "36a7:a868:WL MOUSE"


def test_mouse_function_of_a_keyboard_is_flagged(tmp_path):
    # Keychron K8: the "Mouse" node shares its HID device with the full keyboard.
    add_node(tmp_path, "event3", name="K8 Mouse", keys="ff0000 0 0 0 0", rel=POINTER_REL, hid="kc")
    add_node(tmp_path, "event6", name="K8 Keyboard", keys=KEYBOARD_KEYS, hid="kc")
    # WLMOUSE: its keyboard interface is a different HID device.
    add_node(tmp_path, "event8", name="WL MOUSE", keys=MOUSE_KEYS, rel=POINTER_REL, hid="wl0")
    add_node(tmp_path, "event11", name="WL MOUSE Keyboard", keys=KEYBOARD_KEYS, hid="wl1")

    flags = {m.name: m.on_keyboard for m in find_mice(sysfs_root=tmp_path)}
    assert flags == {"K8 Mouse": True, "WL MOUSE": False}
