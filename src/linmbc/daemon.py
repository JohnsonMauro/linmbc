"""linmbc-daemon: the Service on the session D-Bus, driven by a GLib main loop.

Run from a terminal for now (`linmbc-daemon` or `python -m linmbc.daemon`);
a systemd user unit comes with packaging. On KDE it loads a small KWin script
that reports the focused window, for automatic profile switching.
"""

import json
import logging
import logging.handlers
import os
import signal
import sys
import time
from pathlib import Path

import dbus
import dbus.service
import gi
from dbus.mainloop.glib import DBusGMainLoop

gi.require_version("GLibUnix", "2.0")
from gi.repository import GLib, GLibUnix  # noqa: E402

from linmbc import dbus_api as api  # noqa: E402
from linmbc.config import config_path  # noqa: E402
from linmbc.devices import find_mice  # noqa: E402
from linmbc.engine import GrabbedMouse, UInputSink  # noqa: E402
from linmbc.profile import profiles_dir  # noqa: E402
from linmbc.service import Service  # noqa: E402

RESCAN_SECONDS = 2
LOG_BYTES, LOG_BACKUPS = 1_000_000, 3
KWIN_SCRIPT = Path(__file__).resolve().parent / "kwin" / "focus.js"
KWIN_PLUGIN = "linmbc-focus"

log = logging.getLogger("linmbc")


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(base) / "linmbc"


class DaemonObject(dbus.service.Object):
    def __init__(self, bus_name: dbus.service.BusName, loop: GLib.MainLoop, log_path: Path):
        super().__init__(bus_name, api.OBJECT_PATH)
        self.service: Service | None = None
        self.after_call = lambda: None  # re-arms the tap timer after state changes
        self._loop = loop
        self._log_path = log_path

    def state_json(self) -> str:
        return json.dumps({**self.service.state(), "log_path": str(self._log_path)})

    @dbus.service.method(api.INTERFACE, in_signature="", out_signature="s")
    def GetState(self):
        return self.state_json()

    @dbus.service.method(api.INTERFACE, in_signature="b", out_signature="")
    def SetEnabled(self, enabled):
        self.service.set_enabled(bool(enabled))
        self.after_call()

    @dbus.service.method(api.INTERFACE, in_signature="s", out_signature="")
    def SetDefaultProfile(self, name):
        try:
            self.service.set_default_profile(str(name))
        except ValueError as exc:
            raise dbus.exceptions.DBusException(str(exc), name=api.ERROR_INVALID) from exc
        self.after_call()

    @dbus.service.method(api.INTERFACE, in_signature="sss", out_signature="")
    def SetActiveWindow(self, window_class, resource_name, title):
        self.service.set_active_window(str(window_class), str(resource_name), str(title))
        self.after_call()

    @dbus.service.method(api.INTERFACE, in_signature="", out_signature="")
    def ReloadProfiles(self):
        self.service.reload_profiles()
        self.after_call()

    @dbus.service.method(api.INTERFACE, in_signature="", out_signature="")
    def Quit(self):
        log.info("quit requested over D-Bus")
        self._loop.quit()

    @dbus.service.signal(api.INTERFACE, signature="s")
    def StateChanged(self, state):
        pass

    @dbus.service.signal(api.INTERFACE, signature="s")
    def Log(self, line):
        pass

    @dbus.service.signal(api.INTERFACE, signature="ssi")
    def Button(self, device_key, button, value):
        pass


class DBusLogHandler(logging.Handler):
    def __init__(self, obj: DaemonObject):
        super().__init__()
        self._obj = obj

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._obj.Log(self.format(record))
        except Exception:  # noqa: BLE001 - logging must never break the daemon
            self.handleError(record)


class TapTimer:
    """One GLib timeout armed for the Service's next timed tap (once/toggle/repeat)."""

    def __init__(self, service: Service):
        self._service = service
        self._source: int | None = None

    def rearm(self) -> None:
        if self._source is not None:
            GLib.source_remove(self._source)
            self._source = None
        deadline = self._service.next_deadline()
        if deadline is None:
            return
        delay_ms = max(0, round((deadline - time.monotonic()) * 1000))
        self._source = GLib.timeout_add(delay_ms, self._fire, priority=GLib.PRIORITY_HIGH)

    def _fire(self) -> bool:
        self._source = None
        self._service.tick()
        self.rearm()
        return GLib.SOURCE_REMOVE

    def clear(self) -> None:
        if self._source is not None:
            GLib.source_remove(self._source)
            self._source = None


