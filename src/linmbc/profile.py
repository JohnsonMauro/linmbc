"""Profiles: one TOML file per application.

    name = "Path of Exile 2"
    match = ["steam_app_2694490"]

    [buttons]
    BTN_SIDE = "KEY_1"                       # shorthand: hold, like a plain remap
    BTN_EXTRA = { keys = "KEY_LEFTCTRL+KEY_2", mode = "repeat", count = 5, delay_ms = [100, 900] }

Modes: hold (key follows the button), once (one tap per click; delay = how
long it stays down), toggle (tap every delay until clicked again), repeat
(count taps, delay apart; clicking again cancels). delay_ms is a number or a
[min, max] range sampled for every tap.
"""

import os
import random
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from linmbc.keys import code_of, format_combo, is_button, name_of, parse_combo
from linmbc.tomlw import toml_str, toml_str_list, write_atomic

Combo = tuple[int, ...]

DEFAULT_DELAY_MS = 50
MIN_TIMED_DELAY_MS = 10  # a tap shorter than this is easy for games to miss
MAX_DELAY_MS = 60_000
MAX_COUNT = 1000


class ProfileError(ValueError):
    pass


class Mode(StrEnum):
    HOLD = "hold"
    ONCE = "once"
    TOGGLE = "toggle"
    REPEAT = "repeat"


@dataclass(frozen=True)
class Delay:
    low_ms: int = DEFAULT_DELAY_MS
    high_ms: int = DEFAULT_DELAY_MS

    @property
    def is_random(self) -> bool:
        return self.low_ms != self.high_ms

    def sample(self, rng: random.Random) -> float:
        """Seconds; uniform in [low, high] when it is a range."""
        if not self.is_random:
            return self.low_ms / 1000
        return rng.uniform(self.low_ms, self.high_ms) / 1000


@dataclass(frozen=True)
class Action:
    keys: Combo
    mode: Mode = Mode.HOLD
    count: int = 1  # taps per click, REPEAT only
    delay: Delay = Delay()

    @property
    def sends_several_inputs(self) -> bool:
        """Turbo/macro-like: games with strict ToS may forbid these."""
        return self.mode in (Mode.TOGGLE, Mode.REPEAT)


@dataclass(frozen=True)
class Profile:
    name: str
    match: tuple[str, ...] = ()
    buttons: Mapping[int, Action] = field(default_factory=dict)


def profiles_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "linmbc" / "profiles"


# --- reading -----------------------------------------------------------------


def loads(text: str) -> Profile:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"invalid TOML: {exc}") from exc

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ProfileError("profile needs a non-empty 'name'")
    match = data.get("match", [])
    if not isinstance(match, list) or not all(isinstance(m, str) for m in match):
        raise ProfileError("'match' must be a list of strings")
    return Profile(name=name, match=tuple(match), buttons=_parse_buttons(data.get("buttons", {})))


def _parse_buttons(table: object) -> dict[int, Action]:
    if not isinstance(table, dict):
        raise ProfileError("'buttons' must be a table")
    buttons: dict[int, Action] = {}
    for source, value in table.items():
        try:
            code = code_of(source)
            if not is_button(code):
                raise ValueError("source must be a mouse button (BTN_*)")
            buttons[code] = _parse_action(value)
        except ValueError as exc:
            raise ProfileError(f"buttons.{source}: {exc}") from exc
    return buttons


def _parse_action(value: object) -> Action:
    if isinstance(value, str):
        return Action(parse_combo(value))
    if not isinstance(value, dict):
        raise ValueError('expected "KEY_1" or { keys = "KEY_1", mode = ... }')
    unknown = set(value) - {"keys", "mode", "count", "delay_ms"}
    if unknown:
        raise ValueError(f"unknown field(s): {', '.join(sorted(unknown))}")
    keys = value.get("keys")
    if not isinstance(keys, str):
        raise ValueError('"keys" is required, like "KEY_LEFTCTRL+KEY_2"')
    try:
        mode = Mode(value.get("mode", Mode.HOLD))
    except ValueError:
        raise ValueError(f"mode must be one of: {', '.join(m.value for m in Mode)}") from None
    count = value.get("count", 1)
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= MAX_COUNT:
        raise ValueError(f"count must be a whole number from 1 to {MAX_COUNT}")
    delay = _parse_delay(value.get("delay_ms", DEFAULT_DELAY_MS), mode)
    return Action(parse_combo(keys), mode, count, delay)


def _parse_delay(value: object, mode: Mode) -> Delay:
    if isinstance(value, int) and not isinstance(value, bool):
        low = high = value
    elif (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(v, int) and not isinstance(v, bool) for v in value)
    ):
        low, high = value
    else:
        raise ValueError("delay_ms must be a number or [min, max]")
    minimum = 0 if mode is Mode.HOLD else MIN_TIMED_DELAY_MS
    if not minimum <= low <= high <= MAX_DELAY_MS:
        raise ValueError(f"delay_ms must satisfy {minimum} <= min <= max <= {MAX_DELAY_MS}")
    return Delay(low, high)


# --- writing -----------------------------------------------------------------


def _dump_action(action: Action) -> str:
    keys = toml_str(format_combo(action.keys))
    if action.mode is Mode.HOLD and action.delay == Delay():
        return keys
    fields = [f"keys = {keys}", f'mode = "{action.mode.value}"']
    if action.mode is Mode.REPEAT:
        fields.append(f"count = {action.count}")
    delay = action.delay
    delay_text = f"[{delay.low_ms}, {delay.high_ms}]" if delay.is_random else str(delay.low_ms)
    fields.append(f"delay_ms = {delay_text}")
    return "{ " + ", ".join(fields) + " }"


def dumps(profile: Profile) -> str:
    lines = [f"name = {toml_str(profile.name)}"]
    lines.append(f"match = {toml_str_list(profile.match)}")
    lines.append("")
    lines.append("[buttons]")
    for code, action in sorted(profile.buttons.items()):
        lines.append(f"{name_of(code)} = {_dump_action(action)}")
    return "\n".join(lines) + "\n"


def load(path: Path) -> Profile:
    try:
        return loads(path.read_text(encoding="utf-8"))
    except ProfileError as exc:
        raise ProfileError(f"{path}: {exc}") from exc


def save(profile: Profile, path: Path) -> None:
    write_atomic(path, dumps(profile))
