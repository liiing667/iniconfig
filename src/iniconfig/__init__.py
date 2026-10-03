"""brain-dead simple parser for ini-style files.
(C) Ronny Pfannschmidt, Holger Krekel -- MIT licensed
"""

import os
from collections.abc import Callable
from collections.abc import Iterator
from collections.abc import Mapping
from typing import Final
from typing import TextIO
from typing import TypeVar
from typing import overload

__all__ = ["IniConfig", "ParseError", "COMMENTCHARS", "iscommentline"]

from . import _parse
from ._parse import COMMENTCHARS
from ._parse import ParsedLine
from ._parse import iscommentline
from .exceptions import ParseError

_D = TypeVar("_D")
_T = TypeVar("_T")


def _serialize_key(name: str, value: str) -> list[str]:
    """Serialize a single key/value pair to ini lines.

    Raises ValueError for values that cannot be represented without
    silently losing information (e.g. blank lines inside a value).
    """
    if not isinstance(value, str):
        raise TypeError(
            f"value for key {name!r} must be str, got {type(value).__name__}"
        )
    if "\r" in value:
        raise ValueError(
            f"value for key {name!r} contains a carriage return"
            " and cannot be written safely"
        )
    parts = value.split("\n")
    first = parts[0]
    lines = [f"{name} = {first}" if first else f"{name} ="]
    for part in parts[1:]:
        if not part.strip():
            raise ValueError(
                f"value for key {name!r} contains a blank line"
                " and cannot be written safely"
            )
        lines.append(f"    {part}")
    return lines


def _blank_or_comment_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if not line.strip() or iscommentline(line)]


class SectionWrapper:
    config: Final["IniConfig"]
    name: Final[str]

    def __init__(self, config: "IniConfig", name: str) -> None:
        self.config = config
        self.name = name

    def lineof(self, name: str) -> int | None:
        return self.config.lineof(self.name, name)

    @overload
    def get(self, key: str) -> str | None: ...

    @overload
    def get(
        self,
        key: str,
        convert: Callable[[str], _T],
    ) -> _T | None: ...

    @overload
    def get(
        self,
        key: str,
        default: None,
        convert: Callable[[str], _T],
    ) -> _T | None: ...

    @overload
    def get(self, key: str, default: _D, convert: None = None) -> str | _D: ...

    @overload
    def get(
        self,
        key: str,
        default: _D,
        convert: Callable[[str], _T],
    ) -> _T | _D: ...

    # TODO: investigate possible mypy bug wrt matching the passed over data
    def get(  # type: ignore [misc]
        self,
        key: str,
        default: _D | None = None,
        convert: Callable[[str], _T] | None = None,
    ) -> _D | _T | str | None:
        return self.config.get(self.name, key, convert=convert, default=default)

    def __getitem__(self, key: str) -> str:
        return self.config.sections[self.name][key]

    def __iter__(self) -> Iterator[str]:
        section: Mapping[str, str] = self.config.sections.get(self.name, {})

        def lineof(key: str) -> int:
            return self.config.lineof(self.name, key)  # type: ignore[return-value]

        yield from sorted(section, key=lineof)

    def items(self) -> Iterator[tuple[str, str]]:
        for name in self:
            yield name, self[name]


