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
from jcodemunch_mcp.parser.imports import extract_imports, resolve_specifier
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


# ⚠ The value of a symbol-named define is not always children[2]. Each shape
# below filed a callable as `constant` -- a false statement an agent acts on
# when deciding whether a name can be called -- and every one is KNOWABLE from
# the text, unlike `(define curry (make-curry #f))`, which is not.

def test_define_contract_reads_the_value_after_the_contract():
    s = _by_name("(define/contract handler (-> any/c any/c) (lambda (x) x))")["handler"]
    assert s.kind == "function"
    assert "(-> any/c any/c)" in s.signature


def test_define_contract_with_a_non_lambda_value_is_a_constant():
    s = _by_name("(define/contract limit natural? 10)")["limit"]
    assert s.kind == "constant"
    assert "natural?" in s.signature


def test_typed_define_reads_the_value_after_the_annotation():
    s = _by_name("(define f : (-> Integer Integer) (lambda (x) x))")["f"]
    assert s.kind == "function"
    assert "(-> Integer Integer)" in s.signature


def test_typed_define_of_a_value_is_a_constant_with_its_type():
    s = _by_name("(define limit : Integer 10)")["limit"]
    assert s.kind == "constant"
    assert s.signature.endswith(": Integer")


@pytest.mark.parametrize("value", [
    "(match-lambda [_ 1])", "(match-lambda* [_ 1])", "(thunk 1)", "(thunk* 1)",
    "(case-lambda [(x) x] [(x y) y])",
], ids=["match-lambda", "match-lambda*", "thunk", "thunk*", "case-lambda"])
def test_lambda_shaped_macros_make_a_define_a_function(value):
    assert _by_name(f"(define f {value})")["f"].kind == "function"


def test_case_lambda_signature_shows_the_first_parameter_list_not_a_body():
    s = _by_name("(define f (case-lambda [(x) (frob x)] [(x y) y]))")["f"]
    assert s.signature == "(define f (case-lambda (x)))"


def test_define_syntaxes_binds_macros_which_are_functions():
    """The same rule `define-syntax` follows: a macro is invoked in operator
    position. `constant` contradicted it two blocks away in the same walker."""
    names = _by_name("(define-syntaxes (m1 m2) (values (lambda (s) s) (lambda (s) s)))")
    assert names["m1"].kind == "function" and names["m2"].kind == "function"


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


# ⚠ Adjacency. A docstring is the one place the index serves PROSE as fact,
# so a comment attached to the wrong form is a false statement, not a miss.
# Both shapes below shipped: the trailing comment of the previous form became
# the next form's docstring, and a file's header block became the first
# define's.

def test_a_trailing_comment_belongs_to_the_form_on_its_line_not_the_next():
    names = _by_name("(define alpha 1) ;; note about alpha\n(define beta 2)")
    assert names["beta"].docstring == ""


def test_a_comment_block_separated_by_a_blank_line_is_not_a_docstring():
    """The file-header shape: `#lang`, a description block, a blank line, the
    first define. guards.rkt's header was live-anchor's docstring."""
    src = ("#lang racket/base\n"
           ";; Every form here is something that LOOKS like a definition.\n"
           ";; The expander agrees none of these bind a name.\n"
           "\n"
           "(define live-anchor 1)")
    assert _by_name(src)["live-anchor"].docstring == ""


def test_a_contiguous_block_directly_above_still_attaches_in_full():
    src = (";; First line.\n"
           ";; Second line.\n"
           "(define (documented) 1)")
    assert _by_name(src)["documented"].docstring == "First line.\nSecond line."


def test_a_trailing_comment_does_not_join_the_next_forms_own_block():
    """`(define a 1) ;; about a` directly above `;; about b` must contribute
    nothing: the chain stops at the trailing comment, keeping `about b`."""
    src = ("(define a 1) ;; about a\n"
           ";; about b\n"
           "(define b 2)")
    assert _by_name(src)["b"].docstring == "about b"


