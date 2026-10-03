from pathlib import Path
from textwrap import dedent

import pytest

from iniconfig import IniConfig
from iniconfig import ParseError
from iniconfig import __all__ as ALL
from iniconfig import iscommentline
from iniconfig._parse import ParsedLine as PL

check_tokens: dict[str, tuple[str, list[PL]]] = {
    "section": ("[section]", [PL(0, "section", None, None)]),
    "value": ("value = 1", [PL(0, None, "value", "1")]),
    "value in section": (
        "[section]\nvalue=1",
        [PL(0, "section", None, None), PL(1, "section", "value", "1")],
    ),
    "value with continuation": (
        "names =\n Alice\n Bob",
        [PL(0, None, "names", "Alice\nBob")],
    ),
    "value with aligned continuation": (
        "names = Alice\n        Bob",
        [PL(0, None, "names", "Alice\nBob")],
    ),
    "blank line": (
        "[section]\n\nvalue=1",
        [PL(0, "section", None, None), PL(2, "section", "value", "1")],
    ),
    "comment": ("# comment", []),
    "comment on value": ("value = 1", [PL(0, None, "value", "1")]),
    "comment on section": ("[section] #comment", [PL(0, "section", None, None)]),
    "comment2": ("; comment", []),
    "comment2 on section": ("[section] ;comment", [PL(0, "section", None, None)]),
    "pseudo section syntax in value": (
        "name = value []",
        [PL(0, None, "name", "value []")],
    ),
    "assignment in value": ("value = x = 3", [PL(0, None, "value", "x = 3")]),
    "use of colon for name-values": ("name: y", [PL(0, None, "name", "y")]),
    "use of colon without space": ("value:y=5", [PL(0, None, "value", "y=5")]),
    "equality gets precedence": ("value=xyz:5", [PL(0, None, "value", "xyz:5")]),
}


@pytest.fixture(params=sorted(check_tokens))
def input_expected(request: pytest.FixtureRequest) -> tuple[str, list[PL]]:
    return check_tokens[request.param]


@pytest.fixture
def input(input_expected: tuple[str, list[PL]]) -> str:
    return input_expected[0]


@pytest.fixture
def expected(input_expected: tuple[str, list[PL]]) -> list[PL]:
    return input_expected[1]


def parse(input: str) -> list[PL]:
    from iniconfig._parse import parse_lines

    return parse_lines("sample", input.splitlines(True))


def parse_a_error(input: str) -> ParseError:
    try:
        parse(input)
    except ParseError as e:
        return e
    else:
        raise ValueError(input)


def test_tokenize(input: str, expected: list[PL]) -> None:
    parsed = parse(input)
    assert parsed == expected


def test_parse_empty() -> None:
    parsed = parse("")
    assert not parsed
    ini = IniConfig("sample", "")
    assert not ini.sections


def test_ParseError() -> None:
    e = ParseError("filename", 0, "hello")
    assert str(e) == "filename:1: hello"


def test_continuation_needs_perceeding_token() -> None:
    err = parse_a_error(" Foo")
    assert err.lineno == 0


def test_continuation_cant_be_after_section() -> None:
    err = parse_a_error("[section]\n Foo")
    assert err.lineno == 1


def test_section_cant_be_empty() -> None:
    err = parse_a_error("[]")
    assert err.lineno == 0


@pytest.mark.parametrize(
    "line",
    [
        "!!",
    ],
)
def test_error_on_weird_lines(line: str) -> None:
    parse_a_error(line)


def test_iniconfig_from_file(tmp_path: Path) -> None:
    path = tmp_path / "test.txt"
    path.write_text("[metadata]\nname=1")

    config = IniConfig(path=str(path))
    assert list(config.sections) == ["metadata"]
    config = IniConfig(str(path), "[diff]")
    assert list(config.sections) == ["diff"]
    with pytest.raises(TypeError):
        IniConfig(data=path.read_text())  # type: ignore[call-arg]


def test_iniconfig_section_first() -> None:
    with pytest.raises(ParseError) as excinfo:
        IniConfig("x", data="name=1")
    assert excinfo.value.msg == "no section header defined"


def test_iniconig_section_duplicate_fails() -> None:
    with pytest.raises(ParseError) as excinfo:
        IniConfig("x", data="[section]\n[section]")
    assert "duplicate section" in str(excinfo.value)


def test_iniconfig_duplicate_key_fails() -> None:
    with pytest.raises(ParseError) as excinfo:
        IniConfig("x", data="[section]\nname = Alice\nname = bob")

    assert "duplicate name" in str(excinfo.value)


