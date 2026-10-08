# Changelog

## 0.1.0a1 — first alpha

First public build. Tested on CachyOS with KDE Plasma 6 (Wayland) and Last
Epoch through Steam/Proton.

- Remaps the buttons of any evdev mouse to keys or key combos, per game.
- Four click modes: hold, once, loop until clicked again, repeat N times;
  fixed or random delay.
- Profiles switch with the focused window on KDE Plasma (a KWin script loaded
  at runtime); the `Default` profile applies outside games.
- "Add profile" lists installed Steam games and fills in the window match.
- Every mouse grabbed automatically, several at once, with hotplug.
- Fail-open: any unexpected error releases every mouse.
- GUI in 10 languages (machine translated, review welcome).
- Arch package (`packaging/arch/PKGBUILD`): app, udev rule for mice only,
  systemd user service, menu entry and icon.

Known limits: other desktops get the `Default` profile only; other
distributions are not packaged or tested yet.
