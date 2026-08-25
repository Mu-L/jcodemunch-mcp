"""Racket language support.

Racket's tree-sitter grammar is fully homoiconic -- there are no named
``define`` / ``struct`` nodes, so every form is ``list`` -> ``symbol`` and the
whole extractor is head-symbol dispatch. That makes several of the tests below
ABSENCE tests: the risk is not that a definition is missed, it is that
something which is not a definition is emitted as one.

⚠ Config is isolated deliberately. ``parse_file`` consults
``is_language_enabled``, so without the fixture this suite reports the
developer's ``~/.code-index/config.jsonc`` rather than the parser. A config
carrying an explicit ``languages`` list written before Racket existed reports
zero symbols and looks exactly like a real defect -- the #411 failure mode, and
the reason practice #8 exists.
"""
import pytest

from jcodemunch_mcp.parser.extractor import parse_file
from jcodemunch_mcp.parser.imports import extract_imports
from jcodemunch_mcp.parser.languages import LANGUAGE_EXTENSIONS, LANGUAGE_REGISTRY


@pytest.fixture(autouse=True)
def _all_languages_enabled(monkeypatch):
    """Answer the parser, not the developer's config file."""
    monkeypatch.setattr(
        "jcodemunch_mcp.config.is_language_enabled",
        lambda language, repo=None: True,
    )


def _parse(source: str, filename: str = "demo.rkt"):
    return parse_file(source, filename, "racket",
                      source_bytes=source.encode("utf-8"))


def _by_name(source: str) -> dict:
    return {s.name: s for s in _parse(source)}


# ── wiring ────────────────────────────────────────────────────────────────

def test_racket_parser_available():
    """Non-vacuity for everything below: the grammar must load."""
    from tree_sitter_language_pack import get_parser
    assert get_parser("racket") is not None


@pytest.mark.parametrize("ext", [".rkt", ".rktl", ".rktd"])
def test_extension_mapping(ext):
    assert LANGUAGE_EXTENSIONS[ext] == "racket"


def test_language_in_registry():
    assert "racket" in LANGUAGE_REGISTRY
    assert LANGUAGE_REGISTRY["racket"].ts_language == "racket"


def test_scribble_is_not_claimed():
    """`.scrbl` is excluded on a measurement, not an oversight.

    A Scribble file parses with has_error False and yields garbage -- prose
    words become top-level symbols and `@defproc[(greet ...)]` extracts
    nothing. A green parse with an empty result and no error signal is worse
    than no support at all.
    """
    assert ".scrbl" not in LANGUAGE_EXTENSIONS


# ── definition forms ──────────────────────────────────────────────────────

def test_procedure_define_is_a_function():
    s = _by_name("(define (greet name) (string-append \"hi \" name))")["greet"]
    assert s.kind == "function"
    assert s.line == 1
    assert "(define (greet name))" in s.signature


def test_value_define_is_a_constant():
    assert _by_name('(define greeting "hello")')["greeting"].kind == "constant"


def test_lambda_valued_define_is_a_function():
    """The positive half of the lambda/value discrimination."""
    assert _by_name("(define handler (lambda (x) x))")["handler"].kind == "function"


def test_curried_define_finds_the_leftmost_head():
    """A depth-1-only implementation returns `(adder a)` or nothing."""
    names = _by_name("(define ((adder a) b) (+ a b))")
    assert "adder" in names
    assert names["adder"].kind == "function"


def test_deeply_curried_define():
    assert "curry3" in _by_name("(define (((curry3 a) b) c) a)")


@pytest.mark.parametrize("form", ["struct", "define-struct", "struct/contract"])
def test_struct_forms_are_classes(form):
    assert _by_name(f"({form} point (x y))")["point"].kind == "class"


def test_struct_supertype_is_not_mistaken_for_the_name():
    """`(struct 3d-point point (z))` puts the SUPERTYPE in the slot where the
    field list would otherwise be. The name is children[1], never 'the symbol
    before the field list'."""
    names = _by_name("(struct 3d-point point (z))")
    assert "3d-point" in names
    assert names["3d-point"].kind == "class"


