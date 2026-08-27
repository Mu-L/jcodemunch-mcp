"""The Racket `#lang` gate: a reader is decided before the grammar runs.

tree-sitter-racket parses S-expressions. A `#lang` line names a READER, and a
reader can make a `.rkt` file's surface syntax anything at all -- Markdown
(`punct`), prose (`scribble/manual`), at-exp text over Racket (`conscript`).
Before this gate the walker parsed every `.rkt` as `racket/base`.

Measured on 207 `#lang conscript` files against Racket's own reader: 39% of
definitions found, ~100 FABRICATED (an internal `define` promoted to module
level by error recovery), because `;` `"` `#` `|` are prose inside an at-exp
text body and comment / string / reader-prefix tokens to the grammar. With the
gate: 0 missing, 0 wrong spans. On 94 `#lang punct` files: 0 symbols, where a
Markdown document ABOUT Racket would otherwise index its code samples.

The tests are split by tier. Most are ABSENCE tests, as in
``test_racket_language.py``: the risk is what gets emitted, not what is missed.
"""

import pytest

from jcodemunch_mcp.parser.extractor import (
    _parse_racket_symbols,
    _racket_blank_atexp_bodies,
    _racket_lang_of,
    _racket_tier,
    get_parser,
)


@pytest.fixture(autouse=True)
def _no_project_config(monkeypatch):
    """Answer the gate's built-in lists, not the developer's config file."""
    monkeypatch.setattr(
        "jcodemunch_mcp.config.get",
        lambda key, default=None, repo=None: default,
    )


@pytest.fixture
def langs(monkeypatch):
    """Install `racket_langs` without touching any real config file."""
    def _install(mapping):
        monkeypatch.setattr(
            "jcodemunch_mcp.config.get",
            lambda key, default=None, repo=None: (
                mapping if key == "racket_langs" else default
            ),
        )
    return _install


def _names(src: str, repo=None) -> set:
    return {s.name for s in _parse_racket_symbols(src.encode("utf-8"), "g.rkt", repo=repo)}


# ── reading the #lang line ────────────────────────────────────────────────

@pytest.mark.parametrize("head,expected", [
    (b"#lang racket/base\n", ("racket/base", None)),
    (b"#lang at-exp racket/base\n", ("at-exp", "racket/base")),
    (b"#lang punct opcraftco\n", ("punct", "opcraftco")),
    (b";; a comment first\n;; and another\n#lang racket\n", ("racket", None)),
    (b"#! /usr/bin/env racket\n#lang racket\n", ("racket", None)),
    (b"\n\n  #lang typed/racket\n", ("typed/racket", None)),
    (b"(module m racket/base (define x 1))\n", (None, None)),
    (b"", (None, None)),
], ids=["plain", "at-exp", "punct-with-arg", "after-comments", "after-shebang",
        "after-blank", "module-form", "empty"])
def test_lang_line_is_read_from_the_head_of_the_file(head, expected):
    assert _racket_lang_of(head) == expected


def test_lang_line_is_not_read_from_inside_the_body():
    """A `#lang` mentioned in a comment BELOW the first form is not the lang."""
    assert _racket_lang_of(b"(define x 1)\n;; #lang punct\n") == (None, None)


# ── the three tiers ───────────────────────────────────────────────────────

@pytest.mark.parametrize("lang,tier", [
    ("racket", "sexp"), ("racket/base", "sexp"), ("racket/gui", "sexp"),
    ("typed/racket", "sexp"), ("typed/racket/base", "sexp"), ("s-exp", "sexp"),
    ("info", "sexp"), ("scheme/base", "sexp"), ("plai", "sexp"), ("br", "sexp"),
    ("br/quicklang", "sexp"), ("web-server/insta", "sexp"), ("eopl", "sexp"),
    ("at-exp racket/base", "at-exp"), ("at-exp racket", "at-exp"),
    ("debug racket/base", "sexp"), ("errortrace racket", "sexp"),
    ("punct", "text"), ("punct opcraftco", "text"), ("scribble/manual", "text"),
    ("scribble/base", "text"), ("pollen", "text"), ("pollen/mode", "text"),
    ("markdown", "text"), ("brag", "text"), ("datalog", "text"),
    ("rhombus", "text"), ("at-exp scribble/base", "text"),
])
def test_built_in_tiers(lang, tier):
    assert _racket_tier(f"#lang {lang}\n(define x 1)\n".encode())[0] == tier


def test_no_lang_line_is_the_default_reader_and_therefore_sexp():
    """A `(module ...)` file is read by the default reader by construction."""
    assert _racket_tier(b"(module m racket/base (define x 1))\n") == ("sexp", "")