class FdWatches:
    """Keeps one GLib watch per grabbed mouse fd, in step with the Service."""

    def __init__(self, service: Service, timer: TapTimer):
        self._service = service
        self._timer = timer
        self._sources: dict[int, int] = {}

    def sync(self) -> None:
        wanted = set(self._service.fds())
        for fd in [fd for fd in self._sources if fd not in wanted]:
            GLib.source_remove(self._sources.pop(fd))
        for fd in wanted - self._sources.keys():
            self._sources[fd] = GLib.io_add_watch(
                fd, GLib.PRIORITY_HIGH, GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, self._ready
            )

    def _ready(self, fd: int, _condition) -> bool:
        self._service.on_ready(fd)
        self._timer.rearm()
        return fd in self._sources  # False when on_ready dropped this mouse

    def clear(self) -> None:
        for source in self._sources.values():
            GLib.source_remove(source)
        self._sources.clear()


def kwin_scripting(bus: dbus.SessionBus) -> dbus.Interface | None:
    try:
        return dbus.Interface(
            bus.get_object("org.kde.KWin", "/Scripting"), "org.kde.kwin.Scripting"
        )
    except dbus.DBusException:
        return None


def load_kwin_script(bus: dbus.SessionBus) -> bool:
    """Load the focus reporter into KWin; False (logged) when KWin is not there."""
    scripting = kwin_scripting(bus)
    if scripting is None:
        log.warning("KWin not found on the session bus: automatic profile switching is off")
        return False
    try:
        scripting.unloadScript(KWIN_PLUGIN)
        # loadScript is overloaded (s) / (ss); dbus-python would pick the wrong one.
        scripting.loadScript(str(KWIN_SCRIPT), KWIN_PLUGIN, signature="ss")
        scripting.start()
    except Exception as exc:  # noqa: BLE001 - never let this take the daemon down
        log.warning("could not load the KWin script (%r): automatic switching is off", exc)
        return False
    log.info("KWin focus script loaded: profiles follow the focused window")
    return True


def unload_kwin_script(bus: dbus.SessionBus) -> None:
    scripting = kwin_scripting(bus)
    if scripting is not None:
        try:
            scripting.unloadScript(KWIN_PLUGIN)
        except Exception as exc:  # noqa: BLE001 - shutting down anyway
            log.warning("could not unload the KWin script: %r", exc)


def setup_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S")
    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=LOG_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
    )
    stderr_handler = logging.StreamHandler(sys.stderr)
    for handler in (file_handler, stderr_handler):
        handler.setFormatter(formatter)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


def main() -> int:
    log_path = state_dir() / "daemon.log"
    setup_logging(log_path)

    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    if bus.name_has_owner(api.BUS_NAME):
        log.error("another linmbc-daemon is already running")
        return 1
    bus_name = dbus.service.BusName(api.BUS_NAME, bus, do_not_queue=True)
    loop = GLib.MainLoop()
    obj = DaemonObject(bus_name, loop, log_path)

    dbus_handler = DBusLogHandler(obj)
    dbus_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
    log.addHandler(dbus_handler)

    watches: FdWatches | None = None

    def on_change() -> None:
        if watches is not None:
            watches.sync()
        obj.StateChanged(obj.state_json())

    service = Service(
        config_path=config_path(),
        profiles_dir=profiles_dir(),
        find_mice=find_mice,
        grab_factory=GrabbedMouse,
        sink_factory=UInputSink,
        on_log=log.info,
        on_button=lambda key, name, value: obj.Button(key, name, value),
        on_change=on_change,
    )
    obj.service = service
    timer = TapTimer(service)
    obj.after_call = timer.rearm
    watches = FdWatches(service, timer)

    def stop(*_args) -> bool:
        log.info("signal received, stopping")
        loop.quit()
        return GLib.SOURCE_REMOVE

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        GLibUnix.signal_add(GLib.PRIORITY_HIGH, sig, stop)

    def rescan() -> bool:
        service.rescan()
        return GLib.SOURCE_CONTINUE

    GLib.timeout_add_seconds(RESCAN_SECONDS, rescan)

    log.info("linmbc-daemon started (log: %s)", log_path)
    try:
        service.start()
        load_kwin_script(bus)
        loop.run()
    finally:
        unload_kwin_script(bus)
        timer.clear()
        watches.clear()
        service.shutdown()
        log.info("linmbc-daemon stopped; every mouse released")
    return 0


if __name__ == "__main__":
    sys.exit(main())