def test_iniconfig_lineof() -> None:
    config = IniConfig(
        "x.ini",
        data=("[section]\nvalue = 1\n[section2]\n# comment\nvalue =2"),
    )

    assert config.lineof("missing") is None
    assert config.lineof("section") == 1
    assert config.lineof("section2") == 3
    assert config.lineof("section", "value") == 2
    assert config.lineof("section2", "value") == 5

    assert config["section"].lineof("value") == 2
    assert config["section2"].lineof("value") == 5


def test_iniconfig_get_convert() -> None:
    config = IniConfig("x", data="[section]\nint = 1\nfloat = 1.1")
    assert config.get("section", "int") == "1"
    assert config.get("section", "int", convert=int) == 1


def test_iniconfig_get_missing() -> None:
    config = IniConfig("x", data="[section]\nint = 1\nfloat = 1.1")
    assert config.get("section", "missing", default=1) == 1
    assert config.get("section", "missing") is None


def test_section_get() -> None:
    config = IniConfig("x", data="[section]\nvalue=1")
    section = config["section"]
    assert section.get("value", convert=int) == 1
    assert section.get("value", 1) == "1"
    assert section.get("missing", 2) == 2


def test_missing_section() -> None:
    config = IniConfig("x", data="[section]\nvalue=1")
    with pytest.raises(KeyError):
        config["other"]


def test_section_getitem() -> None:
    config = IniConfig("x", data="[section]\nvalue=1")
    assert config["section"]["value"] == "1"
    assert config["section"]["value"] == "1"


def test_section_iter() -> None:
    config = IniConfig("x", data="[section]\nvalue=1")
    names = list(config["section"])
    assert names == ["value"]
    items = list(config["section"].items())
    assert items == [("value", "1")]


def test_config_iter() -> None:
    config = IniConfig(
        "x.ini",
        data=dedent(
            """
          [section1]
          value=1
          [section2]
          value=2
    """
        ),
    )
    sections = list(config)
    assert len(sections) == 2
    assert sections[0].name == "section1"
    assert sections[0]["value"] == "1"
    assert sections[1].name == "section2"
    assert sections[1]["value"] == "2"


def test_config_contains() -> None:
    config = IniConfig(
        "x.ini",
        data=dedent(
            """
          [section1]
          value=1
          [section2]
          value=2
    """
        ),
    )
    assert "xyz" not in config
    assert "section1" in config
    assert "section2" in config


def test_iter_file_order() -> None:
    config = IniConfig(
        "x.ini",
        data="""
[section2] #cpython dict ordered before section
value = 1
value2 = 2 # dict ordered before value
[section]
a = 1
b = 2
""",
    )
    sections_list = list(config)
    secnames = [x.name for x in sections_list]
    assert secnames == ["section2", "section"]
    assert list(config["section2"]) == ["value", "value2"]
    assert list(config["section"]) == ["a", "b"]


def test_example_pypirc() -> None:
    config = IniConfig(
        "pypirc",
        data=dedent(
            """
        [distutils]
        index-servers =
            pypi
            other

        [pypi]
        repository: <repository-url>
        username: <username>
        password: <password>

        [other]
        repository: http://example.com/pypi
        username: <username>
        password: <password>
    """
        ),
    )
    distutils, pypi, other = list(config)
    assert distutils["index-servers"] == "pypi\nother"
    assert pypi["repository"] == "<repository-url>"
    assert pypi["username"] == "<username>"
    assert pypi["password"] == "<password>"
    assert ["repository", "username", "password"] == list(other)


def test_api_import() -> None:
    assert ALL == ["IniConfig", "ParseError", "COMMENTCHARS", "iscommentline"]


@pytest.mark.parametrize(
    "line",
    [
        "#qwe",
        "  #qwe",
        ";qwe",
        " ;qwe",
    ],
)
def test_iscommentline_true(line: str) -> None:
    assert iscommentline(line)


def test_parse_strips_inline_comments() -> None:
    """Test that IniConfig.parse() strips inline comments from values by default."""
    config = IniConfig.parse(
        "test.ini",
        data=dedent(
            """
            [section1]
            name1 = value1 # this is a comment
            name2 = value2 ; this is also a comment
            name3 = value3# no space before comment
            list = a, b, c # some items
            """
        ),
    )
    assert config["section1"]["name1"] == "value1"
    assert config["section1"]["name2"] == "value2"
    assert config["section1"]["name3"] == "value3"
    assert config["section1"]["list"] == "a, b, c"


