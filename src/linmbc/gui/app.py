"""`linmbc` entry point: the GUI. Closing it leaves the daemon (and remapping) running."""

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from linmbc import i18n
from linmbc.gui.client import DaemonClient
from linmbc.gui.main_window import LOGO, MainWindow
from linmbc.gui.settings import load_settings, settings_path
from linmbc.profile import profiles_dir
from linmbc.profile_store import ProfileStore


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("LinMBC")
    app.setDesktopFileName("linmbc")  # Wayland app id: matches packaging/linmbc.desktop
    app.setWindowIcon(QIcon(str(LOGO)))
    settings = load_settings(settings_path())
    i18n.set_language(i18n.resolve(settings.language, i18n.system_locale()))
    client = DaemonClient()
    if not client.is_available():
        client.start_daemon()  # the window updates itself when the service appears
    window = MainWindow(client, ProfileStore(profiles_dir()), settings, settings_path())
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
