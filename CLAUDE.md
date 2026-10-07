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
| Profile switching | automatic by focused window (KWin script → D-Bus) **and** manual override (tray / hotkey) |
| Actions | button → key/combo, shift layers, turbo, macros — implemented in that order |
| Process model | daemon (systemd user service) separate from the GUI, so mappings survive the GUI closing |
| Profiles | plain text files, one per application |
| Why not xremap | it covers the engine, but switching layouts per game means editing YAML and restarting; the point here is a GUI + quick profile switching |

## Security rules

- The daemon grabs **mouse devices only**. Never open keyboard event nodes —
  that is keylogger-level access.
- Device access comes from [`packaging/udev/70-linmbc.rules`](packaging/udev/70-linmbc.rules)
  (`uaccess` on `ID_INPUT_MOUSE` only). Do not tell users to join the `input`
  group.
- Macros and turbo send several inputs per press; the GUI must warn that online
  games may forbid them (ToS). Plain 1:1 remaps carry no such warning.

## Dev machine facts (verified 2026-10-07)

- CachyOS, KDE Plasma on Wayland, Python 3.14.7, `python-evdev` 2.0.0 (system
  package). PySide6 not installed yet.
- Mouse: WLMOUSE Mini Pro 8K receiver, USB `36a7:a868`. Not Logitech, so
  Solaar/HID++ does not apply.
  - `/dev/input/event8` is the pointer. Its key bitmap declares `BTN_LEFT`,
    `BTN_RIGHT`, `BTN_MIDDLE`, `BTN_SIDE`, `BTN_EXTRA` (decoded from
    `/proc/bus/input/devices`, not yet confirmed by pressing).
  - The receiver also exposes a "Keyboard" interface (`event11`), likely used
    by on-board macros. Do not grab it; it is a keyboard.
  - Event node numbers change between boots — match devices by name/vendor/
    product, never by `eventN`.
- `/dev/uinput` already has a user ACL (write OK). Mouse event nodes are
  `root:input 660` until the udev rule above is installed.

## Phases

1. **Spike:** read button codes, grab the mouse, re-emit through uinput,
   measure added latency. Blocked on installing the udev rule (needs sudo).
2. **Daemon:** profiles + the four action types, with tests.
3. **KWin script + D-Bus:** automatic switching by window class (check what
   Proton games report — expected `steam_app_<id>`, unverified).
4. **GUI + tray.**
5. **Packaging:** udev rule, systemd user service, install docs.

Detailed roadmap: `../linmbc.local-context/roadmap/roadmap.md`.