def test_an_unlisted_lang_is_text():
    """⚠ The asymmetry rule. A lang the gate does not know could be anything;
    a missed definition is recoverable by reading the file, a fabricated one is
    not. So unknown means no symbols, not a guess."""
    tier, written = _racket_tier(b"#lang conscript\n(defstep (s) 1)\n")
    assert tier == "text"
    assert written == "conscript"


def test_text_tier_emits_nothing_even_for_a_define_in_prose():
    """A Markdown document about Racket carries `(define ...)` in code samples.
    Before the gate, every one of those indexed as a module-level binding."""
    src = ("#lang punct\n\n# Defining things\n\nUse define:\n\n"
           "```racket\n(define (greet name) name)\n(struct posn (x y))\n```\n")
    assert _names(src) == set()


def test_text_tier_is_a_gate_not_a_parse_failure(caplog):
    """The file is announced as skipped at INFO, naming the lang, so a corpus
    of an unknown lang shows up in the log rather than as a silent zero."""
    import logging
    with caplog.at_level(logging.INFO, logger="jcodemunch_mcp.parser.extractor"):
        _names("#lang mylang\n(define x 1)\n")
    assert any("mylang" in r.getMessage() and "racket_langs" in r.getMessage()
               for r in caplog.records)


# ── project-declared langs ────────────────────────────────────────────────

def test_config_promotes_a_projects_own_lang(langs):
    langs({"conscript": "at-exp"})
    src = "#lang conscript\n(define (helper x) x)\n"
    assert "helper" in _names(src, repo="/proj")


def test_config_key_covers_its_sub_langs(langs):
    """`conscript` covers `conscript/with-require` and `conscript/local`,
    the way the built-in lists match `racket/*`."""
    langs({"conscript": "at-exp"})
    assert _racket_tier(b"#lang conscript/with-require\n", repo="/proj")[0] == "at-exp"
    assert _racket_tier(b"#lang conscript/local\n", repo="/proj")[0] == "at-exp"


def test_config_wins_over_the_built_in_lists(langs):
    """A project may demote a lang too -- `text` for a `racket/base` file set
    that is really generated data, or `sexp` for a lang we list as text."""
    langs({"racket/base": "text", "markdown": "sexp"})
    assert _racket_tier(b"#lang racket/base\n", repo="/proj")[0] == "text"
    assert _racket_tier(b"#lang markdown\n", repo="/proj")[0] == "sexp"


def test_no_repo_means_no_declarations(langs):
    langs({"conscript": "at-exp"})
    assert _racket_tier(b"#lang conscript\n", repo=None)[0] == "text"


@pytest.mark.parametrize("bad", [
    {"conscript": "prose"},           # not a tier
    {"conscript": ["at-exp"]},        # list, unhashable
    {"conscript": None},
    {3: "at-exp"},                    # non-string key
], ids=["bad-tier", "list", "null", "int-key"])
def test_malformed_entries_cost_one_entry_not_the_file(langs, bad):
    langs({**bad, "other": "sexp"})
    assert _racket_tier(b"#lang other\n", repo="/proj")[0] == "sexp"
    assert _racket_tier(b"#lang conscript\n", repo="/proj")[0] == "text"


# ── at-exp: text bodies are blanked, offsets are not ──────────────────────

HAZARDS = {
    "semicolon": "Thanks; you are done",
    "dquote": 'He said "hi',
    "hash": "Item #1 of 3",
    "bar": "a | b",
    "paren": "1) first, 2) second",
    "all-four": 'Item #1; "quoted" | done',
}


@pytest.mark.parametrize("text", list(HAZARDS.values()), ids=list(HAZARDS))
def test_atexp_text_body_hazards_no_longer_swallow_later_definitions(text):
    """⚠ Each of these is prose to Racket's at-exp reader and a token to the
    grammar. `"` alone took every later definition in the file with it; the
    others made the enclosing form an ERROR."""
    src = ("#lang at-exp racket/base\n"
           "(define (step)\n"
           f"  @html{{{text}}})\n"
           "(define (after) 1)\n")
    parsed = get_parser("racket").parse(src.encode())
    assert parsed.root_node.has_error, "non-vacuity: the raw text must break the grammar"
    assert _names(src) == {"step", "after"}


def test_atexp_nested_bodies_and_commands():
    src = ("#lang at-exp racket/base\n"
           "(define (step)\n"
           "  @html{@h1{Hi @|name|!} Do you; \"consent\"? @button[accepted]{Yes} @button[rejected]{No}})\n"
           "(define (after) 1)\n")
    assert _names(src) == {"step", "after"}


