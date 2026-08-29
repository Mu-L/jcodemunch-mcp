"""The Python Racket reader: shape, spans, at-exp, error resynchronisation,
and the frozen reader-oracle gate.

Two kinds of test live here and they answer different questions.

The unit tests pin the reader's OWN contract: the node surface the walker
consumes, the shape of each form, and what happens on an error -- which is
ours to specify, because Racket's reader simply fails.

The frozen-oracle tests pin the reader against RACKET'S reader: every syntax
object `read-syntax` produces for the fixtures, with its byte span, as
`tests/fixtures/racket_reader_oracle.json` (see `REGENERATE.md`). That is what
lets CI, with no Racket installed, check the reader's positions against the
authority rather than against our own expectations.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from jcodemunch_mcp.parser.racket_reader import (
    LANG_TAKES_ARGUMENT,
    RacketNode,
    RacketReadError,
    RacketTree,
    read_racket,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "racket"
FROZEN = REPO_ROOT / "tests" / "fixtures" / "racket_reader_oracle.json"
HARNESS = REPO_ROOT / "benchmarks" / "racket_fidelity" / "run_reader_fidelity.py"

#: Read off disk at collection, never listed: a fixture missing from the
#: roster would be silently unmeasured (the Rust harness had exactly that).
FIXTURE_NAMES = sorted(p.name for p in FIXTURES.glob("*.rkt"))


def _root(src: bytes, **kw) -> RacketNode:
    return read_racket(src, **kw).root_node


def _top(src: bytes, **kw) -> list[tuple[str, int, int]]:
    return [(c.type, c.start_byte, c.end_byte) for c in _root(src, **kw).children]


def _shape(node: RacketNode) -> list:
    """Nested [type, text-or-children] for compact structural asserts."""
    if node.children:
        return [node.type + ("@" if node.at_form else ""), [_shape(c) for c in node.children]]
    return [node.type, node.text.decode()]


# ── the surface the walker consumes ────────────────────────────────────────

def test_node_surface_matches_tree_sitter_semantics():
    src = b"(define x 1) ; trailing\n(define (f y)\n  y)\n"
    tree = read_racket(src)
    root = tree.root_node
    assert isinstance(tree, RacketTree) and root.type == "program"
    assert (root.start_byte, root.end_byte) == (0, len(src))
    first, comment, second = root.children
    assert first.text == b"(define x 1)"
    assert first.is_named and first.named_children == first.children
    assert first.child_count == 3
    assert first.children[0].parent is first
    assert comment.type == "comment" and comment.text == b"; trailing"
    assert second.prev_named_sibling is comment and comment.prev_named_sibling is first
    assert first.prev_named_sibling is None
    assert second.start_point == (1, 0) and second.end_point == (2, 4)
    assert first.children[1].start_point == (0, 8)
    assert not root.has_error and tree.errors == []


def test_points_are_rows_and_byte_columns():
    src = "(λ (x)\n  \"é\" x)".encode()
    root = _root(src)
    (lam,) = root.children
    string = lam.children[2]
    assert string.text == '"é"'.encode()
    assert string.start_point == (1, 2)
    assert lam.end_point == (1, 2 + len('"é" x)'.encode()))


# ── the default reader, one instance per dispatch ───────────────────────────

@pytest.mark.parametrize("src, type_", [
    (b'"str"', "string"), (b'"multi\nline \\" quote"', "string"),
    (b'#"bytes"', "byte_string"), (b"#<<EOS\nx\nEOS\n", "here_string"),
    (b"#\\a", "character"), (b"#\\space", "character"), (b"#\\SPACE", "character"),
    (b"#\\u3BB", "character"), ("#\\λ".encode(), "character"), (b"#\\(", "character"),
    (b"#\\;", "character"), (b"#\\1", "character"),
    (b"42", "number"), (b"1.5", "number"), (b"1/2", "number"), (b"#x1F", "number"),
    (b"#xFF", "number"), (b"#e1.0", "number"), (b"#i#x10", "number"), (b"+inf.0", "number"),
    (b"-nan.0", "number"), (b"1+2i", "number"), (b"+i", "number"), (b"1@2", "number"),
    (b".5", "number"), (b"5.", "number"), (b"1e3", "number"), (b"1.0t0", "number"),
    (b"#b101", "number"), (b"1#", "number"),
    (b"#t", "boolean"), (b"#f", "boolean"), (b"#true", "boolean"), (b"#F", "boolean"),
    (b"#:kw", "keyword"), (b"#:1", "keyword"),
    (b"foo", "symbol"), (b"|sym bol|", "symbol"), (b"foo|bar|baz", "symbol"),
    (b"a\\ b", "symbol"), (b"#%app", "symbol"), (b"1+", "symbol"), (b"-", "symbol"),
    (b"...", "symbol"), (b".foo", "symbol"), (b"+", "symbol"), (b"1/2/3", "symbol"),
    (b"1e", "symbol"), (b"a@b", "symbol"), (b"@foo", "symbol"), (b"x#y", "symbol"),
    (b"#rx\"re\"", "regex"), (b"#px\"p\"", "regex"), (b"#rx#\"b\"", "regex"),
    (b"#(1 2)", "vector"), (b"#3(a)", "vector"), (b"#fl(1.0)", "vector"), (b"#fx[1]", "vector"),
    (b"#hash((a . 1))", "hash"), (b"#hasheq()", "hash"), (b"#hasheqv()", "hash"), (b"#hashalw{}", "hash"),
    (b"#s(pt 1 2)", "structure"), (b"#&b", "box"),
    (b"'x", "quote"), (b"`x", "quasiquote"), (b",x", "unquote"), (b",@x", "unquote_splicing"),
    (b"#'x", "syntax"), (b"#`x", "quasisyntax"), (b"#,x", "unsyntax"), (b"#,@x", "unsyntax_splicing"),
    (b"(a b)", "list"), (b"[a]", "list"), (b"{a}", "list"), (b"()", "list"),
    (b"; c", "comment"), (b"#| c |#", "block_comment"), (b"#;x", "sexp_comment"),
    (b"#! /bin/sh", "comment"), (b"#!/bin/sh \\\n more", "comment"),
    (b"#lang racket", "extension"), (b"#!r6rs", "extension"),
])
def test_one_datum_one_node_spanning_all_of_it(src, type_):
    """Every token is exactly one node covering exactly its bytes."""
    assert _top(src) == [(type_, 0, len(src))], _top(src)


def test_here_string_span_runs_through_the_terminator_newline():
    # Measured against `read-syntax`: `#<<E\nhi\nE\n` spans 10, not 9.
    assert _top(b"#<<E\nhi\nE\n 1") == [("here_string", 0, 10), ("number", 11, 12)]
    assert _top(b"#<< eos\nabc\n eos") == [("here_string", 0, 16)]   # terminator may start with a space


def test_case_fold_prefix_is_not_a_symbol():
    # tree-sitter reads `#cs` as a symbol; Racket switches case sensitivity.
    assert _top(b"#cs Apple #ci|B|c") == [("symbol", 4, 9), ("symbol", 13, 17)]


def test_compound_forms_mirror_tree_sitter_shapes():
    assert _shape(_root(b"#(1 (a . b))").children[0]) == [
        "vector", [["list", [["number", "1"], ["list", [["symbol", "a"], ["dot", "."], ["symbol", "b"]]]]]]]
    assert _shape(_root(b"'(a . < . b)").children[0]) == [
        "quote", [["list", [["symbol", "a"], ["dot", "."], ["symbol", "<"], ["dot", "."], ["symbol", "b"]]]]]
    assert _shape(_root(b"#&(x)").children[0]) == ["box", [["list", [["symbol", "x"]]]]]
    assert [_shape(c) for c in _root(b"#;(skipped) 1").children] == [
        ["sexp_comment", [["list", [["symbol", "skipped"]]]]], ["number", "1"]]


def test_comments_are_named_children_wherever_they_occur():
    """Mirrors tree-sitter, and the walker relies on it for docstrings."""
    root = _root(b"(define x ; doc\n  1)\n' ;c\n y")
    assert [c.type for c in root.children[0].children] == ["symbol", "symbol", "comment", "number"]
    assert [c.type for c in root.children[1].children] == ["comment", "symbol"]


def test_lang_line_is_an_extension_with_the_lang_name():
    (ext,) = _root(b"#lang racket/base\n").children
    assert ext.type == "extension" and [c.type for c in ext.children] == ["lang_name"]
    assert ext.children[0].text == b"racket/base"


def test_wrapper_langs_consume_their_argument():
    """`#lang at-exp racket/base`: `racket/base` belongs to the `#lang` line,
    not to the module body -- Racket's at-exp reader reads it."""
    top = _top(b"#lang at-exp racket/base\n(define x 1)\n")
    assert [t for t, _, _ in top] == ["extension", "list"]
    (ext, _) = _root(b"#lang s-exp \"lang.rkt\"\n1").children[:2]
    assert [c.text for c in ext.children] == [b"s-exp", b'"lang.rkt"']


