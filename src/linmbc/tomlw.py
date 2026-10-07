"""The little TOML writing LinMBC needs (reading uses the stdlib tomllib)."""

import json
from pathlib import Path


def toml_str(value: str) -> str:
    # JSON string escapes are a subset of TOML basic-string escapes.
    return json.dumps(value, ensure_ascii=False)


def toml_str_list(values: tuple[str, ...]) -> str:
    return "[" + ", ".join(toml_str(v) for v in values) + "]"


def write_atomic(path: Path, text: str) -> None:
    """A crash mid-write never leaves a half file behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
