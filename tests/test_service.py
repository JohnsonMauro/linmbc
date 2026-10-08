import pytest
from evdev import ecodes as e

from linmbc.config import Config, load_config
from linmbc.devices import MouseNode
from linmbc.engine import ButtonRecord
from linmbc.profile import Action, Mode, Profile, save
from linmbc.service import Service

WL = MouseNode("/dev/input/event8", "WL MOUSE", "36a7", "a868", frozenset())
KC = MouseNode("/dev/input/event3", "Keychron Mouse", "3434", "0d80", frozenset())


class FakeGrab:
    def __init__(self, node, runner, sink):
        self.node, self.runner, self.sink = node, runner, sink
        self.closed = False
        self.records = []
        self.error = None
        self.ticks = 0
        self.released = []
        self.deadline = None

    def fileno(self):
        return 100 + int(self.node.path.removeprefix("/dev/input/event"))

    def pump(self):
        if self.error:
            raise self.error
        records, self.records = self.records, []
        return records

    def tick(self):
        self.ticks += 1

    def set_actions(self, actions):
        self.released += self.runner.set_actions(actions, now=0.0)

    def next_deadline(self):
        return self.deadline

    def close(self):
        self.closed = True


class Harness:
    def __init__(self, tmp_path, mice=(WL, KC)):
        self.mice = list(mice)
        self.grabs = []
        self.logs = []
        self.buttons = []
        self.sinks = 0
        self.config_path = tmp_path / "config.toml"
        self.profiles = tmp_path / "profiles"
        self.service = Service(
            config_path=self.config_path,
            profiles_dir=self.profiles,
            find_mice=lambda: list(self.mice),
            grab_factory=self._grab,
            sink_factory=self._sink,
            on_log=self.logs.append,
            on_button=lambda *args: self.buttons.append(args),
        )

    def _grab(self, node, runner, sink):
        grab = FakeGrab(node, runner, sink)
        self.grabs.append(grab)
        return grab

    def _sink(self):
        self.sinks += 1
        return object()

    def open_grabs(self):
        return [g for g in self.grabs if not g.closed]

    def add_profile(self, name, match=(), key=e.KEY_1, mode=Mode.HOLD):
        save(
            Profile(name=name, match=match, buttons={e.BTN_SIDE: Action((key,), mode)}),
            self.profiles / f"{name.lower().replace(' ', '-')}.toml",
        )

    def side_output(self):
        """What the first grabbed mouse sends for a BTN_SIDE press right now."""
        runner = self.open_grabs()[0].runner
        out = runner.key(e.BTN_SIDE, 1, now=0.0)
        runner.key(e.BTN_SIDE, 0, now=0.0)
        return out


def test_enable_grabs_every_physical_mouse(tmp_path):
    h = Harness(tmp_path)
    h.service.set_enabled(True)
    assert {g.node for g in h.open_grabs()} == {WL, KC}
    assert h.sinks == 1


def test_disable_releases_every_grab(tmp_path):
    h = Harness(tmp_path)
    h.service.set_enabled(True)
    h.service.set_enabled(False)
    assert h.open_grabs() == []


def test_state_is_persisted_and_restored(tmp_path):
    h = Harness(tmp_path)
    h.add_profile("Desktop")
    h.service.reload_profiles()
    h.service.set_default_profile("Desktop")
    h.service.set_enabled(True)
    assert load_config(h.config_path) == Config(enabled=True, default_profile="Desktop")

    h2 = Harness(tmp_path)
    h2.service.start()
    assert len(h2.open_grabs()) == 2
    assert h2.side_output() == [(e.KEY_1, 1)]


def test_window_of_a_game_activates_its_profile_and_leaving_restores_default(tmp_path):
    h = Harness(tmp_path)
    h.add_profile("Desktop", key=e.KEY_9)
    h.add_profile("Last Epoch", match=("steam_app_899770",), key=e.KEY_1)
    h.service.reload_profiles()
    h.service.set_default_profile("Desktop")
    h.service.set_enabled(True)

    h.service.set_active_window("steam_app_899770", "last epoch.exe")
    assert h.service.state()["active_profile"] == "Last Epoch"
    assert h.side_output() == [(e.KEY_1, 1)]

    h.service.set_active_window("google-chrome", "chrome")
    assert h.service.state()["active_profile"] == "Desktop"
    assert h.side_output() == [(e.KEY_9, 1)]


def test_window_match_is_case_insensitive_and_also_checks_resource_name(tmp_path):
    h = Harness(tmp_path)
    h.add_profile("PoE", match=("PathOfExile.exe",))
    h.service.reload_profiles()
    h.service.set_active_window("steam_app_238960", "pathofexile.exe")
    assert h.service.state()["active_profile"] == "PoE"


def test_title_entry_matches_the_whole_title_in_any_case(tmp_path):
    # Lutris/umu games without an id all get the class steam_app_default
    h = Harness(tmp_path)
    h.add_profile("Diablo IV", match=("title:Diablo IV",))
    h.service.reload_profiles()
    h.service.set_active_window("steam_app_default", "steam_app_default", "diablo iv")
    assert h.service.state()["active_profile"] == "Diablo IV"
    h.service.set_active_window("steam_app_default", "steam_app_default", "Battle.net")
    assert h.service.state()["active_profile"] == ""
    h.service.set_active_window("firefox", "firefox", "Diablo IV build guide — Mozilla Firefox")
    assert h.service.state()["active_profile"] == ""


