"""A non-ASCII character earlier in a file must not rename later symbols (#414).

Reported by @MotoMato85 against 1.108.241. Sixteen extractors did
``source = source_bytes.decode(...)`` and then sliced that ``str`` with
tree-sitter's ``node.start_byte`` / ``node.end_byte``, which are BYTE offsets.
Every earlier non-ASCII character shifted the extraction window forward by
(bytes - characters), so `Kayttaja` came back as `aja {`. The window keeps its
byte width, so names stayed plausible-looking, and ``line`` / ``end_line`` come
from ``start_point`` and stayed correct -- an outline looked right while the
names in it were unreachable. The corrupted name is baked into the symbol id,
so it persists into the index and every name-keyed lookup misses.

⚠ A pure-ASCII fixture CANNOT catch this: byte and character offsets coincide,
so it passes with or without the bug. That is why it survived so long, and it
is what makes the paired fixtures below the point of this file.

The assertion is differential rather than hand-written: each fixture is parsed
twice, once with a comment holding five U+00E4 and once with the same comment
in pure ASCII. The names must be identical. A hand-written expectation would
pin whatever this parser happens to emit today; the invariant is that a comment
character cannot change a name.
"""
from __future__ import annotations

import pytest

from jcodemunch_mcp.parser.extractor import ByteSlicedSource, parse_file

#: Five U+00E4 -- 5 characters, 10 bytes, so 5 bytes of drift for everything
#: that follows. The ASCII twin substitutes five 'a'.
PLACEHOLDER = "@@PAD@@"
NON_ASCII = "ä" * 5
ASCII = "a" * 5

#: (language, filename, source template with a PLACEHOLDER inside a comment,
#:  names that must come back)
CASES = [
    ("objc", "demo.m",
     "// kommentti @@PAD@@\n"
     "@interface Kappale : NSObject\n- (int)laskeSumma:(int)a;\n@end\n",
     {"Kappale"}),
    ("proto", "demo.proto",
     "// kommentti @@PAD@@\n"
     'syntax = "proto3";\nmessage Kayttaja {\n  string nimi = 1;\n}\n',
     {"Kayttaja"}),
    ("hcl", "demo.tf",
     "# kommentti @@PAD@@\n"
     'resource "aws_s3_bucket" "kauppa" {\n  bucket = "x"\n}\n',
     {"aws_s3_bucket.kauppa"}),
    ("graphql", "demo.graphql",
     "# kommentti @@PAD@@\n"
     "type Kayttaja {\n  nimi: String\n}\n",
     {"Kayttaja"}),
    ("julia", "demo.jl",
     "# kommentti @@PAD@@\n"
     "function laskeSumma(a, b)\n    a + b\nend\n",
     {"laskeSumma"}),
    ("groovy", "demo.groovy",
     "// kommentti @@PAD@@\n"
     "class Kappale {\n    def laskeSumma(a, b) { a + b }\n}\n",
     {"Kappale"}),
    ("xml", "demo.xml",
     '<?xml version="1.0"?>\n'
     "<!-- kommentti @@PAD@@ -->\n"
     "<juuri>\n  <lapsi/>\n</juuri>\n",
     {"juuri"}),
    ("pascal", "demo.pas",
     "// kommentti @@PAD@@\n"
     "function LaskeSumma(a: Integer): Integer;\nbegin\nend;\n",
     {"LaskeSumma"}),
    ("matlab", "demo.mat",
     "% kommentti @@PAD@@\n"
     "function r = laskeSumma(a, b)\n  r = a + b;\nend\n",
     {"laskeSumma"}),
    ("ada", "demo.adb",
     "-- kommentti @@PAD@@\n"
     "procedure LaskeSumma is\nbegin\n   null;\nend LaskeSumma;\n",
     {"LaskeSumma"}),
    ("commonlisp", "demo.lisp",
     "; kommentti @@PAD@@\n"
     "(defun laske-summa (a b) (+ a b))\n",
     {"laske-summa"}),
    ("racket", "demo.rkt",
     ";; kommentti @@PAD@@\n"
     "(define (laske-summa a b) (+ a b))\n",
     {"laske-summa"}),
    ("solidity", "demo.sol",
     "// kommentti @@PAD@@\n"
     "pragma solidity ^0.8.0;\ncontract Kassa {\n    function talleta() public {}\n}\n",
     {"Kassa", "talleta"}),
    ("zig", "demo.zig",
     "// kommentti @@PAD@@\n"
     "pub fn laskeSumma(a: i32, b: i32) i32 {\n    return a + b;\n}\n",
     {"laskeSumma"}),
    ("powershell", "demo.ps1",
     "# kommentti @@PAD@@\n"
     "function Get-Summa { }\n",
     {"Get-Summa"}),
    ("apex", "demo.cls",
     "// kommentti @@PAD@@\n"
     "public class Kappale {\n    public void laskeSumma() {}\n}\n",
     {"Kappale"}),
    ("ocaml", "demo.ml",
     "(* kommentti @@PAD@@ *)\n"
     "let laske_summa a b = a + b\n",
     {"laske_summa"}),
]

