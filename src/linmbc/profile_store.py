"""The profiles directory as the GUI sees it: list, create, edit, rename, delete."""

import re
from dataclasses import dataclass
from pathlib import Path

from linmbc.profile import Profile, ProfileError, load, save


def slug(name: str) -> str:
    text = "".join(ch if ch.isalnum() else "-" for ch in name.lower())
    return re.sub(r"-+", "-", text).strip("-") or "profile"


@dataclass(frozen=True)
class _Entry:
    path: Path
    profile: Profile


class ProfileStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def list(self) -> dict[str, Profile]:
        """Valid profiles by name, sorted; broken files are skipped (the daemon logs them)."""
        return {name: entry.profile for name, entry in sorted(self._scan().items())}

    def save(self, profile: Profile, previous_name: str | None = None) -> Path:
        entries = self._scan()
        if previous_name is not None and previous_name in entries:
            if profile.name != previous_name and profile.name in entries:
                raise ValueError(f"profile {profile.name!r} already exists")
            path = entries[previous_name].path
        else:
            if profile.name in entries:
                raise ValueError(f"profile {profile.name!r} already exists")
            path = self._free_path(slug(profile.name))
        save(profile, path)
        return path

    def delete(self, name: str) -> None:
        self._scan()[name].path.unlink()

    def _scan(self) -> dict[str, _Entry]:
        entries: dict[str, _Entry] = {}
        for path in sorted(self.directory.glob("*.toml")):
            try:
                profile = load(path)
            except (ProfileError, OSError):
                continue
            entries.setdefault(profile.name, _Entry(path, profile))
        return entries

    def _free_path(self, stem: str) -> Path:
        path = self.directory / f"{stem}.toml"
        n = 2
        while path.exists():
            path = self.directory / f"{stem}-{n}.toml"
            n += 1
        return path