def test_wrapper_langs_known_to_the_gate_are_known_to_the_reader():
    """One roster: the `#lang` gate's wrapper sets must be a subset of what
    the reader knows takes an argument, or a wrapper's argument leaks into the
    module body as a symbol."""
    from jcodemunch_mcp.parser.extractor import _RACKET_ATEXP_WRAPPERS, _RACKET_TRANSPARENT_WRAPPERS
    assert (_RACKET_ATEXP_WRAPPERS | _RACKET_TRANSPARENT_WRAPPERS) <= LANG_TAKES_ARGUMENT


def test_reader_extension_is_one_node_wrapping_module_path_and_datum():
    (ext,) = _root(b"#reader scribble/comment-reader (racketblock 1)").children
    assert ext.type == "extension"
    assert [c.type for c in ext.children] == ["lang_name", "list"]


# ── `@` is an ordinary character unless the reader is told otherwise ────────

def test_at_sign_is_a_symbol_constituent_in_the_default_reader():
    root = _root(b"(define @foo 1) x@y '@foo{x}")
    assert root.children[0].children[1].text == b"@foo"
    assert root.children[1].type == "symbol" and root.children[1].text == b"x@y"
    # `'@foo{x}` is a quoted symbol followed by a brace LIST, not an at-form.
    assert [c.type for c in root.children[2:]] == ["quote", "list"]
    assert not any(c.at_form for c in root.children)