#: Extractors that slice ``source_bytes`` directly or use ``node.text``. They
#: were never affected, and they are here so a regression in the shared helper
#: cannot pass unnoticed.
CONTROL_CASES = [
    ("python", "demo.py",
     "# kommentti @@PAD@@\ndef laske_summa(a, b):\n    return a + b\n",
     {"laske_summa"}),
    ("javascript", "demo.js",
     "// kommentti @@PAD@@\nfunction laskeSumma(a, b) {\n  return a + b;\n}\n",
     {"laskeSumma"}),
    ("go", "demo.go",
     "// kommentti @@PAD@@\npackage main\n\nfunc laskeSumma(a int) int {\n\treturn a\n}\n",
     {"laskeSumma"}),
]


def _names(template: str, pad: str, filename: str, language: str) -> set[str]:
    source = template.replace(PLACEHOLDER, pad)
    symbols = parse_file(
        source, filename, language, source_bytes=source.encode("utf-8")
    )
    return {s.name for s in symbols}


ALL = CASES + CONTROL_CASES


@pytest.mark.parametrize(
    "language,filename,template,expected", ALL, ids=[c[0] for c in ALL]
)
def test_non_ascii_comment_does_not_shift_symbol_names(
    language, filename, template, expected
):
    ascii_names = _names(template, ASCII, filename, language)
    utf8_names = _names(template, NON_ASCII, filename, language)

    # Guard against a vacuous pass: if the grammar emitted nothing for either
    # input, an equality assertion between two empty sets proves nothing.
    assert expected <= ascii_names, (
        f"{language}: the ASCII control did not yield {expected}, got "
        f"{ascii_names} -- fixture or grammar problem, not the bug under test"
    )
    assert utf8_names == ascii_names, (
        f"{language}: five U+00E4 in a comment changed the extracted names: "
        f"{sorted(ascii_names)} -> {sorted(utf8_names)}"
    )


@pytest.mark.parametrize(
    "language,filename,template,expected", CASES, ids=[c[0] for c in CASES]
)
def test_symbol_lines_were_never_the_broken_half(
    language, filename, template, expected
):
    """Lines come from start_point and were correct throughout.

    Pinned because it is the reason the corruption stayed invisible: an outline
    with right lines and wrong names reads as healthy.
    """
    def lines(pad):
        source = template.replace(PLACEHOLDER, pad)
        return sorted(
            s.line
            for s in parse_file(
                source, filename, language, source_bytes=source.encode("utf-8")
            )
        )

    assert lines(ASCII) == lines(NON_ASCII)


def test_byte_sliced_source_is_indexed_by_bytes_not_characters():
    """The unit-level invariant, independent of any grammar."""
    text = "ääx"
    view = ByteSlicedSource(text.encode("utf-8"))

    assert len(view) == 5, "length is in bytes"
    assert view[4:5] == "x", "byte offset 4 is 'x'; character offset 4 is past the end"
    assert view[0:2] == "ä"
    assert str(view) == text


def test_byte_sliced_source_trims_a_split_character_instead_of_replacing_it():
    """The 120-byte signature truncations can land mid-character."""
    view = ByteSlicedSource("aäb".encode("utf-8"))

    # Bytes 0..2 cut the two-byte U+00E4 in half.
    assert view[0:2] == "a", "a split trailing character is dropped, not mangled"
    assert "�" not in view[0:2]
    assert view[0:3] == "aä"


def test_byte_sliced_source_still_survives_undecodable_bytes():
    """Invalid UTF-8 must degrade, never raise -- the old idiom used errors='replace'."""
    view = ByteSlicedSource(b"a\xffb")

    assert view[0:3] == "a�b"
    assert str(view) == "a�b"
