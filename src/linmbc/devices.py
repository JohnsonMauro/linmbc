"""Find physical mouse event nodes from sysfs, without opening any device node.

Classification reads sysfs capability bitmaps only, so keyboard nodes are never
opened. A node is a mouse when it has BTN_LEFT + REL_X/REL_Y and declares no
keyboard keys (codes below BTN_MISC other than KEY_UNKNOWN). uinput devices
(including LinMBC's own output) are skipped.
"""

from dataclasses import dataclass
from pathlib import Path

SYSFS_ROOT = Path("/sys")
BTN_MISC = 0x100
BTN_LEFT = 0x110
KEY_UNKNOWN = 240
KEYBOARD_LETTERS = {16, 30, 44, 57}  # KEY_Q, KEY_A, KEY_Z, KEY_SPACE
REL_X, REL_Y = 0, 1


@dataclass(frozen=True)
class MouseNode:
    path: str
    name: str
    vendor: str
    product: str
    keys: frozenset[int]
    # The mouse function of a keyboard (shares its HID device with a full keyboard,
    # e.g. Keychron K8). Still grabbed, but not "the mouse" the user configures.
    on_keyboard: bool = False

    @property
    def usb_id(self) -> str:
        return f"{self.vendor}:{self.product}"

    @property
    def key(self) -> str:
        """Stable identity across boots and replugs (eventN numbers are not)."""
        return f"{self.usb_id}:{self.name}"


def _bits(text: str) -> set[int]:
    """Decode a sysfs capability bitmap (64-bit words, most significant first)."""
    value = 0
    for word in text.split():
        value = (value << 64) | int(word, 16)
    return {bit for bit in range(value.bit_length()) if value >> bit & 1}


def _read(path: Path) -> str:
    return path.read_text().strip() if path.exists() else ""


def _classify(event_dir: Path) -> MouseNode | None:
    dev = event_dir / "device"
    if "/virtual/" in str(dev.resolve()):
        return None
    keys = _bits(_read(dev / "capabilities/key"))
    rels = _bits(_read(dev / "capabilities/rel"))
    if BTN_LEFT not in keys or not {REL_X, REL_Y} <= rels:
        return None
    if any(code < BTN_MISC and code != KEY_UNKNOWN for code in keys):
        return None
    return MouseNode(
        path=f"/dev/input/{event_dir.name}",
        name=_read(dev / "name"),
        vendor=_read(dev / "id/vendor"),
        product=_read(dev / "id/product"),
        keys=frozenset(keys),
        on_keyboard=_shares_hid_with_keyboard(dev.resolve()),
    )


def _shares_hid_with_keyboard(input_dir: Path) -> bool:
    """True when another input of the same HID device has letter keys (a real keyboard).

    Heuristic verified on a Keychron K8 (mouse keys live next to the keyboard) and a
    WLMOUSE receiver (its macro keyboard is a separate HID device) — 2026-10-07.
    """
    for sibling in input_dir.parent.glob("input*"):
        if sibling != input_dir and _bits(_read(sibling / "capabilities/key")) >= KEYBOARD_LETTERS:
            return True
    return False


def find_mice(match: str | None = None, *, sysfs_root: Path = SYSFS_ROOT) -> list[MouseNode]:
    """Physical mice, optionally filtered by "vvvv:pppp" or a name substring."""
    event_dirs = sorted((sysfs_root / "class/input").glob("event*"))
    mice = [node for node in map(_classify, event_dirs) if node is not None]
    if match:
        needle = match.lower()
        mice = [m for m in mice if needle == m.usb_id or needle in m.name.lower()]
    return mice