def test_at_exp_is_never_inferred_from_the_text():
    plain = read_racket(b"@foo{x}")
    assert [c.type for c in plain.root_node.children] == ["symbol", "list"]
    assert read_racket(b"@foo{x}", at_exp=True).root_node.children[0].at_form


# ── at-exp: the shapes `read` produces (spans are pinned by the oracle below) ──

def _at(src: bytes) -> RacketNode:
    return _root(src, at_exp=True).children[0]


def test_an_at_form_is_a_list_from_the_at_sign_to_the_closing_brace():
    form = _at(b"@foo{blah}")
    assert form.type == "list" and form.at_form
    assert (form.start_byte, form.end_byte) == (0, 10)
    assert _shape(form) == ["list@", [["symbol", "foo"], ["string", "blah"]]]
    assert form.children[0].start_byte == 1     # the command's own span excludes `@`


def test_command_only_forms_are_just_the_command_node():
    assert _shape(_at(b"@foo")) == ["symbol", "foo"] and _at(b"@foo").start_byte == 1
    assert _shape(_at(b"@(f 1)")) == ["list", [["symbol", "f"], ["number", "1"]]]
    assert _shape(_at(b"@|x|")) == ["symbol", "x"]
    assert _shape(_at(b'@"@"')) == ["string", '"@"']
    assert not _at(b"@(f 1)").at_form


