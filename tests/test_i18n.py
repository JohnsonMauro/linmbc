import re
import string

import pytest

from linmbc import i18n

FIELD = re.compile(r"\{(\w+)\}")


def fields(text):
    return sorted(name for _, name, _, _ in string.Formatter().parse(text) if name)


def test_every_language_has_a_catalog():
    for code in i18n.LANGUAGES:
        assert (i18n.LOCALES_DIR / f"{code}.json").exists(), code


@pytest.mark.parametrize("code", [c for c in i18n.LANGUAGES if c != i18n.SOURCE])
def test_catalog_matches_english_keys_and_placeholders(code):
    source = i18n.catalog(i18n.SOURCE)
    other = i18n.catalog(code)
    assert set(other) == set(source), set(other) ^ set(source)
    for key, text in source.items():
        assert fields(other[key]) == fields(text), (code, key)
        assert other[key].strip(), (code, key)


@pytest.mark.parametrize(
    ("setting", "system", "expected"),
    [
        ("auto", "pt_BR.UTF-8", "pt_BR"),
        ("auto", "pt_PT.UTF-8", "pt_BR"),
        ("auto", "es_AR.UTF-8", "es"),
        ("auto", "zh_CN.UTF-8", "zh_CN"),
        ("auto", "zh_TW.UTF-8", "zh_CN"),
        ("auto", "de_DE@euro", "de"),
        ("auto", "C", "en"),
        ("auto", "it_IT.UTF-8", "en"),
        ("ja", "pt_BR.UTF-8", "ja"),
        ("xx", "pt_BR.UTF-8", "en"),
    ],
)
def test_resolve(setting, system, expected):
    assert i18n.resolve(setting, system) == expected


def test_tr_formats_and_falls_back():
    i18n.set_language("pt_BR")
    try:
        assert i18n.tr("toggle.on") == "Ligado"
        assert i18n.tr("mode.repeat", count=3) == "Repetir 3 vezes"
        assert i18n.tr("no.such.key") == "no.such.key"
    finally:
        i18n.set_language("en")


def test_every_key_the_code_uses_exists_in_english():
    from pathlib import Path

    from evdev import ecodes

    from linmbc.gui.mapping_dialog import MODES
    from linmbc.keys import name_of

    source = i18n.catalog(i18n.SOURCE)
    code = "\n".join(p.read_text() for p in Path(i18n.__file__).parent.rglob("*.py"))
    used = set(re.findall(r'tr\(\s*"([a-z_.]+)"', code))
    used |= set(re.findall(r'"((?:dialog|toggle|mapping|mode|profiles?)\.[a-z_]+)"', code))
    # any button a detected mouse may report gets a row, so every one needs a label
    used |= {f"button.{name_of(c)}" for c in range(ecodes.BTN_LEFT, ecodes.BTN_TASK + 1)}
    used |= {f"mode.{m.value}" for m in MODES} | {f"mode.{m.value}_label" for m in MODES}
    used |= {f"mapping.col_{c}" for c in ("button", "keys", "mode", "delay")}
    missing = sorted(k for k in used if k not in source)
    assert missing == []


def test_every_language_has_a_flag_file():
    for code in i18n.LANGUAGES:
        path = i18n.flag_path(code)
        assert path.is_file(), code
        assert path.read_text().lstrip().startswith("<svg"), code


def test_flags_are_plain_svg_without_scripts_or_external_links():
    for code in i18n.LANGUAGES:
        text = i18n.flag_path(code).read_text().lower()
        assert "<script" not in text and "http://" not in text.replace("http://www.w3.org/", ""), (
            code
        )
