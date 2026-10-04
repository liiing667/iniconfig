"""Serialization of ini entries back to text.

The helpers here only emit text that the parser in :mod:`._parse` reads
back to the exact same keys and values.  Anything that cannot be
represented safely raises :exc:`ValueError` instead of silently
producing a broken file.
"""

from ._parse import COMMENTCHARS

# line boundary characters recognized by str.splitlines() other than "\n"
_LINE_BOUNDARIES = frozenset("\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029")


def serialize_entry(name: str, value: str) -> list[str]:
    """Serialize a key/value pair to physical lines, each ending in "\\n".

    Multi-line values are written using indented continuation lines.

    Raises:
        ValueError: If the key or value cannot be written in a way that
            parses back to the exact same key and value.
    """
    validate_key(name)
    _check_line_boundaries(value, f"value for {name!r}")
    if "\n" not in value:
        _validate_value_line(name, value, allow_empty=True)
        return [f"{name} = {value}\n"]
    first, *continuations = value.split("\n")
    _validate_value_line(name, first, allow_empty=False)
    lines = [f"{name} = {first}\n"]
    for continuation in continuations:
        _validate_value_line(name, continuation, allow_empty=False)
        if continuation[:1] in COMMENTCHARS:
            raise ValueError(
                f"value for {name!r} has a continuation line starting with "
                f"{continuation[0]!r} which would be read back as a comment"
            )
        lines.append(f"    {continuation}\n")
    return lines


def validate_key(name: str) -> None:
    """Ensure a key can be written so that it parses back unchanged."""
    if not name:
        raise ValueError("empty keys cannot be written safely")
    if "\n" in name:
        raise ValueError(f"key contains a newline: {name!r}")
    _check_line_boundaries(name, f"key {name!r}")
    if name != name.strip():
        raise ValueError(
            f"key has leading/trailing whitespace which would be lost: {name!r}"
        )
    if name[:1] in COMMENTCHARS:
        raise ValueError(f"key starts with a comment character: {name!r}")
    if name[:1] == "[":
        raise ValueError(f"key starts with '[' and would read as a section: {name!r}")
    if "=" in name or ":" in name:
        raise ValueError(f"key contains a name/value delimiter: {name!r}")


def validate_section_name(name: str) -> None:
    """Ensure a section name can be written so that it parses back unchanged."""
    if not name:
        raise ValueError("empty section names cannot be written safely")
    if "\n" in name:
        raise ValueError(f"section name contains a newline: {name!r}")
    _check_line_boundaries(name, f"section name {name!r}")
    for char in COMMENTCHARS:
        if char in name:
            raise ValueError(f"section name contains a comment character: {name!r}")


def _validate_value_line(name: str, line: str, *, allow_empty: bool) -> None:
    if not line and not allow_empty:
        raise ValueError(
            f"value for {name!r} contains an empty line which would be lost "
            "when reading the value back"
        )
    if line != line.strip():
        raise ValueError(
            f"value for {name!r} has a line with leading/trailing whitespace "
            f"which would be lost when reading the value back: {line!r}"
        )


def _check_line_boundaries(text: str, what: str) -> None:
    if any(char in _LINE_BOUNDARIES for char in text):
        raise ValueError(f"{what} contains unsupported line boundary characters")