def test_parse_strips_inline_comments_from_continuations() -> None:
    """Test that inline comments are stripped from continuation lines."""
    config = IniConfig.parse(
        "test.ini",
        data=dedent(
            """
            [section]
            names =
                Alice # first person
                Bob ; second person
                Charlie
            """
        ),
    )
    assert config["section"]["names"] == "Alice\nBob\nCharlie"


def test_parse_preserves_inline_comments_when_disabled() -> None:
    """Test that IniConfig.parse(strip_inline_comments=False) preserves comments."""
    config = IniConfig.parse(
        "test.ini",
        data=dedent(
            """
            [section1]
            name1 = value1 # this is a comment
            name2 = value2 ; this is also a comment
            list = a, b, c # some items
            """
        ),
        strip_inline_comments=False,
    )
    assert config["section1"]["name1"] == "value1 # this is a comment"
    assert config["section1"]["name2"] == "value2 ; this is also a comment"
    assert config["section1"]["list"] == "a, b, c # some items"


def test_constructor_preserves_inline_comments_for_backward_compatibility() -> None:
    """Test that IniConfig() constructor preserves old behavior (no stripping)."""
    config = IniConfig(
        "test.ini",
        data=dedent(
            """
            [section1]
            name1 = value1 # this is a comment
            name2 = value2 ; this is also a comment
            """
        ),
    )
    assert config["section1"]["name1"] == "value1 # this is a comment"
    assert config["section1"]["name2"] == "value2 ; this is also a comment"


def test_unicode_whitespace_stripped() -> None:
    """Test that Unicode whitespace is stripped (issue #4)."""
    config = IniConfig(
        "test.ini",
        data="[section]\n"
        + "name1 = \u00a0value1\u00a0\n"  # NO-BREAK SPACE
        + "name2 = \u2000value2\u2000\n"  # EN QUAD
        + "name3 = \u3000value3\u3000\n",  # IDEOGRAPHIC SPACE
    )
    assert config["section"]["name1"] == "value1"
    assert config["section"]["name2"] == "value2"
    assert config["section"]["name3"] == "value3"


def test_unicode_whitespace_in_section_names_with_opt_in() -> None:
    """Test that Unicode whitespace can be stripped from section names with opt-in (issue #4)."""
    config = IniConfig.parse(
        "test.ini",
        data="[section\u00a0]\n"  # NO-BREAK SPACE at end
        + "key = value\n",
        strip_section_whitespace=True,
    )
    assert "section" in config
    assert config["section"]["key"] == "value"


def test_unicode_whitespace_in_key_names() -> None:
    """Test that Unicode whitespace is stripped from key names (issue #4)."""
    config = IniConfig(
        "test.ini",
        data="[section]\n" + "key\u00a0 = value\n",  # NO-BREAK SPACE after key
    )
    assert "key" in config["section"]
    assert config["section"]["key"] == "value"


ROUNDTRIP_DATA = (
    "# leading comment\n"
    "\n"
    "[section1] # comment\n"
    'key = "value with spaces"\n'
    "path = C:\\dir\\file\n"
    "hashy = #starts with hash\n"
    "semi = ;starts with semicolon\n"
    "names =\n"
    "    Alice\n"
    "    Bob\n"
    "\n"
    "; another comment\n"
    "[section2]\n"
    "empty =\n"
    "flag: yes\n"
)


def test_dump_unchanged_is_byte_identical() -> None:
    config = IniConfig("x.ini", data=ROUNDTRIP_DATA)
    assert config.dump() == ROUNDTRIP_DATA


def test_dump_roundtrip_values() -> None:
    config = IniConfig("x.ini", data=ROUNDTRIP_DATA)
    reparsed = IniConfig("y.ini", data=config.dump())
    assert reparsed.sections == config.sections
    assert reparsed.get("section1", "key") == '"value with spaces"'
    assert reparsed.get("section1", "path") == "C:\\dir\\file"
    assert reparsed.get("section1", "hashy") == "#starts with hash"
    assert reparsed.get("section1", "semi") == ";starts with semicolon"
    assert reparsed.get("section1", "names") == "Alice\nBob"


def test_write_roundtrip_via_file(tmp_path: Path) -> None:
    path = tmp_path / "config.ini"
    path.write_text(ROUNDTRIP_DATA, encoding="utf-8")
    config = IniConfig(str(path))
    with open(path, "w", encoding="utf-8") as fp:
        config.write(fp)
    reparsed = IniConfig(str(path))
    assert reparsed.sections == config.sections


