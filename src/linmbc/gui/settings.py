"""GUI-only preferences (the daemon never reads them): ~/.config/linmbc/gui.toml."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from linmbc.config import config_dir
from linmbc.i18n import AUTO
from linmbc.tomlw import toml_str, toml_str_list, write_atomic


@dataclass(frozen=True)
class GuiSettings:
    language: str = AUTO
    profile_order: tuple[str, ...] = ()  # names as dragged in the list; others go last


def settings_path() -> Path:
    return config_dir() / "gui.toml"


def load_settings(path: Path) -> GuiSettings:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return GuiSettings()
    language = data.get("language", AUTO)
    order = data.get("profile_order", [])
    if not isinstance(order, list) or not all(isinstance(n, str) for n in order):
        order = []
    return GuiSettings(
        language=language if isinstance(language, str) else AUTO, profile_order=tuple(order)
    )


def save_settings(settings: GuiSettings, path: Path) -> None:
    write_atomic(
        path,
        f"language = {toml_str(settings.language)}\n"
        f"profile_order = {toml_str_list(settings.profile_order)}\n",
    )


def ordered(names: list[str], order: tuple[str, ...]) -> list[str]:
    """`names` sorted by the saved order; names not in it keep their order, at the end."""
    rank = {name: i for i, name in enumerate(order)}
    return sorted(names, key=lambda n: (rank.get(n, len(rank)), names.index(n)))