def test_a_multi_line_block_comment_directly_above_attaches():
    src = ("#| Spans\n   two lines. |#\n"
           "(define (spanned) 1)")
    assert _by_name(src)["spanned"].docstring == "Spans\n   two lines."


# ── call references ───────────────────────────────────────────────────────

def test_call_references_name_callees_not_binding_forms():
    src = ("(define (uses-let)\n"
           "  (let ([z (helper 1)])\n"
           "    (if (odd? z) (compute z) (fallback z))))")
    refs = _by_name(src)["uses-let"].call_references
    assert {"helper", "odd?", "compute", "fallback"} <= set(refs)
    for not_a_call in ("let", "if", "z", "define"):
        assert not_a_call not in refs


# ⚠ Binding positions are not calls. Each shape below was measured producing
# a phantom reference: a parameter, a clause head, a pattern head or a struct
# field was attributed as a CALL of the enclosing function, and for a struct
# form, of whichever synthesised accessor was emitted last. Those references
# feed get_call_hierarchy, blast radius and get_untested_symbols' name match.

def _refs(src: str, name: str) -> set:
    return set(_by_name("#lang racket/base\n" + src)[name].call_references)


def test_lambda_parameters_are_not_calls():
    refs = _refs("(define (f lst) (map (lambda (item acc) (helper item)) lst))", "f")
    assert {"map", "helper"} <= refs
    assert "item" not in refs and "acc" not in refs


def test_every_for_variant_treats_its_clause_heads_as_bindings():
    src = ("(define (f lst)\n"
           "  (for/sum ([elem lst]) (score elem))\n"
           "  (for/vector ([v lst]) (shape v))\n"
           "  (for*/hash ([k lst] [w lst]) (values k (weigh w)))\n"
           "  (for/fold ([acc 0]) ([x lst]) (fold-step acc x)))")
    refs = _refs(src, "f")
    assert {"score", "shape", "weigh", "fold-step"} <= refs
    for binding in ("elem", "v", "k", "w", "acc", "x", "for/sum", "for/vector",
                    "for*/hash", "for/fold"):
        assert binding not in refs


def test_named_let_bindings_and_case_lambda_params_are_not_calls():
    src = ("(define (f)\n"
           "  (let loop ([i 0]) (when (< i 3) (loop (add1 i))))\n"
           "  ((case-lambda [(x) (one x)] [(x y) (two x y)]) 1))")
    refs = _refs(src, "f")
    assert {"loop", "add1", "<", "one", "two"} <= refs
    assert "i" not in refs and "x" not in refs


def test_match_patterns_are_not_calls_but_clause_bodies_are():
    src = ("(define (f v)\n"
           "  (match v\n"
           "    [(list a b) (pair-case a b)]\n"
           "    [(cons x _) (cons-case x)]\n"
           "    [(? number? n) (num-case n)]))")
    refs = _refs(src, "f")
    assert {"pair-case", "cons-case", "num-case"} <= refs
    for pattern_head in ("list", "cons", "?", "a", "x", "n"):
        assert pattern_head not in refs


def test_send_records_the_method_not_the_dispatcher():
    refs = _refs("(define (f obj) (send obj compute (arg-of obj)))", "f")
    assert {"compute", "arg-of"} <= refs
    assert "send" not in refs and "obj" not in refs


def test_new_records_the_class_and_not_the_init_names():
    refs = _refs("(define (f) (new widget% [width (measure)] [height 2]))", "f")
    assert {"widget%", "measure"} <= refs
    assert "width" not in refs and "height" not in refs and "new" not in refs


def test_struct_fields_and_option_lambdas_leave_the_accessors_clean():
    """A struct's synthesised accessors share the form's byte range, so the
    field list `(x y)` and the `#:guard (lambda (a b n) ...)` parameters were
    attributed to whichever accessor was emitted last."""
    syms = _parse("#lang racket/base\n"
                  "(struct posn (x y) #:guard (lambda (a b n) (values a b)))")
    for s in syms:
        assert s.call_references == [], (s.name, s.call_references)


