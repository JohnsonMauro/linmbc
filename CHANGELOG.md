# Changelog

## 0.1.0a2 — games that share a window class

- Profiles also match the focused window's title, and a title match wins
  over a class match. Lutris/umu games without a umu id all get the window
  class `steam_app_default` (their launcher too); a profile matching
  `Diablo IV` now tells that game apart. Tested with Diablo IV through
  Lutris (Battle.net, GE-Proton).
- "Add profile" lists the windows focused since LinMBC started: pick one and
  the match is filled in (the title for `steam_app_default`, else the class).
- Fix: restarting the service while a mouse button was held left that button
  stuck on the desktop (menus and panel stopped reacting until the next
  click). A mouse is now grabbed only once every button is up.

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
