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
LAST_EPOCH = Game("Last Epoch", ("steam_app_899770",))
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


def sample_store(directory: Path) -> ProfileStore:
    store = ProfileStore(directory)
    store.save(Profile("Default"))
    store.save(
        Profile(
            "Last Epoch",
            LAST_EPOCH.match,
            {
                e.BTN_SIDE: Action((e.KEY_Q,)),
                e.BTN_EXTRA: LOOP,
                e.BTN_MIDDLE: Action((e.KEY_R,), Mode.REPEAT, count=3, delay=Delay(50, 50)),
            },
        )
    )
    store.save(Profile("Path of Exile 2", ("steam_app_2694490",)))
    return store


def render(app: QApplication, language: str, out: Path) -> None:
    i18n.set_language(language)
    daemon = FakeDaemon()
    tmp = Path(tempfile.mkdtemp(prefix="linmbc-shots-"))
    win = MainWindow(
        daemon,
        sample_store(tmp / "profiles"),
        GuiSettings(language=language),
        tmp / "gui.toml",
        games=lambda: [LAST_EPOCH],
    )
    daemon.state_changed.emit(
        {
            "enabled": True,
            "default_profile": "Default",
            "active_profile": "Last Epoch",
            "window_class": LAST_EPOCH.match[0],
            "profiles": ["Default", "Last Epoch", "Path of Exile 2"],
            "mice": ["WLMOUSE Mini Pro 8K"],
            "buttons": BUTTONS,
            "log_path": "",
        }
    )
    win._fill_profiles(select="Last Epoch")
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