def test_provide_specs_and_define_values_names_are_not_calls():
    src = ("(provide (contract-out [f (-> integer? integer?)]) (rename-out [f g]))\n"
           "(define-values (p q) (values 1 2))\n"
           "(define (f x) (h x))")
    refs = _refs(src, "f")
    assert refs == {"h"}


def test_class_body_declarations_are_not_calls():
    src = ("(define c%\n"
           "  (class object%\n"
           "    (init-field [w 1])\n"
           "    (field [h (initial-height)])\n"
           "    (define/public (area) (* w h))\n"
           "    (super-new)))")
    names = _by_name("#lang racket/base\n" + src)
    assert names["area"].call_references == ["*"]


def test_a_define_header_default_is_not_a_call_of_itself():
    """`(define (f [x (default)]) ...)`: `f` used to be recorded as calling
    `f`. The header is skipped whole; `default` is a lost call, which is a
    miss rather than a fabrication."""
    refs = _refs("(define (f [x 1]) (use x))\n(define (g) (f))", "g")
    assert refs == {"f"}


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


# ── import edges must RESOLVE, not merely parse ───────────────────────────
#
# ⚠⚠ An extracted edge nothing downstream can resolve is indistinguishable
# from no edge at all. The first cut of this parser produced correct
# specifiers that resolved to nothing for two of the four real require
# shapes, and the visible symptom was `find_dead_code` reporting 78% of the
# Racket collects tree as dead -- against 13% for a Python stdlib corpus
# indexed the same isolated way. Asserting on the extractor's output alone
# could not see it, which is why these tests go through resolve_specifier.

RACKET_FILES = frozenset({
    "racket/list.rkt", "racket/string.rkt",
    "app/main.rkt", "app/helper.rkt", "lib/util.rkt",
})


@pytest.mark.parametrize("specifier,expected", [
    # A collection path names <path>.rkt. `.rkt` is not in _ALL_EXTENSIONS,
    # so the generic candidate list never reaches it.
    ("racket/list", "racket/list.rkt"),
    # ⚠ A Racket STRING require is relative to the IMPORTING FILE and has no
    # `./` convention. The generic relative branch only fires on a leading
    # dot, so this -- the commonest intra-project form -- resolved to nothing.
    ("helper.rkt", "app/helper.rkt"),
    ("../lib/util.rkt", "lib/util.rkt"),
    ("./helper.rkt", "app/helper.rkt"),
], ids=["collection-path", "sibling-string", "parent-relative", "explicit-dot"])
def test_require_specifiers_resolve_to_files(specifier, expected):
    assert resolve_specifier(specifier, "app/main.rkt", RACKET_FILES) == expected


def test_a_string_require_is_relative_not_repo_rooted():
    """`(require "util.rkt")` from lib/ must NOT reach a repo-root util.rkt."""
    files = frozenset({"util.rkt", "lib/caller.rkt", "lib/util.rkt"})
    assert resolve_specifier("util.rkt", "lib/caller.rkt", files) == "lib/util.rkt"


def test_an_unresolvable_collection_require_yields_no_edge():
    """`(require racket/base)` in a project that does not vendor Racket names
    an installed collection, not a file. Inventing an edge would be worse
    than having none."""
    assert resolve_specifier("racket/base", "app/main.rkt",
                             frozenset({"app/main.rkt"})) is None


# ── synthesised struct bindings ───────────────────────────────────────────
#
# `(struct posn (x y))` binds `posn?`, `posn-x` and `posn-y` in addition to
# `posn`, and those are the names callers actually write -- but none of them
# occur anywhere in the file, so they exist only if synthesised.
#
# ⚠ Every expectation below was read off Racket's own expander for that exact
# variant, not from the documentation. The rules differ in ways that are easy
# to get backwards, and one of them (constructor-name) shipped as a fabricated
# name until the fidelity harness caught it.


def _names(src: str) -> set:
    return {s.name for s in _parse("#lang racket/base\n" + src)}


