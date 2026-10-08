# CLAUDE.md — LinMBC

Project-level instructions for Claude Code. Read before editing.

## What this is

Linux take on X-Mouse Button Control: per-application mouse button remapping,
Wayland first, KDE Plasma as the first target. Main use case: switching button
layouts between ARPG games (Steam/Proton) without editing config by hand.

Personal repo (`JohnsonMauro/linmbc`). Drafts, roadmap and scratch live
outside the clone in `../linmbc.local-context/` — never commit them and never
reference them from tracked code.

## Decisions (2026-10-07)

| Topic | Decision |
|---|---|
| Language | Python + `python-evdev` for the engine |
| GUI | PySide6 (Qt), fits KDE |
| Profile switching | automatic by focused window: the daemon loads [`kwin/focus.js`](src/linmbc/kwin/focus.js) at runtime through `org.kde.KWin /Scripting` (no package install); it calls `SetActiveWindow(class, name, title)`, again when the focused window's title changes. Profile `match` entries are compared to class, name and whole title, any case; a title match wins over a class match (2026-10-08: Lutris/umu games without a umu id all get class `steam_app_default`, Battle.net launcher included); `title:<text>` compares the title only; else the `Default` profile. "Add profile" lists the windows focused since the daemon started (in memory, never logged) and fills the match: the title for `steam_app_default`, else the class. Manual override (tray / hotkey) later |
| Actions | per button: keys + mode `hold` / `once` / `toggle` (loop until clicked again) / `repeat` N, delay fixed or random `[min, max]` ms (decided with the user 2026-10-07). Shift layers and sequences later |
| Process model | daemon (systemd user service) separate from the GUI, so mappings survive the GUI closing |
| Profiles | TOML, one file per application, in `~/.config/linmbc/profiles/`. Read with `tomllib`, written by a small own serializer (no dependency) |
| GUI ↔ daemon | D-Bus session bus (also what the KWin script will call). Daemon: `dbus-python` + GLib main loop, no Qt (verified working 2026-10-07). GUI: QtDBus as a client only. API in [`src/linmbc/dbus_api.py`](src/linmbc/dbus_api.py) |
| Failure policy | fail-open: unexpected error → release every grab and disable, so the mouse goes back to normal; unplugged mouse → dropped, re-grabbed when it returns (2 s rescan). A mouse with a button down is not grabbed until every button is up (retried at the rescan): the press already reached the compositor, and a grabbed release would leave the desktop with that button stuck (seen 2026-10-08 restarting the service mid-click) |
| Dependencies | runtime from system packages (`python-evdev`, `pyside6`); dev tools (pytest, pytest-qt, ruff) in `.venv` created with `--system-site-packages` |
| Virtual output | two uinput devices: a mouse (buttons + rel axes) and a keyboard (all keys), so the compositor classifies each normally |
| Device support | any evdev mouse (relative pointer + buttons). Every physical mouse is grabbed automatically — no device picker (user: "the other macro tool just knows the mouse", 2026-10-07). Several mice and hotplug handled |
| Languages | GUI in en, pt-BR, es, fr, de, ru, pl, ja, ko, zh-CN: the set ≥4 of 7 ARPGs ship on Steam (store API, 2026-10-07). JSON catalogs in `src/linmbc/locales/`; machine-translated, native review pending. Picker shows SVG flags vendored from lipis/flag-icons v7.5.0 (MIT, `src/linmbc/flags/`); English = US flag |
| Games | "Add profile" lists installed Steam games (`libraryfolders.vdf` + `appmanifest_*.acf`); match `steam_app_<appid>` |
| Buttons sent as keyboard keys (Razer Naga keypad, firmware-programmed buttons) | opt-in per device only — see Security rules |
| License | MIT (user, 2026-10-07). `pyproject.toml` declares it (PEP 639, setuptools ≥77) with the vendored flag-icons licence |
| Distribution | Target: desktop distros with a graphical session. Only Arch/CachyOS is packaged and tested (`packaging/arch/PKGBUILD`, builds the committed HEAD of the checkout). Other distros stay pending until tested in a real environment |
| Daemon start | systemd user unit `linmbc.service` (`Type=dbus`, `WantedBy=graphical-session.target`). The GUI runs `systemctl --user --no-block start linmbc.service` and falls back to spawning `sys.executable -m linmbc.daemon` (source checkout) |
| Why not xremap | it covers the engine, but switching layouts per game means editing YAML and restarting; the point here is a GUI + quick profile switching |

## Security rules

- By default the daemon grabs **mouse nodes only**. Never open keyboard event
  nodes by default — that is keylogger-level access.
- Device access comes from [`packaging/udev/70-linmbc.rules`](packaging/udev/70-linmbc.rules)
  (`uaccess` on `ID_INPUT_MOUSE` nodes that are not also `ID_INPUT_KEYBOARD`).
  Do not tell users to join the `input` group.
- **Exception (decided 2026-10-07), opt-in per device:** the user may enable the
  keyboard interface of the *same physical device* as a mouse (same USB parent),
  e.g. a Naga side keypad. Rules:
  - Never automatic, never a standalone keyboard. The GUI asks per device and
    names the node it will read.
  - The warning must say that on combo receivers (e.g. Logitech Unifying with a
    keyboard paired) that interface can be a real keyboard, and every key typed
    on it passes through the daemon.
  - Access is a separate generated udev rule scoped to that vendor:product,
    removable from the GUI. The base rule never grants keyboard nodes.
- Macros and turbo send several inputs per press; the GUI must warn that online
  games may forbid them (ToS). Plain 1:1 remaps carry no such warning.

## Dev machine facts (verified 2026-10-07)