def test_dump_modified_value_preserves_comments_and_order() -> None:
    data = (
        "[section]\n"
        "# a comment\n"
        "a = 1\n"
        "b = 2 # trailing\n"
        "\n"
        "[other]\n"
        "c = 3\n"
    )
    config = IniConfig("x.ini", data=data)
    config.sections["section"]["a"] = "changed"  # type: ignore[index]
    out = config.dump()
    assert "# a comment" in out
    assert "b = 2 # trailing" in out
    assert "a = changed" in out
    # key order is preserved
    assert out.index("a = changed") < out.index("b = 2")
    assert out.index("[section]") < out.index("[other]")
    reparsed = IniConfig("y.ini", data=out)
    assert reparsed.sections == config.sections
    assert reparsed.get("section", "a") == "changed"
    assert reparsed.get("section", "b") == "2 # trailing"


def test_dump_modified_multiline_value() -> None:
    config = IniConfig("x.ini", data="[s]\nnames =\n    Alice\n    Bob\n")
    config.sections["s"]["names"] = "Carol\nDave"  # type: ignore[index]
    out = config.dump()
    assert "names = Carol\n    Dave" in out
    reparsed = IniConfig("y.ini", data=out)
    assert reparsed.get("s", "names") == "Carol\nDave"


def test_dump_modified_value_drops_old_continuations() -> None:
    config = IniConfig("x.ini", data="[s]\nnames =\n    Alice\n    Bob\nk = 1\n")
    config.sections["s"]["names"] = "solo"  # type: ignore[index]
    out = config.dump()
    reparsed = IniConfig("y.ini", data=out)
    assert reparsed.get("s", "names") == "solo"
    assert reparsed.get("s", "k") == "1"


def test_dump_new_key_and_new_section() -> None:
    config = IniConfig("x.ini", data="[s]\na = 1\n")
    config.sections["s"]["b"] = "2"  # type: ignore[index]
    config.sections["new"] = {"k": "v"}  # type: ignore[index]
    out = config.dump()
    reparsed = IniConfig("y.ini", data=out)
    assert reparsed.sections == config.sections
    assert reparsed.get("s", "b") == "2"
    assert reparsed.get("new", "k") == "v"
    assert out.index("a = 1") < out.index("b = 2")


def test_dump_removed_key_and_section() -> None:
    data = "[s]\na = 1\nb = 2\n\n[gone]\nx = 1\n"
    config = IniConfig("x.ini", data=data)
    del config.sections["s"]["a"]  # type: ignore[attr-defined]
    del config.sections["gone"]  # type: ignore[attr-defined]
    out = config.dump()
    reparsed = IniConfig("y.ini", data=out)
    assert reparsed.sections == config.sections
    assert "gone" not in reparsed
    assert reparsed.get("s", "a") is None
    assert reparsed.get("s", "b") == "2"


@pytest.mark.parametrize(
    "value",
    [
        "line1\n\nline3",  # blank line inside a value
        "trailing\n",  # trailing bare newline
        "  padded  ",  # leading/trailing whitespace would be stripped
        "carriage\rreturn",
    ],
)
def test_dump_raises_valueerror_for_unsafe_values(value: str) -> None:
    config = IniConfig("x.ini", data="[s]\na = 1\n")
    config.sections["s"]["a"] = value  # type: ignore[index]
    with pytest.raises(ValueError):
        config.dump()


def test_write_does_not_touch_file_on_valueerror(tmp_path: Path) -> None:
    path = tmp_path / "config.ini"
    path.write_text("[s]\na = 1\n", encoding="utf-8")
    config = IniConfig(str(path))
    config.sections["s"]["a"] = "bad\n\nvalue"  # type: ignore[index]
    with pytest.raises(ValueError), open(path, "w", encoding="utf-8") as fp:
        config.write(fp)


def test_dump_crlf_preserved() -> None:
    data = "[s]\r\na = 1\r\n"
    config = IniConfig("x.ini", data=data)
    assert config.dump() == data
    config.sections["s"]["b"] = "2"  # type: ignore[index]
    out = config.dump()
    assert "b = 2\r\n" in out
    assert IniConfig("y.ini", data=out).sections == config.sections


def test_dump_from_parse_with_inline_comment_stripping() -> None:
    config = IniConfig.parse("x.ini", data="[s]\na = 1 # note\n")
    assert config.get("s", "a") == "1"
    reparsed = IniConfig.parse("y.ini", data=config.dump())
    assert reparsed.sections == config.sections