def test_datums_and_bodies_stack_behind_the_command():
    assert _shape(_at(b"@foo[1 2]{3 4}")) == [
        "list@", [["symbol", "foo"], ["number", "1"], ["number", "2"], ["string", "3 4"]]]
    assert _shape(_at(b"@foo[#:style 'big]")) == [
        "list@", [["symbol", "foo"], ["keyword", "#:style"], ["quote", [["symbol", "big"]]]]]
    assert _shape(_at(b"@foo[]{}")) == ["list@", [["symbol", "foo"]]]


def test_the_command_can_be_omitted():
    assert _shape(_at(b"@{blah}")) == ["list@", [["string", "blah"]]]
    assert _shape(_at(b"@{blah @[3]}")) == ["list@", [["string", "blah "], ["list@", [["number", "3"]]]]]


def test_punctuation_prefixes_wrap_the_whole_form_from_the_at_sign():
    outer = _at(b"@`',@foo{blah}")
    chain = []
    n = outer
    while n.children and not n.at_form:
        chain.append((n.type, n.start_byte, n.end_byte))
        n = n.children[0]
    assert chain == [("quasiquote", 0, 14), ("quote", 0, 14), ("unquote_splicing", 0, 14)]
    assert n.at_form and (n.start_byte, n.end_byte) == (0, 14)
    assert _shape(_at(b"@'foo")) == ["quote", [["symbol", "foo"]]]


def test_text_bodies_hold_text_nested_forms_and_escapes():
    form = _at(b'@foo{a @bar{b} @|c d| @"s" @(+ 1 2) x}')
    assert _shape(form) == ["list@", [
        ["symbol", "foo"], ["string", "a "],
        ["list@", [["symbol", "bar"], ["string", "b"]]], ["string", " "],
        ["symbol", "c"], ["symbol", "d"], ["string", " "],
        ["string", '"s"'], ["string", " "],
        ["list", [["symbol", "+"], ["number", "1"], ["number", "2"]]], ["string", " x"]]]


def test_balanced_braces_and_string_escapes_are_text():
    assert _shape(_at(b"@foo{f{o}o}")) == ["list@", [["symbol", "foo"], ["string", "f{o}o"]]]
    assert _shape(_at(b"@foo{{{}}{}}")) == ["list@", [["symbol", "foo"], ["string", "{{}}{}"]]]
    form = _at(b'@foo{A @"}" marks the end} 1')
    assert form.end_byte == len(b'@foo{A @"}" marks the end}')


def test_escapes_read_with_the_command_readtable():
    """Inside `@|...|` a `|` TERMINATES a symbol, so `@|user|span` is the escape
    `user` followed by the text `span` -- not one symbol running to the next
    bar in the file (measured: 2,000 bytes of JavaScript read as a symbol)."""
    assert _shape(_at(b"@foo{x@|user|span_classes = [ y }")) == [
        "list@", [["symbol", "foo"], ["string", "x"], ["symbol", "user"], ["string", "span_classes = [ y "]]]
    assert _shape(_at(b"@foo{x@|1 (+ 2 3) 4|y}")) == ["list@", [
        ["symbol", "foo"], ["string", "x"], ["number", "1"],
        ["list", [["symbol", "+"], ["number", "2"], ["number", "3"]]], ["number", "4"], ["string", "y"]]]
    assert _shape(_at(b"@foo{Alice@||Bob}")) == ["list@", [["symbol", "foo"], ["string", "Alice"], ["string", "Bob"]]]


def test_command_ends_at_a_bar_and_no_space_is_allowed_before_a_brace():
    assert _shape(_at(b"@foo|{bar}|")) == ["list@", [["symbol", "foo"], ["string", "bar"]]]
    # `@foo {x}`: the command `foo`, then an ordinary brace list.
    assert [c.type for c in _root(b"@foo {x}", at_exp=True).children] == ["symbol", "list"]


