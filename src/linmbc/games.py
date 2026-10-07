"""Installed games, to create a profile for one without typing its window class.

Steam (native and Flatpak): libraries from steamapps/libraryfolders.vdf, games
from appmanifest_<appid>.acf. A Proton game's window is expected to report the
class `steam_app_<appid>` (to be confirmed per game; the GUI shows the class of
the focused window so the match can be corrected).
"""

import re
from dataclasses import dataclass
from pathlib import Path

STEAM_ROOTS = [
    Path.home() / ".local/share/Steam",
    Path.home() / ".steam/steam",
    Path.home() / ".var/app/com.valvesoftware.Steam/data/Steam",
]
# Tools and runtimes Steam installs as "apps"; never something to play.
NOT_GAMES = re.compile(
    r"^(Proton\b|Steam Linux Runtime|Steamworks Common Redistributables|SteamVR\b)"
)
_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])')
_ESCAPE = re.compile(r"\\(.)")


@dataclass(frozen=True)
class Game:
    name: str
    match: tuple[str, ...]


def _unescape(text: str) -> str:
    return _ESCAPE.sub(lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), text)


def parse_vdf(text: str) -> dict:
    """Parse Valve's text KeyValues (quoted keys/values and braces). ValueError if broken."""
    stack: list[dict] = [{}]
    key: str | None = None
    for quoted, brace in _TOKEN.findall(text):
        if brace == "{":
            if key is None:
                raise ValueError("block without a key")
            child: dict = {}
            stack[-1][key] = child
            stack.append(child)
            key = None
        elif brace == "}":
            if len(stack) == 1:
                raise ValueError("unbalanced '}'")
            stack.pop()
        elif key is None:
            key = _unescape(quoted)
        else:
            stack[-1][key] = _unescape(quoted)
            key = None
    if len(stack) != 1:
        raise ValueError("unbalanced '{'")
    return stack[0]


def _read_vdf(path: Path) -> dict:
    try:
        return parse_vdf(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}


def _libraries(roots: list[Path]) -> list[Path]:
    seen: dict[Path, None] = {}
    for root in roots:
        if not (root / "steamapps").is_dir():
            continue
        seen.setdefault(root.resolve())
        folders = _read_vdf(root / "steamapps/libraryfolders.vdf").get("libraryfolders", {})
        for entry in folders.values() if isinstance(folders, dict) else []:
            path = entry.get("path") if isinstance(entry, dict) else None
            if path and Path(path, "steamapps").is_dir():
                seen.setdefault(Path(path).resolve())
    return list(seen)


def installed_steam_games(roots: list[Path] | None = None) -> list[Game]:
    games: dict[str, Game] = {}
    for library in _libraries(STEAM_ROOTS if roots is None else roots):
        for manifest in sorted((library / "steamapps").glob("appmanifest_*.acf")):
            state = _read_vdf(manifest).get("AppState", {})
            appid, name = state.get("appid"), state.get("name")
            if not (isinstance(appid, str) and appid.isdigit() and isinstance(name, str)):
                continue
            if NOT_GAMES.match(name):
                continue
            games[appid] = Game(name, (f"steam_app_{appid}",))
    return sorted(games.values(), key=lambda g: g.name.lower())