def test_title_match_wins_over_class_match(tmp_path):
    h = Harness(tmp_path)
    h.add_profile("Battle.net", match=("steam_app_default",))
    h.add_profile("Diablo IV", match=("title:Diablo IV",))
    h.service.reload_profiles()
    h.service.set_active_window("steam_app_default", "steam_app_default", "Diablo IV")
    assert h.service.state()["active_profile"] == "Diablo IV"
    h.service.set_active_window("steam_app_default", "steam_app_default", "Battle.net")
    assert h.service.state()["active_profile"] == "Battle.net"


def test_title_entry_is_not_compared_to_the_class(tmp_path):
    h = Harness(tmp_path)
    h.add_profile("Odd", match=("title:", "title:firefox"))
    h.service.reload_profiles()
    h.service.set_active_window("firefox", "firefox", "")
    assert h.service.state()["active_profile"] == ""


def test_title_changing_on_the_focused_window_switches_profile(tmp_path):
    h = Harness(tmp_path)
    h.add_profile("Diablo IV", match=("title:Diablo IV",))
    h.service.reload_profiles()
    h.service.set_active_window("steam_app_default", "steam_app_default", "Wine")
    h.service.set_active_window("steam_app_default", "steam_app_default", "Diablo IV")
    assert h.service.state()["active_profile"] == "Diablo IV"
    assert h.service.state()["window_title"] == "Diablo IV"


def test_no_default_profile_means_buttons_unchanged_outside_games(tmp_path):
    h = Harness(tmp_path)
    h.add_profile("Last Epoch", match=("steam_app_899770",))
    h.service.reload_profiles()
    h.service.set_enabled(True)
    h.service.set_active_window("konsole", "konsole")
    assert h.service.state()["active_profile"] == ""
    assert h.side_output() == [(e.BTN_SIDE, 1)]


def test_profile_switch_is_logged_once_with_the_window(tmp_path):
    h = Harness(tmp_path)
    h.add_profile("Last Epoch", match=("steam_app_899770",))
    h.service.reload_profiles()
    h.service.set_active_window("steam_app_899770", "x")
    h.service.set_active_window("steam_app_899770", "x")
    switches = [line for line in h.logs if "steam_app_899770" in line]
    assert len(switches) == 1
    assert "Last Epoch" in switches[0]


def test_unknown_default_profile_is_refused(tmp_path):
    h = Harness(tmp_path)
    with pytest.raises(ValueError, match="nope"):
        h.service.set_default_profile("nope")


def test_broken_profile_file_is_logged_not_fatal(tmp_path):
    h = Harness(tmp_path)
    h.profiles.mkdir()
    (h.profiles / "broken.toml").write_text("name = ")
    h.add_profile("Good")
    h.service.reload_profiles()
    assert [p["name"] for p in h.service.state()["profiles"]] == ["Good"]
    assert any("broken.toml" in line for line in h.logs)


def test_reload_reapplies_the_active_profile(tmp_path):
    h = Harness(tmp_path)
    h.add_profile("Desktop", key=e.KEY_1)
    h.service.reload_profiles()
    h.service.set_default_profile("Desktop")
    h.service.set_enabled(True)
    h.add_profile("Desktop", key=e.KEY_2)
    h.service.reload_profiles()
    assert h.side_output() == [(e.KEY_2, 1)]


def test_rescan_picks_up_replugged_mouse(tmp_path):
    h = Harness(tmp_path, mice=[])
    h.service.set_enabled(True)
    assert h.open_grabs() == []
    h.mice = [WL]
    h.service.rescan()
    assert [g.node for g in h.open_grabs()] == [WL]


def test_unplugged_mouse_is_dropped_and_service_keeps_running(tmp_path):
    h = Harness(tmp_path, mice=[WL])
    h.service.set_enabled(True)
    grab = h.open_grabs()[0]
    grab.error = OSError(19, "No such device")
    h.service.on_ready(grab.fileno())
    assert grab.closed
    assert h.service.state()["enabled"] is True
    assert any("WL MOUSE" in line and "lost" in line for line in h.logs)


def test_unexpected_error_fails_open(tmp_path):
    h = Harness(tmp_path)
    h.service.set_enabled(True)
    h.open_grabs()[0].error = RuntimeError("boom")
    h.service.on_ready(h.open_grabs()[0].fileno())
    assert h.open_grabs() == []
    assert h.service.state()["enabled"] is False
    assert any("boom" in line for line in h.logs)


def test_unexpected_error_in_tick_fails_open(tmp_path):
    h = Harness(tmp_path, mice=[WL])
    h.service.set_enabled(True)
    h.open_grabs()[0].tick = lambda: (_ for _ in ()).throw(RuntimeError("tick boom"))
    h.service.tick()
    assert h.open_grabs() == []
    assert h.service.state()["enabled"] is False