def test_alternate_delimiters_make_braces_and_at_signs_text():
    assert _shape(_at(b"@foo|{bar}@{baz}|")) == ["list@", [["symbol", "foo"], ["string", "bar}@{baz"]]]
    assert _shape(_at(b"@foo|{bar |@x{X} baz}|")) == ["list@", [
        ["symbol", "foo"], ["string", "bar "], ["list@", [["symbol", "x"], ["string", "X"]]], ["string", " baz"]]]
    assert _shape(_at(b"@foo|<<{bar}@|{baz}>>|")) == ["list@", [["symbol", "foo"], ["string", "bar}@|{baz"]]]
    assert _shape(_at(b"@foo|!!{X |!!@b{Y}...}!!|")) == ["list@", [
        ["symbol", "foo"], ["string", "X "], ["list@", [["symbol", "b"], ["string", "Y"]]], ["string", "..."]]]
    assert _shape(_at(b"@foo|<<<{@x{foo} |@{bar}|.}>>>|")) == ["list@", [
        ["symbol", "foo"], ["string", "@x{foo} |@{bar}|."]]]


def test_at_comments_leave_nothing_behind_in_text_and_a_comment_node_in_code():
    assert _shape(_at(b"@foo{a @; line\n b}")) == ["list@", [["symbol", "foo"], ["string", "a "], ["string", "b"]]]
    assert _shape(_at(b"@foo{a @;{ block {nested} } b}")) == [
        "list@", [["symbol", "foo"], ["string", "a "], ["string", " b"]]]
    top = _root(b"@; whole line\n(define x 1)", at_exp=True).children
    assert [c.type for c in top] == ["comment", "list"]


def test_whitespace_after_the_command_character_is_an_error():
    tree = read_racket(b"(define x @ foo)", at_exp=True)
    assert tree.errors and "whitespace" in tree.errors[0].message


def test_command_character_is_configurable():
    src = "◊foo{x @not-a-form}".encode()
    form = _root(src, at_exp=True, command_char="◊".encode()).children[0]
    assert form.at_form and _shape(form) == ["list@", [["symbol", "foo"], ["string", "x @not-a-form"]]]


def test_inside_mode_reads_text_at_top_level():
    root = _root(b"Hello @bold{x} { braces are text } @(define y 1)", inside=True)
    assert [c.type for c in root.children] == ["string", "list", "string", "list"]
    assert root.children[1].at_form and not root.children[3].at_form


# ── errors: designed, not recovered ────────────────────────────────────────

def test_errors_are_recorded_never_raised():
    tree = read_racket(b")))((( \"unterminated #| #\\ #zz")
    assert tree.errors and tree.root_node.has_error
    assert all(isinstance(e, RacketReadError) and isinstance(e.pos, int) for e in tree.errors)


def test_a_missing_close_paren_costs_only_its_own_form():
    """Racket rejects the whole file; the definitions after the broken form
    are found by resynchronising at the next column-0 opener."""
    src = b"(define (a) 1\n(define (b) 2)\n(define (c) 3)\n"
    top = _top(src)
    assert top[0] == ("ERROR", 0, src.index(b"(define (b)"))
    assert [t for t, _, _ in top] == ["ERROR", "list", "list"]
    assert [n.children[1].children[0].text for n in _root(src).children[1:]] == [b"b", b"c"]


def test_an_extra_close_paren_folds_the_leaked_internal_forms_into_the_error():
    """The form closes early and its remaining internal definitions arrive at
    top level INDENTED. Reporting them would be the fabrication tree-sitter's
    recovery produced; they fold back into the ERROR instead."""
    src = (b"(define (a)\n  (let ()\n    (define (inner) 1)))\n"
           b"    (define (leaked) 2)\n    (define (leaked2) 3))\n(define (b) 4)\n")
    root = _root(src)
    assert [c.type for c in root.children] == ["list", "ERROR", "list"]
    err = root.children[1]
    assert err.start_byte == src.index(b"    (define (leaked)") + 4
    assert err.end_byte == src.index(b"(define (b)")
    assert root.children[2].children[1].children[0].text == b"b"


