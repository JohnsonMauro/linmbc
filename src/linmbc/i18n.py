"""Interface translations: one JSON catalog per language in linmbc/locales/.

English (en.json) is the source; every other catalog must carry the same keys
and the same {placeholders} (enforced by tests). The shipped set is the one
most ARPGs on Steam support (research 2026-10-07, see the roadmap).
"""

import json
import locale
import os
from functools import cache
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parent / "locales"
FLAGS_DIR = Path(__file__).resolve().parent / "flags"
SOURCE = "en"
AUTO = "auto"
LANGUAGES = {
    "en": "English",
    "pt_BR": "Português (Brasil)",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "ru": "Русский",
    "pl": "Polski",
    "ja": "日本語",
    "ko": "한국어",
    "zh_CN": "简体中文",
}


# Flag shown next to each language (flag-icons file name). English uses the US flag.
FLAGS = {
    "en": "us",
    "pt_BR": "br",
    "es": "es",
    "fr": "fr",
    "de": "de",
    "ru": "ru",
    "pl": "pl",
    "ja": "jp",
    "ko": "kr",
    "zh_CN": "cn",
}


def flag_path(code: str) -> Path:
    return FLAGS_DIR / f"{FLAGS[code]}.svg"


@cache
def catalog(code: str) -> dict[str, str]:
    return json.loads((LOCALES_DIR / f"{code}.json").read_text(encoding="utf-8"))


def system_locale() -> str:
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            return value
    return locale.getlocale()[0] or SOURCE


def resolve(setting: str, system: str) -> str:
    """'auto' follows the system locale ('pt_BR.UTF-8' -> 'pt_BR', 'pt_PT' -> 'pt_BR')."""
    if setting != AUTO:
        return setting if setting in LANGUAGES else SOURCE
    tag = system.split(".")[0].split("@")[0].replace("-", "_")
    if tag in LANGUAGES:
        return tag
    base = tag.split("_")[0]
    for code in LANGUAGES:
        if code.split("_")[0] == base:
            return code
    return SOURCE


_language = SOURCE


def set_language(code: str) -> None:
    global _language
    _language = code if code in LANGUAGES else SOURCE


def language() -> str:
    return _language


def tr(key: str, **fields: object) -> str:
    """Text for `key` in the current language, falling back to English, then the key."""
    text = catalog(_language).get(key) or catalog(SOURCE).get(key) or key
    return text.format(**fields) if fields else text