class IniConfig:
    path: Final[str]
    sections: Final[Mapping[str, Mapping[str, str]]]
    _sources: Final[Mapping[tuple[str, str | None], int]]
    _raw: Final[str | None]
    _strip_inline_comments: Final[bool]
    _strip_section_whitespace: Final[bool]
    _original_sections: Final[Mapping[str, Mapping[str, str]]]

    def __init__(
        self,
        path: str | os.PathLike[str],
        data: str | None = None,
        encoding: str = "utf-8",
        *,
        _sections: Mapping[str, Mapping[str, str]] | None = None,
        _sources: Mapping[tuple[str, str | None], int] | None = None,
        _raw: str | None = None,
        _strip_inline_comments: bool = False,
        _strip_section_whitespace: bool = False,
    ) -> None:
        self.path = os.fspath(path)

        # Determine sections and sources
        if _sections is not None and _sources is not None:
            # Use provided pre-parsed data (called from parse())
            sections_data = _sections
            sources = _sources
            raw: str | None = _raw
        else:
            # Parse the data (backward compatible path)
            if data is None:
                with open(self.path, encoding=encoding) as fp:
                    data = fp.read()

            # Use old behavior (no stripping) for backward compatibility
            sections_data, sources = _parse.parse_ini_data(
                self.path, data, strip_inline_comments=False
            )
            raw = data

        # Assign once to Final attributes
        self._sources = sources
        self.sections = sections_data
        self._raw = raw
        self._strip_inline_comments = _strip_inline_comments
        self._strip_section_whitespace = _strip_section_whitespace
        self._original_sections = {
            section: dict(values) for section, values in sections_data.items()
        }

    @classmethod
    def parse(
        cls,
        path: str | os.PathLike[str],
        data: str | None = None,
        encoding: str = "utf-8",
        *,
        strip_inline_comments: bool = True,
        strip_section_whitespace: bool = False,
    ) -> "IniConfig":
        """Parse an INI file.

        Args:
            path: Path to the INI file (used for error messages)
            data: Optional INI content as string. If None, reads from path.
            encoding: Encoding to use when reading the file (default: utf-8)
            strip_inline_comments: Whether to strip inline comments from values
                (default: True). When True, comments starting with # or ; are
                removed from values, matching the behavior for section comments.
            strip_section_whitespace: Whether to strip whitespace from section and key names
                (default: False). When True, strips Unicode whitespace from section and key names,
                addressing issue #4. When False, preserves existing behavior for backward compatibility.

        Returns:
            IniConfig instance with parsed configuration

        Example:
            # With comment stripping (default):
            config = IniConfig.parse("setup.cfg")
            # value = "foo" instead of "foo # comment"

            # Without comment stripping (old behavior):
            config = IniConfig.parse("setup.cfg", strip_inline_comments=False)
            # value = "foo # comment"

            # With section name stripping (opt-in for issue #4):
            config = IniConfig.parse("setup.cfg", strip_section_whitespace=True)
            # section names and keys have Unicode whitespace stripped
        """
        fspath = os.fspath(path)

        if data is None:
            with open(fspath, encoding=encoding) as fp:
                data = fp.read()

        sections_data, sources = _parse.parse_ini_data(
            fspath,
            data,
            strip_inline_comments=strip_inline_comments,
            strip_section_whitespace=strip_section_whitespace,
        )

        # Call constructor with pre-parsed sections and sources
        return cls(
            path=fspath,
            _sections=sections_data,
            _sources=sources,
            _raw=data,
            _strip_inline_comments=strip_inline_comments,
            _strip_section_whitespace=strip_section_whitespace,
        )

    def dump(self) -> str:
        """Return the current configuration as ini text.

        Unchanged sections and entries are emitted from the original text,
        so comments, blank lines and key order are preserved. Changed or
        added entries are serialized in a form the parser reads back to the
        same values.

        Raises ValueError if the current data cannot be represented without
        information loss (e.g. a value with a bare newline that the parser
        would drop); no file is written in that case.
        """
        lines = self._render_lines()
        newline = (
            "\r\n"
            if self._raw is not None and "\r\n" in self._raw
            else "\n"
        )
        text = newline.join(lines)
        if self._raw is None:
            if text:
                text += newline
        elif self._raw.endswith(("\n", "\r")):
            text += newline
        self._verify_roundtrip(text)
        return text

    def write(self, fp: TextIO) -> None:
        """Write the current configuration to an open text file object."""
        fp.write(self.dump())

    def _render_lines(self) -> list[str]:
        current = self.sections
        original = self._original_sections

        if self._raw is None:
            return self._render_fresh()

        lines = self._raw.splitlines()
        tokens = _parse.parse_lines(
            self.path,
            self._raw.splitlines(True),
            strip_inline_comments=self._strip_inline_comments,
            strip_section_whitespace=self._strip_section_whitespace,
        )

        # Each token owns the raw lines from its own line up to the next token.
        regions: list[tuple[int, int, ParsedLine]] = []
        for index, token in enumerate(tokens):
            end = tokens[index + 1].lineno if index + 1 < len(tokens) else len(lines)
            regions.append((token.lineno, end, token))

        # Keys added to sections that already exist are appended at the end
        # of their section, i.e. right after the section's last entry.
        new_keys: dict[str, list[tuple[str, str]]] = {}
        insert_at: dict[str, int] = {}
        for start, end, token in regions:
            assert token.section is not None
            insert_at[token.section] = end
        for section, mapping in current.items():
            if section in original:
                added = [
                    (name, value)
                    for name, value in mapping.items()
                    if name not in original[section]
                ]
                if added:
                    new_keys[section] = added
        insert_points: dict[int, list[str]] = {}
        for section in new_keys:
            insert_points.setdefault(insert_at[section], []).append(section)

        out: list[str] = []
        pos = 0
        for start, end, token in regions:
            out.extend(lines[pos:start])
            pos = end
            assert token.section is not None
            section = token.section
            if token.name is None:
                if section in current:
                    # Existing section header (with comments/blanks below it).
                    out.extend(lines[start:end])
                else:
                    # Removed section: drop the header, keep loose comments.
                    out.extend(_blank_or_comment_lines(lines[start + 1 : end]))
            elif section in current and token.name in current[section]:
                value = current[section][token.name]
                untouched = (
                    section in original
                    and token.name in original[section]
                    and original[section][token.name] == value
                )
                if untouched:
                    out.extend(lines[start:end])
                else:
                    out.extend(_serialize_key(token.name, value))
                    out.extend(_blank_or_comment_lines(lines[start + 1 : end]))
            else:
                # Removed key: drop the key line and its continuations,
                # keep surrounding comments/blanks.
                out.extend(_blank_or_comment_lines(lines[start + 1 : end]))

            for new_section in insert_points.get(end, ()):
                for name, value in new_keys[new_section]:
                    out.extend(_serialize_key(name, value))

        # Lines after the last token (there are none for a valid file) and
        # leading content when no token exists (comments-only input).
        out.extend(lines[pos:])

        # Brand-new sections are appended at the end in iteration order.
        for section, mapping in current.items():
            if section not in original:
                out.append(f"[{section}]")
                for name, value in mapping.items():
                    out.extend(_serialize_key(name, value))

        return out

    def _render_fresh(self) -> list[str]:
        out: list[str] = []
        for section, mapping in self.sections.items():
            out.append(f"[{section}]")
            for name, value in mapping.items():
                out.extend(_serialize_key(name, value))
        return out

    def _verify_roundtrip(self, text: str) -> None:
        try:
            sections, _ = _parse.parse_ini_data(
                self.path,
                text,
                strip_inline_comments=self._strip_inline_comments,
                strip_section_whitespace=self._strip_section_whitespace,
            )
        except ParseError as error:
            raise ValueError(f"cannot safely write config: {error}") from error

        current = {section: dict(values) for section, values in self.sections.items()}
        if sections != current:
            raise ValueError(
                "cannot safely write config: serialized values would not round-trip"
            )

    def lineof(self, section: str, name: str | None = None) -> int | None:
        lineno = self._sources.get((section, name))
        return None if lineno is None else lineno + 1

    @overload
    def get(
        self,
        section: str,
        name: str,
    ) -> str | None: ...

    @overload
    def get(
        self,
        section: str,
        name: str,
        convert: Callable[[str], _T],
    ) -> _T | None: ...

    @overload
    def get(
        self,
        section: str,
        name: str,
        default: None,
        convert: Callable[[str], _T],
    ) -> _T | None: ...

    @overload
    def get(
        self, section: str, name: str, default: _D, convert: None = None
    ) -> str | _D: ...

    @overload
    def get(
        self,
        section: str,
        name: str,
        default: _D,
        convert: Callable[[str], _T],
    ) -> _T | _D: ...

    def get(  # type: ignore
        self,
        section: str,
        name: str,
        default: _D | None = None,
        convert: Callable[[str], _T] | None = None,
    ) -> _D | _T | str | None:
        try:
            value: str = self.sections[section][name]
        except KeyError:
            return default
        else:
            if convert is not None:
                return convert(value)
            else:
                return value

    def __getitem__(self, name: str) -> SectionWrapper:
        if name not in self.sections:
            raise KeyError(name)
        return SectionWrapper(self, name)

    def __iter__(self) -> Iterator[SectionWrapper]:
        for name in sorted(self.sections, key=self.lineof):  # type: ignore
            yield SectionWrapper(self, name)

    def __contains__(self, arg: str) -> bool:
        return arg in self.sections
