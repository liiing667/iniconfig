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


ROUNDTRIP_DATA = """\
# top comment
[section1] # trailing comment
key = "值带空格"
path = C:\\dir\\file
hash = #starts with hash
semi = ;starts with semi
multi =
    line1
    line2

; another comment
[section2]
a = 1
b = 2
"""


def test_dump_unmodified_is_identical() -> None:
    config = IniConfig("test.ini", ROUNDTRIP_DATA)
    assert config.dump() == ROUNDTRIP_DATA


def test_dump_roundtrip_values() -> None:
    config = IniConfig("test.ini", ROUNDTRIP_DATA)
    reread = IniConfig("test.ini", config.dump())
    assert config.sections == reread.sections


def test_dump_roundtrip_with_parse() -> None:
    config = IniConfig.parse("test.ini", ROUNDTRIP_DATA)
    reread = IniConfig.parse("test.ini", config.dump())
    assert config.sections == reread.sections


def test_write_to_file(tmp_path: Path) -> None:
    path = tmp_path / "test.ini"
    path.write_text(ROUNDTRIP_DATA, encoding="utf-8")
    config = IniConfig(str(path))
    config.sections["section1"]["key"] = '"changed"'
    with path.open("w", encoding="utf-8") as fp:
        config.write(fp)
    reread = IniConfig(str(path))
    assert reread["section1"]["key"] == '"changed"'
    assert reread["section1"]["path"] == "C:\\dir\\file"
    assert reread["section1"]["multi"] == "line1\nline2"


def test_dump_preserves_comments_and_order_on_change() -> None:
    config = IniConfig("test.ini", ROUNDTRIP_DATA)
    config.sections["section2"]["b"] = "changed"
    config.sections["section2"]["c"] = "added"
    out = config.dump()
    assert "# top comment" in out
    assert "; another comment" in out
    assert "[section1] # trailing comment" in out
    # key order of untouched entries is preserved
    assert out.index("a = 1") < out.index("b = changed") < out.index("c = added")
    reread = IniConfig("test.ini", out)
    assert reread["section2"]["b"] == "changed"
    assert reread["section2"]["c"] == "added"


def test_dump_modified_multiline_value() -> None:
    config = IniConfig("test.ini", ROUNDTRIP_DATA)
    config.sections["section1"]["multi"] = "one\ntwo\nthree"
    reread = IniConfig("test.ini", config.dump())
    assert reread["section1"]["multi"] == "one\ntwo\nthree"


def test_dump_new_section_appended() -> None:
    config = IniConfig("test.ini", "[s]\na = 1\n")
    config.sections["new"] = {"x": "y"}
    out = config.dump()
    assert out == "[s]\na = 1\n[new]\nx = y\n"
    assert IniConfig("test.ini", out)["new"]["x"] == "y"


def test_dump_removed_key_and_section() -> None:
    config = IniConfig("test.ini", "[s]\na = 1\nb = 2\n[t]\nc = 3\n")
    del config.sections["s"]["b"]
    del config.sections["t"]
    out = config.dump()
    assert out == "[s]\na = 1\n"
    assert IniConfig("test.ini", out).sections == {"s": {"a": "1"}}


def test_dump_no_trailing_newline() -> None:
    config = IniConfig("test.ini", "[s]\nb = 2")
    assert config.dump() == "[s]\nb = 2"
    config.sections["s"]["c"] = "3"
    assert config.dump() == "[s]\nb = 2\nc = 3\n"


@pytest.mark.parametrize(
    "value",
    [
        " leading",
        "trailing ",
        "a\n\nb",  # empty line inside a multi-line value
        "a\n#comment",  # continuation would be read as a comment
        "a\n;comment",
        "a\n b",  # leading whitespace on a continuation line
        "\na",  # empty first line
        "a\rb",  # bare carriage return
    ],
)
def test_dump_unsafe_value_raises(value: str) -> None:
    config = IniConfig("test.ini", "[s]\nk = v\n")
    config.sections["s"]["k"] = value
    with pytest.raises(ValueError):
        config.dump()


@pytest.mark.parametrize(
    "key",
    [
        "",
        " spaced ",
        "a=b",
        "a:b",
        "#comment",
        ";comment",
        "[section]",
        "a\nb",
    ],
)
def test_dump_unsafe_key_raises(key: str) -> None:
    config = IniConfig("test.ini", "[s]\nk = v\n")
    config.sections["s"][key] = "value"
    with pytest.raises(ValueError):
        config.dump()


@pytest.mark.parametrize("section", ["", "a#b", "a;b", "a\nb"])
def test_dump_unsafe_section_name_raises(section: str) -> None:
    config = IniConfig("test.ini", "[s]\nk = v\n")
    config.sections[section] = {"k": "v"}
    with pytest.raises(ValueError):
        config.dump()