- CachyOS, KDE Plasma 6.7.5 on Wayland (KWin 6.7.5), Python 3.14.7,
  `python-evdev` 2.0.0, PySide6 6.11.2 on Qt 6.12.0 (system packages).
- Steam library `~/.local/share/Steam`; Last Epoch is appid 899770.
- Mouse: WLMOUSE Mini Pro 8K receiver, USB `36a7:a868`. Not Logitech, so
  Solaar/HID++ does not apply.
  - `/dev/input/event8` is the pointer. Its key bitmap declares `BTN_LEFT`,
    `BTN_RIGHT`, `BTN_MIDDLE`, `BTN_SIDE`, `BTN_EXTRA` plus `KEY_UNKNOWN` (240),
    so udev tags it `ID_INPUT_KEY=1` as well as `ID_INPUT_MOUSE=1`. Pressing
    confirmed all five arrive on `event8` (nothing on the keyboard interface);
    `BTN_SIDE` is the rear side button, `BTN_EXTRA` the front one.
  - The Keychron K8 keyboard exposes a separate mouse node (8 buttons,
    `ID_INPUT_MOUSE=1`) on the same HID device as its full keyboard. The daemon
    grabs it (passthrough) but flags it `on_keyboard` and leaves it out of the
    GUI's mouse name and button rows. The WLMOUSE's own keyboard interface is a
    separate HID device, so it is not flagged.
  - The receiver also exposes a "Keyboard" interface (`event11`), likely used
    by on-board macros. Do not grab it; it is a keyboard.
  - Event node numbers change between boots — match devices by name/vendor/
    product, never by `eventN`.
- `/dev/uinput` already has a user ACL (write OK). Mouse event nodes are
  `root:input 660` until the udev rule above is installed.

## Commands

```bash
python3 -m venv --system-site-packages .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest            # tests, no device access needed
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/linmbc-daemon     # runs in the foreground; Ctrl+C releases every mouse
.venv/bin/linmbc            # GUI; starts linmbc.service if installed, else spawns the checkout
cd packaging/arch && makepkg -si   # Arch package from the committed HEAD
```

With the package installed, the GUI starts the packaged daemon: stop
`linmbc.service` before running a checkout's daemon. `makepkg` rewrites
`pkgver=` in the PKGBUILD; do not commit that change.

## Layout

| Module | Role |
|---|---|
| `devices` | find physical mice from sysfs (never opens a node) |
| `keys`, `keynames` | evdev names/combos; friendly names ("Ctrl+2") for the GUI |
| `remap`, `actions` | hold remap with ref-counted outputs; timed modes as a pure state machine (`now` passed in) |
| `profile`, `profile_store`, `config`, `tomlw` | TOML files: profiles (`Action` per button), daemon state |
| `engine` | frame translator, uinput sinks, `GrabbedMouse` (`tick`/`next_deadline` for timed taps) |
| `service` | grab policy, profile per focused window, fail-open, rescan — tested with fakes |
| `daemon`, `dbus_api`, `kwin/focus.js` | D-Bus + GLib loop (fd watches, tap timer), KWin focus script |
| `games` | installed Steam games |
| `i18n`, `locales/` | translations |
| `keycapture`, `gui/` | GUI: QtDBus client, main window, mapping/game dialogs, settings |

GUI facts (verified 2026-10-07, KDE Plasma Wayland, PySide6 6.11.2):
- `QKeyEvent.nativeScanCode() - 8` is the evdev code, layout-independent.
  Keys grabbed by global shortcuts never reach the window — keep the key list.
- PySide6 QtDBus: signal `connect()` needs `SLOT("name(types)")`; `asyncCall()`
  takes no arguments, use `asyncCallWithArgumentList()`.
- Keys field: "+" joins keys pressed together; a part that is not a key name is
  split into its characters pressed together ("er" = E+R, as in X-Mouse Button
  Control). A key name wins over its letters ("end" = End; "E+N+D" for letters).
  The "?" next to the field explains this. Sequences (one key after another)
  are not supported yet.
- The GUI shows one row per button of the detected mouse (no "add button").
  `BTN_LEFT` can be configured only in game profiles, never in `Default`
  (outside games the desktop would lose its click).
- Profile order is GUI-only (`~/.config/linmbc/gui.toml`, drag and drop);
  `Default` is pinned on top. Removing a profile asks for confirmation.
- dbus-python picks one signature for overloaded methods: KWin `loadScript`
  needs `signature="ss"`. Anything failing while loading the script only turns
  automatic switching off — it must never take the daemon down.

- GUI tests run offscreen (`tests/conftest.py` sets `QT_QPA_PLATFORM`).
- Tests never create a virtual keyboard: anything written to it would type
  into the real session. Use fakes for the sink.
- Daemon files: config `~/.config/linmbc/config.toml`, profiles
  `~/.config/linmbc/profiles/*.toml`, log `~/.local/state/linmbc/daemon.log`
  (all honour `XDG_*`, which is how to run an isolated instance).

## Phases

1. **Spike** (scripts outside the clone): udev access, button/wheel codes done.
   Grab/latency/crash-release are now tested through the first playable slice.
2. **Daemon:** profiles + the four action types, with tests. First slice
   (2026-10-07): button → key/combo only, manual profile, log file, together
   with a minimal GUI so it can be tried in a game.
3. **KWin script + D-Bus:** done (2026-10-07). Verified in Last Epoch: the
   window reports `steam_app_899770` and remapped keys reach the game.
4. **GUI + tray.**
5. **Packaging:** Arch package done (2026-10-07): udev rule, systemd user
   service, .desktop, icon, licences; `makepkg` + `check()` verified in a
   scratch clone. Not yet: installing it with pacman and a login with the
   service enabled; packages for other distros.

Detailed roadmap: `../linmbc.local-context/roadmap/roadmap.md`.
