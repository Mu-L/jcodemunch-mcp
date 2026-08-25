"""Racket extraction fidelity, gated without a Racket install.

`benchmarks/racket_fidelity/` compares our extractor against Racket's own
expander. That needs Racket on PATH, so it is a benchmark rather than a test.
This file closes the gap: the expander's answer for a small fixture set is
FROZEN into `tests/fixtures/racket_oracle.json`, so the buckets that must never
be non-zero are checked everywhere, CI included.

The bar is asymmetric on purpose. An incomplete index makes an agent read the
file; a WRONG one makes it repeat a falsehood. So:

  extra       a name we assert that Racket does not know   -> must be 0
  wrong_span  the definition is not inside the bytes we
              would hand back for that symbol              -> must be 0
  missing     a name a human wrote that we did not find    -> pinned, not zero

The classifier is imported from the benchmark rather than reimplemented, so
there is one definition of what each bucket means.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "racket"
FROZEN = REPO_ROOT / "tests" / "fixtures" / "racket_oracle.json"
CLASSIFIER = REPO_ROOT / "benchmarks" / "racket_fidelity" / "run_fidelity.py"


def _load_classifier():
    spec = importlib.util.spec_from_file_location("_racket_fidelity", CLASSIFIER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def frozen() -> dict:
    return json.loads(FROZEN.read_text())["files"]


@pytest.fixture(scope="module")
def classify():
    return _load_classifier().classify


@pytest.fixture(autouse=True)
def _all_languages_enabled(monkeypatch):
    monkeypatch.setattr(
        "jcodemunch_mcp.config.is_language_enabled",
        lambda language, repo=None: True,
    )


def _result(classify, frozen, name: str) -> dict:
    return classify(FIXTURES / name, frozen[name])


FIXTURE_NAMES = ["basics.rkt", "guards.rkt", "macros.rkt"]


def test_frozen_data_covers_every_fixture(frozen):
    """A fixture with no frozen answer is silently unmeasured."""
    on_disk = {p.name for p in FIXTURES.glob("*.rkt")}
    assert on_disk == set(FIXTURE_NAMES) == set(frozen)


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_no_fabricated_symbols(classify, frozen, name):
    """Nothing we emit may be a name Racket does not know.

    This is the bucket the whole exercise exists for: a symbol an agent trusts
    and cannot find, or worse, calls.
    """
    extra = _result(classify, frozen, name)["extra"]
    assert extra == [], f"{name} emits names the expander does not know: {extra}"


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_every_definition_lies_inside_its_reported_span(classify, frozen, name):
    """`get_symbol_source` must return bytes that contain the definition."""
    spans = _result(classify, frozen, name)["wrong_span"]
    assert spans == [], f"{name} reports spans that exclude the definition: {spans}"


def test_guards_fixture_is_not_vacuous(classify, frozen):
    """The absence file must still yield its anchors.

    Without this, a walker that returned [] for everything would pass every
    fabrication test above.
    """
    from jcodemunch_mcp.parser.extractor import _parse_racket_symbols
    names = {s.name for s in _parse_racket_symbols(
        (FIXTURES / "guards.rkt").read_bytes(), "guards.rkt")}
    assert {"live-anchor", "outer-with-helper"} <= names


def test_macro_defined_names_are_the_named_ceiling(classify, frozen):
    """The irreducible gap, pinned by name.

    `(define-constants fasl-box-type ...)` is the shape of racket/fasl.rkt's own
    macro (49 names) and racket/list.rkt's `(define-lgetter second 2)` (12
    names). A human typed these names -- the expander marks them
    syntax-original -- but no `define` form exists, so no static parser can
    reach them.

    Pinned rather than tolerated: if this set SHRINKS someone found a way in and
    should say so; if it GROWS the extractor lost ground it used to hold.
    """
    missing = _result(classify, frozen, "macros.rkt")["missing"]
    assert set(missing) == {"fasl-box-type", "fasl-char-type", "fasl-eof-type"}
    # The macro itself, and an ordinary define beside it, stay reachable -- the
    # gap is the macro's OUTPUT, not the file.
    from jcodemunch_mcp.parser.extractor import _parse_racket_symbols
    names = {s.name for s in _parse_racket_symbols(
        (FIXTURES / "macros.rkt").read_bytes(), "macros.rkt")}
    assert {"define-constants", "reachable-by-static-parsing"} <= names


def test_basics_fixture_is_fully_covered(classify, frozen):
    """The forms the extractor claims to handle must actually be complete.

    A coverage number averaged over a corpus can hide a form that never works;
    this file holds one instance of each supported form, so it must come back
    with nothing missing.
    """
    missing = _result(classify, frozen, "basics.rkt")["missing"]
    assert missing == [], f"a supported form is not being extracted: {missing}"
