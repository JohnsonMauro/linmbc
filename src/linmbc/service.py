"""Daemon logic without IPC or event loop: grab the mice, pick the profile, run actions.

Every physical mouse is grabbed while enabled. The profile in effect is the one
whose `match` names the focused window (class or resource name, any case; a
"title:" entry names the whole title and wins over class matches), else the
default profile. Devices, grabs and the uinput sink come in as
arguments so every rule here is unit-tested with fakes.

Failure policy is fail-open: on an unexpected error every grab is released, so
the mouse falls back to its normal behaviour.
"""

import contextlib
import dataclasses
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from evdev.ecodes import BTN_LEFT, BTN_TASK

from linmbc.actions import ActionRunner
from linmbc.config import load_config, save_config
from linmbc.devices import MouseNode
from linmbc.engine import ButtonRecord, latency_seconds
from linmbc.keys import name_of
from linmbc.profile import Action, Profile, ProfileError, load, match_title


class Grab(Protocol):
    node: MouseNode

    def fileno(self) -> int: ...
    def pump(self) -> list[ButtonRecord]: ...
    def tick(self) -> None: ...
    def next_deadline(self) -> float | None: ...
    def set_actions(self, actions: dict[int, Action]) -> None: ...
    def close(self) -> None: ...


class Service:
    def __init__(
        self,
        *,
        config_path: Path,
        profiles_dir: Path,
        find_mice: Callable[[], list[MouseNode]],
        grab_factory: Callable[[MouseNode, ActionRunner, Any], Grab],
        sink_factory: Callable[[], Any],
        on_log: Callable[[str], None],
        on_button: Callable[[str, str, int], None],
        on_change: Callable[[], None] = lambda: None,
    ) -> None:
        self._config_path = config_path
        self._profiles_dir = profiles_dir
        self._find_mice = find_mice
        self._grab_factory = grab_factory
        self._sink_factory = sink_factory
        self._log = on_log
        self._on_button = on_button
        self._on_change = on_change
        self._config = load_config(config_path)
        self._profiles: dict[str, Profile] = {}
        self._window: tuple[str, str, str] = ("", "", "")  # class, name, title
        self._active = ""  # profile in effect right now
        self._grabs: dict[str, Grab] = {}
        self._detected: list[MouseNode] = []
        self._sink: Any = None

    # --- lifecycle -------------------------------------------------------

    def start(self) -> None:
        self.reload_profiles()
        self._sync(force_notify=True)

    def shutdown(self) -> None:
        self._release_all()
        if self._sink is not None:
            self._sink.close()
            self._sink = None

    # --- commands --------------------------------------------------------

    def set_enabled(self, enabled: bool) -> None:
        self._update_config(enabled=enabled)
        self._log("remapping enabled" if enabled else "remapping disabled")
        self._sync(force_notify=True)

    def set_default_profile(self, name: str) -> None:
        if name and name not in self._profiles:
            raise ValueError(f"unknown profile: {name!r}")
        self._update_config(default_profile=name)
        self._log(f"default profile: {name or '(none)'}")
        self._choose_profile(reapply=False)

    def set_active_window(self, window_class: str, resource_name: str, title: str = "") -> None:
        """Called by the KWin script when another window gets focus or its title changes."""
        window = (window_class, resource_name, title)
        if window == self._window:
            return
        self._window = window
        self._choose_profile(reapply=False)

    def reload_profiles(self) -> None:
        profiles: dict[str, Profile] = {}
        for path in sorted(self._profiles_dir.glob("*.toml")):
            try:
                profile = load(path)
            except (ProfileError, OSError) as exc:
                self._log(f"skipping profile {exc}")
                continue
            if profile.name in profiles:
                self._log(f"skipping {path.name}: duplicate profile name {profile.name!r}")
                continue
            profiles[profile.name] = profile
        self._profiles = profiles
        self._log(f"profiles loaded: {', '.join(profiles) or 'none'}")
        default = self._config.default_profile
        if default and default not in profiles:
            self._log(f"default profile {default!r} not found; buttons pass through unchanged")
        self._choose_profile(reapply=True)

    def rescan(self) -> None:
        """Called periodically: picks up replugged mice, drops vanished ones."""
        self._sync(force_notify=False)

    # --- events ----------------------------------------------------------

    def fds(self) -> list[int]:
        return [grab.fileno() for grab in self._grabs.values()]

    def on_ready(self, fd: int) -> None:
        key = next((k for k, g in self._grabs.items() if g.fileno() == fd), None)
        if key is None:
            return
        grab = self._grabs[key]
        try:
            records = grab.pump()
        except OSError as exc:
            self._log(f"{grab.node.name}: device lost ({exc}); waiting for it to come back")
            self._drop(key)
            self._on_change()
            return
        except Exception as exc:  # noqa: BLE001 - fail open on anything unexpected
            self._fail_open(exc)
            return
        for record in records:
            self._report(grab.node, record)

    def tick(self) -> None:
        """Run timed taps that are due (the daemon calls this at next_deadline())."""
        try:
            for grab in list(self._grabs.values()):
                grab.tick()
        except OSError:
            self.rescan()  # a mouse went away mid-loop; rescan drops it
        except Exception as exc:  # noqa: BLE001 - fail open on anything unexpected
            self._fail_open(exc)

    def next_deadline(self) -> float | None:
        deadlines = [d for g in self._grabs.values() if (d := g.next_deadline()) is not None]
        return min(deadlines, default=None)

    # --- state for the GUI -------------------------------------------------

    def state(self) -> dict[str, Any]:
        return {
            "enabled": self._config.enabled,
            "default_profile": self._config.default_profile,
            "active_profile": self._active,
            "window_class": self._window[0],
            "window_title": self._window[2],
            "profiles": [{"name": p.name, "match": list(p.match)} for p in self._profiles.values()],
            # what the user thinks of as "the mouse": detected (grabbed or not), minus
            # the mouse function of keyboards, which is grabbed but not configured here
            "mice": [node.name for node in self._pointing_devices()],
            "buttons": [name_of(code) for code in self._detected_buttons()],
        }

    # --- internals ---------------------------------------------------------

    def _update_config(self, **changes: Any) -> None:
        self._config = dataclasses.replace(self._config, **changes)
        save_config(self._config, self._config_path)

    def _pointing_devices(self) -> list[MouseNode]:
        return [node for node in self._detected if not node.on_keyboard]

    def _detected_buttons(self) -> list[int]:
        """Mouse buttons (BTN_LEFT..BTN_TASK) any detected mouse declares, in code order."""
        mice = self._pointing_devices()
        codes = set().union(*(node.keys for node in mice)) if mice else set()
        return sorted(c for c in codes if BTN_LEFT <= c <= BTN_TASK)

    def _profile_for_window(self) -> str:
        window_class, resource_name, title = self._window
        names = {n.lower() for n in (window_class, resource_name) if n}
        title = title.strip().lower()
        by_class = ""
        for profile in self._profiles.values():
            for entry in profile.match:
                wanted = match_title(entry)
                if wanted is None:
                    if not by_class and entry.lower() in names:
                        by_class = profile.name
                elif wanted and wanted.lower() == title:
                    return profile.name
        if by_class:
            return by_class
        default = self._config.default_profile
        return default if default in self._profiles else ""

    def _actions(self) -> dict[int, Action]:
        profile = self._profiles.get(self._active)
        return dict(profile.buttons) if profile else {}

    def _choose_profile(self, *, reapply: bool) -> None:
        """Pick the profile for the focused window; always tells the GUI.

        Actions are swapped only when the profile changes or was reloaded, so a
        running loop survives focus moving between windows of the same profile.
        """
        chosen = self._profile_for_window()
        changed = chosen != self._active
        if changed:
            window = self._window[0] or "(no window)"
            self._log(f"window {window} -> profile {chosen or '(none: buttons unchanged)'}")
        self._active = chosen
        if changed or reapply:
            self._apply_actions()
        self._on_change()

    def _apply_actions(self) -> None:
        actions = self._actions()
        for grab in self._grabs.values():
            grab.set_actions(actions)  # also writes releases of loops that stop

    def _sync(self, *, force_notify: bool) -> None:
        before = (tuple(self._grabs), tuple(n.key for n in self._detected))
        self._detected = self._find_mice()
        present = {node.key: node for node in self._detected}
        wanted = present if self._config.enabled else {}
        for key in [k for k in self._grabs if k not in wanted]:
            self._drop(key)
        for key, node in wanted.items():
            if key not in self._grabs:
                self._open(node)
        after = (tuple(self._grabs), tuple(n.key for n in self._detected))
        if force_notify or before != after:
            self._on_change()

    def _open(self, node: MouseNode) -> None:
        if self._sink is None:
            self._sink = self._sink_factory()
        runner = ActionRunner(self._actions())
        try:
            grab = self._grab_factory(node, runner, self._sink)
        except OSError as exc:
            self._log(f"{node.name}: cannot grab {node.path} ({exc})")
            return
        self._grabs[node.key] = grab
        self._log(f"{node.name}: grabbed {node.path}")

    def _drop(self, key: str) -> None:
        grab = self._grabs.pop(key)
        with contextlib.suppress(OSError):  # device may already be unplugged
            grab.close()
        self._log(f"{grab.node.name}: released")

    def _release_all(self) -> None:
        for key in list(self._grabs):
            try:
                self._drop(key)
            except Exception as exc:  # noqa: BLE001 - keep releasing the others
                self._log(f"error releasing {key}: {exc!r}")

    def _fail_open(self, exc: Exception) -> None:
        self._log(f"unexpected error, releasing every mouse and disabling: {exc!r}")
        self._release_all()
        self._update_config(enabled=False)
        self._on_change()

    def _report(self, node: MouseNode, record: ButtonRecord) -> None:
        source = name_of(record.source)
        self._on_button(node.key, source, record.value)
        if record.output == [(record.source, record.value)]:
            return  # unmapped button: not logged, a left click per line would flood it
        state = "down" if record.value else "up"
        output = ", ".join(f"{name_of(c)} {'down' if v else 'up'}" for c, v in record.output)
        latency_ms = latency_seconds(record.timestamp) * 1000
        profile = self._active or "no profile"
        self._log(f"{source} {state} -> {output or '(nothing)'} [{profile}] {latency_ms:.2f} ms")
