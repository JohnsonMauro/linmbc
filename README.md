<p align="center"><img src="src/linmbc/icons/linmbc.svg" width="112" alt="LinMBC logo"></p>

# LinMBC

Per-application mouse button remapping for Linux (Wayland first), inspired by
[X-Mouse Button Control](https://www.highrez.co.uk/downloads/xmousebuttoncontrol.htm)
for Windows.

LinMBC is an independent project and is not affiliated with Highrez.

> **Status:** early development. Nothing to install yet.

## Goals

- Remap mouse buttons per application, switching profiles automatically when
  the focused window changes (e.g. a different layout per ARPG), with a manual
  override from the tray or a hotkey.
- Actions: button → key/combo, shift layers (hold a button to change what the
  others do), turbo (repeat while held), and macros/sequences.
- A GUI profile editor: press the button you want to remap, pick the action.
- Works on Wayland. KDE Plasma is the first target.

## How it works (planned)

```
mouse ──evdev──▶ linmbc daemon ──uinput──▶ virtual device ──▶ compositor/apps
                     ▲
     KWin script ────┘ (D-Bus: active window class → profile)
                     ▲
     Qt GUI / tray ──┘ (edit profiles, override active profile)
```

- The daemon grabs **only mouse devices** and never reads keyboards.
- Profiles are plain text files, one per application.

## A note on games

Remapping one button to another key is a 1:1 input change. Macros and turbo
send several inputs per press, which some online games forbid in their terms of
service. Check the rules of the game before using them.

## License

Not chosen yet.
