"""The Rust fidelity artifact must agree with the prose that quotes it.

⚠⚠ Written because this project has been bitten twice. In 1.108.298 EIGHT
artifacts mirrored one benchmark run and five were stale while both sync tests
passed. In 1.108.299 the Racket coverage figure had three mirrors and the PR
regenerated one. A number in a README is a COPY, and copies drift.

⚠ Figures are derived from `results.json` and checked as ROWS, not as a single
headline. A test that compares one total passes while every row underneath it is
wrong -- which is exactly what happened in .298.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

_HARNESS = pathlib.Path(__file__).parent.parent / "benchmarks" / "rust_fidelity"
_RESULTS = _HARNESS / "results.json"
_README = _HARNESS / "README.md"
_CORPUS = _HARNESS / "corpus.json"

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@pytest.fixture(scope="module")
def results():
    if not _RESULTS.exists():
        pytest.skip("rust fidelity results.json absent")
    return json.loads(_RESULTS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def readme():
    if not _README.exists():
        pytest.skip("rust fidelity README absent")
    return _README.read_text(encoding="utf-8")


def test_corpus_shas_are_real_shas():
    """⚠ A pin that is not 40 lowercase hex pins nothing.

    The first draft of corpus.json carried U+096B DEVANAGARI DIGIT FIVE from a
    shell heredoc. It renders identically and would have silently disabled the
    drift check.
    """
    corpus = json.loads(_CORPUS.read_text(encoding="utf-8"))
    assert corpus["targets"], "corpus declares no targets"
    for t in corpus["targets"]:
        assert _SHA_RE.match(t["sha"]), f"{t['id']}: sha is not 40 lowercase hex: {t['sha']!r}"


def test_results_were_measured_at_the_pinned_sha(results):
    corpus = json.loads(_CORPUS.read_text(encoding="utf-8"))
    pinned = {t["id"]: t["sha"] for t in corpus["targets"]}
    s = results["summary"]
    assert s["target"] in pinned, f"results target {s['target']!r} not in corpus"
    assert s["sha"] == pinned[s["target"]], "results.json was measured at a different SHA"
    assert s["sha_matches_corpus"] is True


def test_hard_gates_are_zero_in_the_published_artifact(results):
    """`extra` and `wrong_span` are the two bars. A published non-zero is a bug."""
    s = results["summary"]
    from harness import thresholds as _thresholds
    assert s["extra"] == _thresholds.floor("fidelity.rust.extra"), f"published artifact carries {s['extra']} fabrication(s)"
    assert s["wrong_span"] == _thresholds.floor("fidelity.rust.wrong_span"), f"published artifact carries {s['wrong_span']} wrong span(s)"


def test_summary_totals_are_derived_from_the_rows(results):
    """⚠ The .298 failure: a headline agreeing while its rows disagree.

    Every summary figure is recomputed from `per_file` here, so a hand-edited
    summary fails even though it looks internally consistent.
    """
    s, rows = results["summary"], results["per_file"]
    assert s["oracle_defs"] == sum(r["oracle_defs"] for r in rows)
    assert s["jcm_symbols"] == sum(r["jcm_symbols"] for r in rows)
    assert s["extra"] == sum(len(r["extra"]) for r in rows)
    assert s["wrong_span"] == sum(len(r["wrong_span"]) for r in rows)
    assert s["missing"] == sum(
        len(names) for r in rows for names in r["missing"].values()
    )
    assert s["clean_files"] == sum(
        1 for r in rows if not r["extra"] and not r["wrong_span"] and not r["missing"]
    )


def test_missing_by_kind_is_derived_from_the_rows(results):
    """No summary field carries this, so it must be recomputed to be checked."""
    s, rows = results["summary"], results["per_file"]
    recomputed: dict[str, int] = {}
    for r in rows:
        for kind, names in r["missing"].items():
            recomputed[kind] = recomputed.get(kind, 0) + len(names)
    assert s["missing_by_kind"] == recomputed


def test_coverage_pct_is_derived_not_typed(results):
    s = results["summary"]
    expected = round(100.0 * (s["oracle_defs"] - s["missing"]) / s["oracle_defs"], 1)
    assert s["coverage_pct"] == expected


@pytest.mark.parametrize(
    "field", ["oracle_defs", "jcm_symbols", "missing", "clean_files", "files_parsed"]
)
def test_readme_quotes_the_artifact(results, readme, field):
    """Every headline figure in the README must appear in the artifact.

    ⚠ Checked per FIELD rather than as one total. `.298` passed a sync test
    while five of eight mirrored artifacts were 22 days stale, because the check
    compared a grand total that happened to still agree.
    """
    value = results["summary"][field]
    assert str(value) in readme, (
        f"README does not quote {field}={value} from results.json; "
        "regenerate the table after re-measuring"
    )


def test_readme_quotes_the_pinned_sha(readme):
    corpus = json.loads(_CORPUS.read_text(encoding="utf-8"))
    for t in corpus["targets"]:
        assert t["sha"] in readme, f"README does not name the pinned sha for {t['id']}"


def test_readme_states_the_macro_ceiling(readme):
    """⚠ The one claim this harness CANNOT make must stay written down.

    `syn` parses and does not expand, so macro-generated items are unscored in
    both directions. A reader who misses that will over-read a green run.
    """
    lowered = readme.lower()
    assert "does not" in lowered and "expand" in lowered
    assert "macro" in lowered
