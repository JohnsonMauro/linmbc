"""Render the GUI for the website: main window and button dialog, one PNG per language.

    QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME=kde \\
        .venv/bin/python scripts/gui_screenshots.py OUT_DIR

Offscreen, against a fake daemon and throwaway profiles, so no real device,
path or log line ends up in a picture. With the KDE platform theme and the
Breeze style the pictures match the app on Plasma (Breeze Dark here).
"""

import sys
import tempfile
from pathlib import Path

from evdev import ecodes as e
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from linmbc import i18n
from linmbc.games import Game
from linmbc.gui.main_window import MainWindow
from linmbc.gui.mapping_dialog import MappingDialog
from linmbc.gui.settings import GuiSettings
from linmbc.profile import Action, Delay, Mode, Profile
from linmbc.profile_store import ProfileStore

BUTTONS = ["BTN_LEFT", "BTN_RIGHT", "BTN_MIDDLE", "BTN_SIDE", "BTN_EXTRA"]
# Generic game profiles: the website shows no real game names or app ids.
WINDOW = "steam_app_…"
# Generic device name: no real mouse model in the pictures.
MOUSE = "Gaming Mouse"
GAME_NAMES = {
    "en": ("Game A", "Game B"),
    "pt_BR": ("Jogo A", "Jogo B"),
    "es": ("Juego A", "Juego B"),
    "fr": ("Jeu A", "Jeu B"),
    "de": ("Spiel A", "Spiel B"),
    "ru": ("Игра A", "Игра B"),
    "pl": ("Gra A", "Gra B"),
    "ja": ("ゲーム A", "ゲーム B"),
    "ko": ("게임 A", "게임 B"),
    "zh_CN": ("游戏 A", "游戏 B"),
}
LOOP = Action((e.KEY_LEFTCTRL, e.KEY_2), Mode.TOGGLE, delay=Delay(80, 140))


class FakeDaemon(QObject):
    """The DaemonClient surface MainWindow uses, with nothing behind it."""

    state_changed = Signal(dict)
    log_line = Signal(str)
    button = Signal(str, str, int)
    available_changed = Signal(bool)
    error = Signal(str)

    def is_available(self) -> bool:
        return True

    def refresh(self) -> None: ...

    def set_enabled(self, enabled: bool) -> None: ...

    def set_default_profile(self, name: str) -> None: ...

    def reload_profiles(self) -> None: ...

    def quit_daemon(self) -> None: ...

    def start_daemon(self) -> bool:
        return True


def sample_store(directory: Path, game: str, other: str) -> ProfileStore:
    store = ProfileStore(directory)
    store.save(Profile("Default"))
    store.save(
        Profile(
            game,
            (WINDOW,),
            {
                e.BTN_SIDE: Action((e.KEY_Q,)),
                e.BTN_EXTRA: LOOP,
                e.BTN_MIDDLE: Action((e.KEY_R,), Mode.REPEAT, count=3, delay=Delay(50, 50)),
            },
        )
    )
    store.save(Profile(other, (WINDOW,)))
    return store


def render(app: QApplication, language: str, out: Path) -> None:
    i18n.set_language(language)
    game, other = GAME_NAMES[language]
    daemon = FakeDaemon()
    tmp = Path(tempfile.mkdtemp(prefix="linmbc-shots-"))
    win = MainWindow(
        daemon,
        sample_store(tmp / "profiles", game, other),
        GuiSettings(language=language),
        tmp / "gui.toml",
        games=lambda: [Game(game, (WINDOW,))],
    )
    daemon.state_changed.emit(
        {
            "enabled": True,
            "default_profile": "Default",
            "active_profile": game,
            "window_class": WINDOW,
            "profiles": ["Default", game, other],
            "mice": [MOUSE],
            "buttons": BUTTONS,
            "log_path": "",
        }
    )
    win._fill_profiles(select=game)
    win.resize(980, 430)
    win.show()
    app.processEvents()
    win.grab().save(str(out / f"main-{language}.png"))

    dialog = MappingDialog(e.BTN_EXTRA, LOOP)
    dialog.show()
    app.processEvents()
    dialog.grab().save(str(out / f"mapping-{language}.png"))
    dialog.close()
    win.close()


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv[:1])
    app.setStyle("Breeze")
    for language in i18n.LANGUAGES:
        render(app, language, out)
        print(f"{language}: main-{language}.png, mapping-{language}.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
