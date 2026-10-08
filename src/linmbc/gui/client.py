"""QtDBus client for linmbc-daemon.

PySide6 specifics (verified 6.11.2, 2026-10-07): QDBusConnection.connect()
needs the slot wrapped in SLOT("name(types)"), and asyncCall() takes no extra
arguments, so calls go through asyncCallWithArgumentList().
"""

import json
import sys
from typing import Any

from PySide6.QtCore import SLOT, QObject, QProcess, Signal, Slot
from PySide6.QtDBus import (
    QDBusConnection,
    QDBusInterface,
    QDBusMessage,
    QDBusPendingCallWatcher,
    QDBusServiceWatcher,
)

from linmbc import dbus_api as api

SYSTEMD_UNIT = "linmbc.service"


def start_daemon() -> bool:
    """Start the daemon through its systemd user unit; without one (a source checkout),
    spawn it detached with this interpreter."""
    # --no-block: the unit is Type=dbus, so a blocking start would wait for the bus name.
    if QProcess.execute("systemctl", ["--user", "--no-block", "start", SYSTEMD_UNIT]) == 0:
        return True
    started, _pid = QProcess.startDetached(sys.executable, ["-m", "linmbc.daemon"])
    return bool(started)


class DaemonClient(QObject):
    state_changed = Signal(dict)
    log_line = Signal(str)
    button = Signal(str, str, int)  # device key, button name, value
    available_changed = Signal(bool)
    error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._bus = QDBusConnection.sessionBus()
        self._watcher = QDBusServiceWatcher(
            api.BUS_NAME, self._bus, QDBusServiceWatcher.WatchModeFlag.WatchForOwnerChange, self
        )
        self._watcher.serviceOwnerChanged.connect(self._owner_changed)
        for name, slot in (
            ("StateChanged", "_on_state(QString)"),
            ("Log", "_on_log(QString)"),
            ("Button", "_on_button(QString,QString,int)"),
        ):
            self._bus.connect(api.BUS_NAME, api.OBJECT_PATH, api.INTERFACE, name, self, SLOT(slot))
        self._pending: set[QDBusPendingCallWatcher] = set()

    # --- queries -----------------------------------------------------------

    def is_available(self) -> bool:
        return bool(self._bus.interface().isServiceRegistered(api.BUS_NAME).value())

    def refresh(self) -> None:
        reply = self._iface().call("GetState")
        if reply.type() == QDBusMessage.MessageType.ReplyMessage:
            self.state_changed.emit(json.loads(reply.arguments()[0]))
        else:
            self.error.emit(reply.errorMessage())

    # --- commands (async: the first enable blocks the daemon ~2 s) ----------

    def set_enabled(self, enabled: bool) -> None:
        self._call("SetEnabled", [enabled])

    def set_default_profile(self, name: str) -> None:
        self._call("SetDefaultProfile", [name])

    def reload_profiles(self) -> None:
        self._call("ReloadProfiles", [])

    def quit_daemon(self) -> None:
        self._call("Quit", [])

    def start_daemon(self) -> bool:
        return start_daemon()

    # --- internals ---------------------------------------------------------

    def _iface(self) -> QDBusInterface:
        return QDBusInterface(api.BUS_NAME, api.OBJECT_PATH, api.INTERFACE, self._bus)

    def _call(self, method: str, args: list[Any]) -> None:
        watcher = QDBusPendingCallWatcher(
            self._iface().asyncCallWithArgumentList(method, args), self
        )
        self._pending.add(watcher)
        watcher.finished.connect(self._call_finished)

    @Slot(QDBusPendingCallWatcher)
    def _call_finished(self, watcher: QDBusPendingCallWatcher) -> None:
        self._pending.discard(watcher)
        if watcher.isError():
            self.error.emit(watcher.error().message())
        watcher.deleteLater()

    @Slot(str, str, str)
    def _owner_changed(self, _name: str, _old: str, new: str) -> None:
        self.available_changed.emit(bool(new))
        if new:
            self.refresh()

    @Slot(str)
    def _on_state(self, state: str) -> None:
        self.state_changed.emit(json.loads(state))

    @Slot(str)
    def _on_log(self, line: str) -> None:
        self.log_line.emit(line)

    @Slot(str, str, int)
    def _on_button(self, device: str, name: str, value: int) -> None:
        self.button.emit(device, name, value)