def test_define_type_is_a_type():
    s = _by_name("(define-type Point (Pairof Integer Integer))")["Point"]
    assert s.kind == "type"
    assert "(Pairof Integer Integer)" in s.signature


def test_define_syntax_rule_is_a_function():
    assert _by_name("(define-syntax-rule (swap! a b) (void))")["swap!"].kind == "function"


def test_define_syntax_with_a_transformer_is_a_function_not_a_constant():
    """A macro is invoked in operator position, so it is a `function`.

    Regression: routing this through the lambda/value check squashed every
    `(define-syntax name (syntax-rules ...))` to `constant`, because
    `syntax-rules` is not a lambda head.
    """
    src = "(define-syntax alias (syntax-rules () [(_ a b) (define a b)]))"
    assert _by_name(src)["alias"].kind == "function"


def test_define_values_binds_every_name():
    names = _by_name("(define-values (q r) (quotient/remainder 7 2))")
    assert names["q"].kind == "constant"
    assert names["r"].kind == "constant"


def test_define_values_with_a_dotted_tail_is_skipped():
    """`(define-values (a . rest) ...)` carries a `dot` node; emitting from it
    would invent a binding named `.`."""
    names = _by_name("(define-values (a . rest) (values 1 2))")
    assert "a" not in names and "rest" not in names


# ── absence: things that are not definitions ──────────────────────────────

def test_internal_helper_defines_are_not_emitted():
    """The return-after-match rule. An internal helper is not part of the
    file's interface; emitting it would inflate outlines and make every helper
    look unreferenced to dead-code analysis."""
    names = _by_name("(define (outer q) (define (inner r) r) (inner q))")
    assert "outer" in names
    assert "inner" not in names


def test_sexp_commented_definition_is_absent():
    """`#;` is how Racketeers disable code. `sexp_comment` is a NAMED wrapper
    holding a real `list`, so without a guard the disabled definition appears
    in outlines and counts as live."""
    names = _by_name("#;(define commented-out 3)\n(define live 1)")
    assert "live" in names, "non-vacuity: the guard must not eat the file"
    assert "commented-out" not in names


@pytest.mark.parametrize("src,ghost", [
    ("'(define quoted-x 1)", "quoted-x"),
    ("`(define qq 2)", "qq"),
    ("#'(define stx-x 1)", "stx-x"),
    ("#`(define qs 4)", "qs"),
])
def test_quoted_data_is_not_a_definition(src, ghost):
    names = _by_name(f"{src}\n(define live 1)")
    assert "live" in names
    assert ghost not in names


def test_macro_template_body_does_not_leak_symbols():
    src = "(define-syntax alias (syntax-rules () [(_ a b) (define a b)]))"
    names = _by_name(src)
    assert "alias" in names
    assert "a" not in names and "b" not in names


def test_let_bindings_never_become_symbols():
    names = _by_name("(let ([x 1] [y 2]) (+ x y))\n(define live 1)")
    assert "live" in names
    assert "x" not in names and "y" not in names


def test_head_symbol_is_case_sensitive():
    """Common Lisp readers upcase, so _parse_commonlisp_symbols lowercases the
    head. Racket is case-sensitive; copying that would make `(Define x 1)` a
    definition."""
    assert "x" not in _by_name("(Define x 1)")


def test_lang_only_file_yields_no_symbols():
    assert _parse("#lang racket/base\n;; just a comment\n") == []


# ── nesting ───────────────────────────────────────────────────────────────

def test_submodule_opens_a_scope_and_members_stay_functions():
    """A submodule's members are module-level definitions, not object members."""
    names = _by_name("(module+ test\n  (define (t-helper x) x))")
    assert names["test"].kind == "class"
    helper = names["t-helper"]
    assert helper.kind == "function"
    assert helper.qualified_name == "test::t-helper"