def test_a_stray_close_paren_after_a_column_zero_form_costs_nothing_else():
    src = b"(define (a) 1))\n(define (b) 2)\n"
    assert [t for t, _, _ in _top(src)] == ["list", "ERROR", "list"]


def test_an_unterminated_string_resyncs_at_the_next_column_zero_opener():
    src = b"(define (a)\n  \"oops)\n;; comment\n(define (b) 2)\n"
    top = _top(src)
    assert [t for t, _, _ in top] == ["ERROR", "comment", "list"]
    assert top[0][2] == src.index(b";; comment")


def test_a_missing_closing_brace_in_at_exp_resyncs_too():
    src = b"(define (a)\n  @html{never closed)\n(define (b) 2)\n"
    top = _top(src, at_exp=True)
    assert [t for t, _, _ in top] == ["ERROR", "list"]


def test_a_mismatched_closer_keeps_the_form_and_records_the_error():
    tree = read_racket(b"(define (a) [x 1))\n(define (b) 2]\n")
    assert [c.type for c in tree.root_node.children] == ["list", "list"]
    assert len(tree.errors) == 2 and tree.root_node.has_error


def test_resync_never_loops():
    src = b")\n)\n)\n(define (b) 1)\n"
    top = _top(src)
    assert top[-1][0] == "list" and all(t in ("ERROR", "list") for t, _, _ in top)


# ── the frozen reader-oracle gate ───────────────────────────────────────────

def _load_harness():
    spec = importlib.util.spec_from_file_location("_racket_reader_fidelity", HARNESS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def frozen() -> dict:
    return json.loads(FROZEN.read_text(encoding="utf-8"))["files"]


@pytest.fixture(scope="module")
def harness():
    return _load_harness()


def test_frozen_reader_data_covers_every_fixture(frozen):
    """A fixture with no frozen answer is silently unmeasured."""
    assert set(FIXTURE_NAMES) == set(frozen)
    assert all("error" not in rec for rec in frozen.values())


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_reader_produces_every_node_racket_reads_and_no_other(harness, frozen, name):
    from jcodemunch_mcp.parser.extractor import _racket_tier
    path = FIXTURES / name
    tier, _ = _racket_tier(path.read_bytes(), None)
    assert tier != "text", f"{name} is not a reader fixture"
    result = harness.compare(path, frozen[name], at_exp=(tier == "at-exp"))
    assert result.get("our_error") is None, result
    assert result["only_racket"] == [], f"{name}: Racket reads nodes we do not: {result['only_racket']}"
    assert result["only_ours"] == [], f"{name}: we read nodes Racket does not: {result['only_ours']}"
    assert result["nodes_compared"] > 0, "non-vacuity: the comparison must have compared something"


def test_the_gate_is_not_vacuous(harness, frozen):
    """The at-exp fixtures must exercise at-forms and the whole set must be
    large enough that an empty tree could not pass by accident."""
    from jcodemunch_mcp.parser.extractor import _racket_tier
    at_forms = nodes = 0
    for name in FIXTURE_NAMES:
        path = FIXTURES / name
        tier, _ = _racket_tier(path.read_bytes(), None)
        r = harness.compare(path, frozen[name], at_exp=(tier == "at-exp"))
        at_forms += r["at_forms"]
        nodes += r["nodes_compared"]
    assert at_forms >= 90 and nodes >= 900


def test_the_gate_fails_on_a_span_that_is_off_by_one(harness, frozen):
    """Non-vacuity for the comparison itself: shift one node's span and the
    gate must notice. A gate that could not fail proves nothing."""
    name = "reader.rkt"
    rec = json.loads(json.dumps(frozen[name]))
    first_symbol = next(n for n in rec["nodes"] if n[0] == "symbol")
    first_symbol[2] += 1
    result = harness.compare(FIXTURES / name, rec, at_exp=False)
    assert result["only_racket"] and result["only_ours"]