def test_tick_and_deadline_cover_every_grab(tmp_path):
    h = Harness(tmp_path)
    h.service.set_enabled(True)
    a, b = h.open_grabs()
    a.deadline, b.deadline = 5.0, 2.0
    assert h.service.next_deadline() == 2.0
    h.service.tick()
    assert a.ticks == b.ticks == 1


def test_button_records_are_logged_and_signalled(tmp_path):
    h = Harness(tmp_path, mice=[WL])
    h.service.set_enabled(True)
    grab = h.open_grabs()[0]
    grab.records = [ButtonRecord(e.BTN_SIDE, 1, [(e.KEY_1, 1)], 0.0)]
    h.service.on_ready(grab.fileno())
    assert h.buttons == [(WL.key, "BTN_SIDE", 1)]
    assert any("BTN_SIDE down -> KEY_1 down" in line for line in h.logs)


def test_state_reports_grabbed_mice_profiles_and_window(tmp_path):
    h = Harness(tmp_path, mice=[WL])
    h.add_profile("Last Epoch", match=("steam_app_899770",))
    h.service.reload_profiles()
    h.service.set_enabled(True)
    h.service.set_active_window("steam_app_899770", "x")
    state = h.service.state()
    assert state["mice"] == ["WL MOUSE"]
    assert state["profiles"] == [{"name": "Last Epoch", "match": ["steam_app_899770"]}]
    assert state["window_class"] == "steam_app_899770"


def test_switching_profile_releases_keys_of_a_running_loop(tmp_path):
    h = Harness(tmp_path, mice=[WL])
    h.add_profile("Last Epoch", match=("steam_app_899770",), mode=Mode.TOGGLE)
    h.service.reload_profiles()
    h.service.set_enabled(True)
    h.service.set_active_window("steam_app_899770", "x")
    grab = h.open_grabs()[0]
    assert grab.runner.key(e.BTN_SIDE, 1, now=0.0) == [(e.KEY_1, 1)]  # loop running
    h.service.set_active_window("konsole", "konsole")
    assert grab.released == [(e.KEY_1, 0)]


def test_detected_mice_are_reported_even_when_disabled(tmp_path):
    h = Harness(tmp_path)
    h.service.start()
    assert h.service.state()["enabled"] is False
    assert h.service.state()["mice"] == ["WL MOUSE", "Keychron Mouse"]
    assert h.open_grabs() == []


def test_gui_is_told_about_every_focus_change_even_without_profile_change(tmp_path):
    changes = []
    h = Harness(tmp_path)
    h.service._on_change = lambda: changes.append(h.service.state()["window_class"])
    h.service.set_active_window("firefox", "firefox")
    h.service.set_active_window("konsole", "konsole")
    h.service.set_active_window("konsole", "konsole")
    assert changes == ["firefox", "konsole"]


def test_state_lists_buttons_of_detected_mice(tmp_path):
    wl = MouseNode(
        "/dev/input/event8", "WL MOUSE", "36a7", "a868", frozenset({240, *range(0x110, 0x115)})
    )
    big = MouseNode("/dev/input/event9", "Big", "1234", "0001", frozenset({0x110, 0x115, 0x116}))
    h = Harness(tmp_path, mice=[wl, big])
    h.service.start()
    assert h.service.state()["buttons"] == [
        "BTN_LEFT",
        "BTN_RIGHT",
        "BTN_MIDDLE",
        "BTN_SIDE",
        "BTN_EXTRA",
        "BTN_FORWARD",
        "BTN_BACK",
    ]


def test_focus_change_within_the_same_profile_keeps_a_running_loop(tmp_path):
    h = Harness(tmp_path, mice=[WL])
    h.add_profile("Last Epoch", match=("steam_app_899770", "last epoch.exe"), mode=Mode.TOGGLE)
    h.service.reload_profiles()
    h.service.set_enabled(True)
    h.service.set_active_window("steam_app_899770", "x")
    grab = h.open_grabs()[0]
    grab.runner.key(e.BTN_SIDE, 1, now=0.0)  # loop running
    h.service.set_active_window("whatever", "last epoch.exe")  # same profile
    assert grab.released == []


def test_mouse_function_of_a_keyboard_is_grabbed_but_not_shown(tmp_path):
    kb_mouse = MouseNode(
        "/dev/input/event3", "K8 Mouse", "3434", "0d80", frozenset(range(0x110, 0x118)), True
    )
    wl = MouseNode("/dev/input/event8", "WL MOUSE", "36a7", "a868", frozenset(range(0x110, 0x115)))
    h = Harness(tmp_path, mice=[kb_mouse, wl])
    h.service.set_enabled(True)
    assert {g.node.name for g in h.open_grabs()} == {"K8 Mouse", "WL MOUSE"}
    assert h.service.state()["mice"] == ["WL MOUSE"]
    assert h.service.state()["buttons"] == [
        "BTN_LEFT",
        "BTN_RIGHT",
        "BTN_MIDDLE",
        "BTN_SIDE",
        "BTN_EXTRA",
    ]