def test_plain_struct_binds_predicate_and_accessors():
    assert _names("(struct posn (x y))") == {"posn", "posn?", "posn-x", "posn-y"}


def test_struct_does_not_bind_a_make_constructor():
    """`(struct posn ...)` binds `posn` as the constructor; only the
    `define-struct` family binds `make-posn`."""
    assert "make-posn" not in _names("(struct posn (x y))")


def test_define_struct_binds_a_make_constructor():
    assert "make-posn" in _names("(define-struct posn (x y))")


def test_struct_type_descriptor_is_deliberately_not_emitted():
    """`struct:posn` is a descriptor almost nobody calls, and one more symbol
    matching every query for the struct is pure ranking noise."""
    assert "struct:posn" not in _names("(struct posn (x y))")


def test_struct_level_mutable_binds_a_setter_per_field():
    assert _names("(struct posn (x y) #:mutable)") == {
        "posn", "posn?", "posn-x", "posn-y", "set-posn-x!", "set-posn-y!"}


def test_per_field_mutable_binds_only_that_setter():
    n = _names("(struct posn (x [y #:mutable]))")
    assert "set-posn-y!" in n
    assert "set-posn-x!" not in n


def test_inherited_fields_keep_the_supertypes_accessors():
    """⚠ `(struct derived base (c))` binds `derived-c` and NOT `derived-a`.
    Synthesising accessors for inherited fields would invent names."""
    n = _names("(struct base (a b))\n(struct derived base (c))")
    assert {"base-a", "base-b", "derived-c", "derived?"} <= n
    assert "derived-a" not in n and "derived-b" not in n


def test_constructor_name_replaces_rather_than_adds():
    """⚠ Regression. `#:constructor-name` REPLACES the default constructor, so
    `make-<name>` is not bound. Emitting it anyway invented
    `make-base-object/c` in racket/private/object-c.rkt, which the fidelity
    harness caught as the only fabricated name in 211 files."""
    n = _names("(define-struct posn (x y) #:constructor-name NEVER_CALL_THIS)")
    assert "NEVER_CALL_THIS" in n
    assert "make-posn" not in n


def test_extra_constructor_name_adds_alongside_the_default():
    n = _names("(define-struct posn (x y) #:extra-constructor-name build-posn)")
    assert {"make-posn", "build-posn"} <= n


def test_serializable_struct_binds_the_same_accessor_set():
    assert {"posn", "posn?", "posn-x", "posn-y"} <= _names(
        "(serializable-struct posn (x y))")


def test_serializable_struct_versions_finds_the_real_field_list():
    """The version number sits between the name and the fields, and a trailing
    `()` follows them -- the field list is the FIRST list, not a fixed index."""
    assert {"posn-x", "posn-y"} <= _names(
        "(serializable-struct/versions posn 1 (x y) ())")


def test_contracted_struct_field_names_drop_the_contract():
    """`(struct/contract posn ([x number?] ...))` -- the field is `x`, not the
    whole `[x number?]` clause."""
    assert {"posn-x", "posn-y"} <= _names(
        "(struct/contract posn ([x number?] [y number?]))")


def test_synthesised_names_point_at_the_struct_form():
    """They share the struct's byte range, so `get_symbol_source("posn-x")`
    returns the form that generates it -- the honest answer to "where does this
    come from"."""
    syms = {s.name: s for s in _parse("#lang racket/base\n(struct posn (x y))")}
    struct, accessor = syms["posn"], syms["posn-x"]
    assert accessor.line == struct.line
    assert accessor.byte_offset == struct.byte_offset
    assert accessor.parent == syms["posn"].id
    assert accessor.kind == "function"
    assert "posn-x" in accessor.signature


@pytest.mark.parametrize("opts", [
    "#:transparent", "#:prefab", "#:authentic", "#:sealed", "#:inspector #f",
    "#:guard (lambda (a b n) (values a b))",
    "#:property prop:procedure (lambda (s) 1)",
    "#:reflection-name (quote other)",
    "#:transparent #:authentic",
], ids=["transparent", "prefab", "authentic", "sealed", "inspector",
        "guard", "property", "reflection-name", "combined"])
