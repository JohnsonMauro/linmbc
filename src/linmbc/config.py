"""Daemon state that survives restarts: on/off and the profile used outside games."""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from linmbc.tomlw import toml_str, write_atomic


@dataclass(frozen=True)
class Config:
    enabled: bool = False
    default_profile: str = ""  # used when no game profile matches; "" = buttons unchanged


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "linmbc"


def config_path() -> Path:
    return config_dir() / "config.toml"


def load_config(path: Path) -> Config:
    """Any unreadable or ill-typed file yields the defaults (disabled = mouse untouched)."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return Config()
    enabled = data.get("enabled", False)
    default = data.get("default_profile", "")
    if not isinstance(enabled, bool) or not isinstance(default, str):
        return Config()
    return Config(enabled=enabled, default_profile=default)


def save_config(config: Config, path: Path) -> None:
    text = (
        f"enabled = {'true' if config.enabled else 'false'}\n"
        f"default_profile = {toml_str(config.default_profile)}\n"
    )
    write_atomic(path, text)
