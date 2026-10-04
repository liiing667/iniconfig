"""brain-dead simple parser for ini-style files.
(C) Ronny Pfannschmidt, Holger Krekel -- MIT licensed
"""

import os
from collections.abc import Callable
from collections.abc import Iterator
from collections.abc import Mapping
from typing import IO
from typing import Final
from typing import TypeVar
from typing import overload

__all__ = ["IniConfig", "ParseError", "COMMENTCHARS", "iscommentline"]

from . import _parse
from . import _write
from ._parse import COMMENTCHARS
from ._parse import iscommentline
from .exceptions import ParseError

_D = TypeVar("_D")
_T = TypeVar("_T")


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
    _lines: Final[list[str]]
    _spans: Final[Mapping[tuple[str, str | None], tuple[int, int]]]
    _parsed_sections: Final[Mapping[str, Mapping[str, str]]]

    def __init__(
        self,
        path: str | os.PathLike[str],
        data: str | None = None,
        encoding: str = "utf-8",
        *,
        _sections: Mapping[str, Mapping[str, str]] | None = None,
        _sources: Mapping[tuple[str, str | None], int] | None = None,
        _lines: list[str] | None = None,
        _spans: Mapping[tuple[str, str | None], tuple[int, int]] | None = None,
    ) -> None:
        self.path = os.fspath(path)

        # Determine sections and sources
        if _sections is not None and _sources is not None:
            # Use provided pre-parsed data (called from parse())
            sections_data = _sections
            sources = _sources
            lines = _lines if _lines is not None else []
            spans = _spans if _spans is not None else {}
        else:
            # Parse the data (backward compatible path)
            if data is None:
                with open(self.path, encoding=encoding) as fp:
                    data = fp.read()

            # Use old behavior (no stripping) for backward compatibility
            sections_data, sources, spans = _parse.parse_ini_data(
                self.path, data, strip_inline_comments=False
            )
            lines = data.splitlines(True)

        # Assign once to Final attributes
        self._sources = sources
        self.sections = sections_data
        self._lines = lines
        self._spans = spans
        # snapshot of the parsed values, used to detect modifications on dump()
        self._parsed_sections = {
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

        sections_data, sources, spans = _parse.parse_ini_data(
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
            _lines=data.splitlines(True),
            _spans=spans,
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

    def dump(self) -> str:
        """Serialize the configuration back to ini text.

        Sections, keys, comments and blank lines that were not modified
        through the ``sections`` mapping are reproduced exactly as they
        were read, preserving order and formatting.  Changed, added or
        removed entries are re-serialized in place; keys added to an
        existing section are appended at the end of that section and new
        sections are appended at the end of the file.

        Returns:
            The configuration as ini text.

        Raises:
            ValueError: If a key, section name or value cannot be
                written in a way that parses back to the exact same
                data (for example values with leading/trailing
                whitespace, empty lines inside multi-line values, or
                continuation lines starting with a comment character).
        """
        lines = self._lines
        current = self.sections
        parsed = self._parsed_sections

        replacements: dict[int, list[str]] = {}
        skipped: set[int] = set()
        section_end: dict[str, int] = {}

        for (section, name), (start, end) in self._spans.items():
            section_end[section] = max(section_end.get(section, 0), end + 1)
            skipped.update(range(start, end + 1))
            if name is None:
                # section headers never change, keep them verbatim
                replacements[start] = lines[start : end + 1] if section in current else []
                continue
            values = current.get(section)
            if values is None or name not in values:
                # the key (or its whole section) was removed
                replacements[start] = []
            elif parsed[section][name] == values[name]:
                # unchanged entries are copied verbatim
                replacements[start] = lines[start : end + 1]
            else:
                replacements[start] = _write.serialize_entry(name, values[name])

        inserts: dict[int, list[str]] = {}
        for section, values in current.items():
            known = parsed.get(section)
            if known is None:
                continue  # brand-new sections are handled below
            added = [
                line
                for name, value in values.items()
                if name not in known
                for line in _write.serialize_entry(name, value)
            ]
            if added:
                pos = section_end.get(section, len(lines))
                inserts.setdefault(pos, []).extend(added)

        trailer: list[str] = []
        for section, values in current.items():
            if section in parsed:
                continue
            _write.validate_section_name(section)
            trailer.append(f"[{section}]\n")
            for name, value in values.items():
                trailer.extend(_write.serialize_entry(name, value))
        if trailer:
            inserts.setdefault(len(lines), []).extend(trailer)

        out: list[str] = []
        for pos in range(len(lines) + 1):
            pending = inserts.get(pos)
            if pending:
                if out and not out[-1].endswith("\n"):
                    out[-1] += "\n"
                out.extend(pending)
            if pos == len(lines):
                break
            replacement = replacements.get(pos)
            if replacement is not None:
                out.extend(replacement)
            elif pos not in skipped:
                out.append(lines[pos])
        return "".join(out)

    def write(self, fp: IO[str]) -> None:
        """Write the configuration to a text file object.

        This is a thin wrapper around :meth:`dump`, see its documentation
        for details on formatting guarantees and errors.

        Example:
            with open(config.path, "w", encoding="utf-8") as fp:
                config.write(fp)
        """
        fp.write(self.dump())

    def __iter__(self) -> Iterator[SectionWrapper]:
        for name in sorted(self.sections, key=self.lineof):  # type: ignore
            yield SectionWrapper(self, name)

    def __contains__(self, arg: str) -> bool:
        return arg in self.sections