def test_struct_options_do_not_disturb_the_derived_names(opts):
    """Options follow the field list, so none of them may displace it.

    `#:guard` and `#:property` in particular take a `(lambda ...)` argument --
    another list node -- so a field-list rule that took the LAST list, or a
    fixed index, would read the guard as the fields.
    """
    assert _names(f"(struct posn (x y) {opts})") == {
        "posn", "posn?", "posn-x", "posn-y"}


def test_methods_clause_does_not_leak_its_internal_defines():
    """`#:methods gen:x [(define (f ...) ...)]` holds real `define` forms; they
    are class members, not module-level bindings."""
    n = _names("(require racket/generic)\n"
               "(struct posn (x y) #:methods gen:custom-write "
               "[(define (write-proc s p m) (void))])")
    assert {"posn", "posn?", "posn-x", "posn-y"} <= n
    assert "write-proc" not in n


def test_auto_fields_get_an_accessor():
    assert "posn-z" in _names("(struct posn (x y [z #:auto]) #:auto-value 0)")


def test_a_struct_with_no_fields_still_binds_a_predicate():
    assert _names("(struct posn ())") == {"posn", "posn?"}


@pytest.mark.parametrize("kw", ["#:name", "#:extra-name"])
def test_name_keywords_bind_a_type_not_a_callable(kw):
    """Both bind their argument as a struct-type transformer. Emitting it as a
    function would claim you can call it."""
    syms = {s.name: s for s in _parse(f"#lang racket/base\n(struct posn (x y) {kw} posn-type)")}
    assert "posn-type" in syms
    assert syms["posn-type"].kind == "type"


# ── project-declared defining forms ───────────────────────────────────────
#
# A Racket project routinely defines its own defining forms with
# `define-syntax`, and what those bind is not recoverable from the text:
# `(defstep (check-admin) ...)` is indistinguishable from a function call.
#
# ⚠ Two automatic guesses were measured against Racket's expander and both
# invent names. Treating any `def*` head as a definition recovers 140 real
# names across the collects tree and fabricates 225 -- `(default d ...)` and
# `(definify map ...)` are calls. Restricting that to macros the repo defines
# itself still fabricates 168, because `(define-logger enter!)` binds
# `log-enter!-debug` rather than `enter!`. So the only sound source for the
# claim is the user making it, which is what this key is.


@pytest.fixture
def declared(monkeypatch):
    """Install racket_definition_forms without touching any real config file."""
    def _install(forms):
        monkeypatch.setattr(
            "jcodemunch_mcp.config.get",
            lambda key, default=None, repo=None: (
                forms if key == "racket_definition_forms" else default
            ),
        )
    return _install


CONSCRIPT = {"defstep": "function", "defstudy": "constant", "defvar": "constant"}


def _decl_names(src, repo="/proj"):
    from jcodemunch_mcp.parser.extractor import _parse_racket_symbols
    return {s.name: s for s in _parse_racket_symbols(
        ("#lang racket/base\n" + src).encode("utf-8"), "p.rkt", repo=repo)}


def test_declared_forms_are_inert_by_default(declared):
    """The default is {}, and an unconfigured project must parse exactly as
    before -- verified separately against the whole fidelity corpus."""
    declared({})
    assert _decl_names("(defstep (check-admin) (void))") == {}


def test_declared_header_form_binds_the_head_of_its_parameter_list(declared):
    declared(CONSCRIPT)
    s = _decl_names("(defstep (check-admin) (void))")["check-admin"]
    assert s.kind == "function"
    assert s.line == 2


def test_declared_symbol_form_binds_the_second_element(declared):
    declared(CONSCRIPT)
    names = _decl_names("(defstudy conscript-example (--> a b))\n(defvar current-matrix)")
    assert names["conscript-example"].kind == "constant"
    assert names["current-matrix"].kind == "constant"