def test_class_members_become_methods_with_a_parent():
    src = ("(define my-class%\n"
           "  (class object%\n"
           "    (super-new)\n"
           "    (define/public (area) (* 2 2))\n"
           "    (define/private (secret) 1)))")
    names = _by_name(src)
    assert names["my-class%"].kind == "class"
    area = names["area"]
    assert area.kind == "method"
    assert area.qualified_name == "my-class%::area"
    # summarizer/file_summarize.py counts methods via s.parent.endswith(...),
    # so a method without a parent is invisible to it.
    assert area.parent == "demo.rkt::my-class%#class"
    assert names["secret"].kind == "method"


# ── typed racket ──────────────────────────────────────────────────────────

def test_type_annotation_attaches_and_does_not_duplicate():
    """`(: f type)` must enrich the define's signature, never emit its own
    symbol -- two same-named symbols of different kinds in one file would give
    search_symbols a duplicate pair and find_dead_code a phantom type."""
    syms = _parse("(: f (-> Integer Integer))\n(define (f n) n)")
    fs = [s for s in syms if s.name == "f"]
    assert len(fs) == 1
    assert fs[0].kind == "function"
    assert "(-> Integer Integer)" in fs[0].signature


def test_stale_annotation_does_not_attach_to_a_later_define():
    syms = _parse("(: f (-> Integer Integer))\n(define (f n) n)\n(define (g m) m)")
    g = next(s for s in syms if s.name == "g")
    assert "Integer" not in g.signature


# ── docstrings ────────────────────────────────────────────────────────────

def test_preceding_semicolon_comment_becomes_the_docstring():
    """The shared _clean_comment_markers has no `;` branch, so a naive reuse
    would leave the semicolons attached."""
    s = _by_name(";; Greet a person by name.\n(define (greet n) n)")["greet"]
    assert s.docstring == "Greet a person by name."


def test_block_comment_becomes_the_docstring():
    s = _by_name("#| Adds two numbers. |#\n(define (add a b) (+ a b))")["add"]
    assert s.docstring == "Adds two numbers."


# ── call references ───────────────────────────────────────────────────────

def test_call_references_name_callees_not_binding_forms():
    src = ("(define (uses-let)\n"
           "  (let ([z (helper 1)])\n"
           "    (if (odd? z) (compute z) (fallback z))))")
    refs = _by_name(src)["uses-let"].call_references
    assert {"helper", "odd?", "compute", "fallback"} <= set(refs)
    for not_a_call in ("let", "if", "z", "define"):
        assert not_a_call not in refs


# ── imports ───────────────────────────────────────────────────────────────

def test_require_extraction():
    src = ('(require racket/list\n'
           '         (only-in racket/string string-join)\n'
           '         "helper.rkt"\n'
           '         (prefix-in h: "../lib/util.rkt")\n'
           '         (for-syntax racket/base)\n'
           '         (submod "." test))')
    edges = {e["specifier"]: e["names"] for e in extract_imports(src, "a.rkt", "racket")}
    assert edges["racket/list"] == []
    assert edges["racket/string"] == ["string-join"]
    assert edges["helper.rkt"] == []
    assert edges["../lib/util.rkt"] == []
    assert "racket/base" in edges
    # (submod "." test) names a submodule of THIS file, not another file.
    assert not any(k.startswith(".") and k != "../lib/util.rkt" for k in edges)


def test_rename_in_records_the_source_side_name():
    """`(rename-in m [f g])` records `f`, the name at the definition site.

    This is the reduction _clean_names already applies to `import {a as b}` and
    Gleam's `X as Y` for every other language -- it is what makes the edge point
    at a real symbol.
    """
    edges = extract_imports('(require (rename-in "m.rkt" [f g]))', "a.rkt", "racket")
    assert edges == [{"specifier": "m.rkt", "names": ["f"]}]


def test_requires_inside_comments_are_ignored():
    src = ';; (require fake/one)\n#| (require fake/two) |#\n(require real/three)'
    specs = [e["specifier"] for e in extract_imports(src, "a.rkt", "racket")]
    assert specs == ["real/three"]