def test_blanking_keeps_every_offset():
    src = b'#lang at-exp racket/base\n(define (f) @p{a "b" ; c})\n(define g 2)\n'
    out = _racket_blank_atexp_bodies(src)
    assert len(out) == len(src)
    assert out.count(b"\n") == src.count(b"\n"), "line numbers must survive"
    # Outside the body, byte-identical; inside, spaces; the braces themselves kept.
    body_start = src.index(b"{") + 1
    body_end = src.index(b"}")
    assert out[:body_start] == src[:body_start]
    assert out[body_end:] == src[body_end:]
    assert out[body_start:body_end] == b" " * (body_end - body_start)


def test_symbols_from_an_atexp_file_hash_the_original_bytes():
    """Blanking is for the GRAMMAR. The symbol's content_hash and byte range
    must describe the file on disk, or an unchanged file re-hashes differently
    from its stored row and incremental indexing re-parses it forever."""
    src = b'#lang at-exp racket/base\n(define (f) @p{a "b"})\n'
    syms = _parse_racket_symbols(src, "g.rkt")
    (f,) = syms
    span = src[f.byte_offset:f.byte_offset + f.byte_length]
    assert span == b'(define (f) @p{a "b"})'
    from jcodemunch_mcp.parser.symbols import compute_content_hash
    assert f.content_hash == compute_content_hash(span)


@pytest.mark.parametrize("code", [
    '(define s "a { b")',          # brace inside a string
    "(define c #\\{)",              # brace character literal
    "(define d 1) ; open { here",   # brace inside a line comment
    "#| a { block |# (define e 1)", # brace inside a block comment
], ids=["string", "char", "line-comment", "block-comment"])
def test_a_brace_in_code_mode_does_not_open_a_body(code):
    """⚠ Each of these would otherwise blank to the next `}` or to the end of
    the file, taking real definitions with it."""
    src = f"#lang at-exp racket/base\n{code}\n(define (after) 1)\n"
    assert "after" in _names(src)


def test_a_brace_body_in_a_plain_racket_file_is_not_blanked():
    """`{}` are parentheses in the default reader -- `(let {[x 1]} x)` is
    legal Racket -- so the sexp tier must not touch them."""
    src = "#lang racket/base\n(define (f) (let {[x (helper 1)]} x))\n"
    (f,) = _parse_racket_symbols(src.encode(), "g.rkt")
    assert "helper" in f.call_references


def test_atexp_over_a_text_lang_is_still_text():
    assert _racket_tier(b"#lang at-exp scribble/base\n")[0] == "text"


# ── ERROR recovery: skipped in both directions ────────────────────────────

def test_a_recovery_promoted_internal_define_is_not_a_module_binding(caplog):
    """⚠ Regression for the fabrication class. An unterminated string inside
    a form makes tree-sitter re-parent the form's INTERNAL define under a root
    ERROR node (`list -> ERROR -> program`, the shape measured on a real
    `(define abc@ (unit ... (define (compute-payment) ...)))`). Walking ERROR
    reported `inner` as an importable module-level function."""
    import logging
    src = ('#lang racket\n(define outer\n  (thing\n    (define (inner) 1)\n'
           '    "))\n(define (after) 2)\n')
    tree = get_parser("racket").parse(src.encode())

    def ancestry(n):
        if n.type == "list" and n.text.startswith(b"(define (inner)"):
            chain, m = [], n
            while m is not None:
                chain.append(m.type)
                m = m.parent
            return chain
        for c in n.children:
            r = ancestry(c)
            if r:
                return r
    assert "ERROR" in (ancestry(tree.root_node) or []), \
        "non-vacuity: recovery must have promoted `inner` for this test to mean anything"

    with caplog.at_level(logging.WARNING, logger="jcodemunch_mcp.parser.extractor"):
        names = _names(src)
    assert "inner" not in names
    assert any("g.rkt" in r.getMessage() and "not indexed" in r.getMessage()
               for r in caplog.records), "the partial parse must be announced"


def test_a_clean_file_logs_no_parse_warning(caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="jcodemunch_mcp.parser.extractor"):
        assert _names("#lang racket\n(define (a) 1)\n") == {"a"}
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_definitions_after_a_stray_close_paren_are_missed_not_fabricated():
    """The other direction, pinned so it is a decision rather than an
    accident: a stray `)` puts every later top-level form under ERROR. They
    are lost -- the WARNING names the file -- because the same ERROR node is
    where recovery puts promoted internal defines, and the two cannot be told
    apart."""
    names = _names("#lang racket\n(define (a) 1))\n(define (b) 2)\n")
    assert names == {"a"}