def test_no_repo_means_no_declarations(declared):
    """Parsing outside a project cannot consult a project file."""
    declared(CONSCRIPT)
    assert _decl_names("(defstep (check-admin) (void))", repo=None) == {}


def test_a_declaration_cannot_shadow_real_racket_syntax(declared):
    """Declared forms are matched AFTER every built-in, so declaring `define`
    or `struct` gets the built-in handling rather than the user's."""
    declared({"define": "constant", "struct": "constant"})
    names = _decl_names("(define (f x) x)\n(struct posn (a b))")
    assert names["f"].kind == "function", "built-in define must win"
    assert names["posn"].kind == "class", "built-in struct must win"
    assert "posn-a" in names, "struct synthesis must still run"


@pytest.mark.parametrize("bad", [
    {"defstep": "wizard"},                    # kind not in the allow-list
    {"defstep": "method"},                    # method belongs to a class body
    {"defstep": {"kind": "function"}},        # object form is not accepted
    {"defstep": None},
    {"defstep": ["function"]},
], ids=["bad-kind", "method-kind", "object-form", "null", "list"])
def test_malformed_declarations_cost_one_form_not_the_file(declared, bad):
    """A typo must not take the rest of the file with it."""
    declared(bad)
    names = _decl_names("(defstep (check-admin) (void))\n(define (ordinary x) x)")
    assert "ordinary" in names, "the rest of the file must still parse"


def test_one_form_may_appear_in_both_shapes(declared):
    """⚠ The reason the name position is inferred rather than declared.
    Measured on a real project, `defstep` appears 44 times as
    `(defstep (name args) ...)` and once as `(defstep name ...)`. A declared
    position would have missed one of them."""
    declared({"defstep": "function"})
    names = _decl_names("(defstep (header-shaped) (void))\n(defstep symbol-shaped)")
    assert "header-shaped" in names
    assert "symbol-shaped" in names


def test_declared_form_inside_a_submodule_is_scoped(declared):
    declared(CONSCRIPT)
    names = _decl_names("(module+ test\n  (defstep (t-helper) (void)))")
    assert names["t-helper"].qualified_name == "test::t-helper"


# ── the descent allow-list, asserted in BOTH directions ───────────────────
#
# ⚠⚠ This guard was deleted once and nothing noticed. An edit that moved the
# declared-forms block spliced away the `Nothing matched` return with it, so
# `_walk` recursed into every unrecognised form. All eight CI jobs and the full
# local suite stayed green, because every test over this path asserted
# PRESENCE -- that a splicing head IS descended into -- and descending into
# everything satisfies that too. Only the fidelity corpus saw it: `extra` went
# 0 -> 5 and `wrong_span` 0 -> 26, re-emitting the very names #548 added the
# guard to suppress.
#
# So both directions are pinned here. The absence test fails if the guard is
# removed; the presence test fails if a future early return over-suppresses.


def test_unrecognised_forms_are_not_descended(declared):
    """A `define` inside a form we do not recognise is an INTERNAL definition.

    `(some-unknown-macro (define hidden 42))` binds nothing importable, so
    emitting `hidden` claims a binding Racket does not create. Measured on the
    real corpus, losing this guard fabricated `cmp/c`, `elem/c`, `equal-key/c`,
    `kind/c` and `lazy?` from contract combinators in racket/set.rkt.
    """
    declared({})
    names = _decl_names(
        "(define (real-fn x) (+ x 1))\n"
        "(some-unknown-macro\n"
        "  (define hidden-internal 42)\n"
        "  (define (hidden-fn y) y))"
    )
    assert "real-fn" in names, "non-vacuity: the file must still parse"
    assert "hidden-internal" not in names
    assert "hidden-fn" not in names


def test_splicing_forms_are_still_descended(declared):
    """The other direction. `begin` SPLICES, so `(begin (define a 1))` really
    does define `a` at module level -- a guard that returned on everything
    would silently drop it."""
    declared({})
    names = _decl_names("(begin (define spliced-in 1))")
    assert "spliced-in" in names
