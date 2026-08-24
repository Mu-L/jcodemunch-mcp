"""The realistic baseline: grep the corpus, then open the top N files.

The published baseline has always been "concatenate every indexed source file",
which is a **ceiling nobody pays**. No agent reads an entire repository before
acting; it greps and opens a few files. Dividing by the ceiling overstates the
advantage, and measuring it showed by how much: on the pinned corpus the
grep-then-read baseline is **11.8%** of the read-all figure, so the headline
ratio falls from **237.3x to 27.9x** and the reduction from **99.6% to 96.4%**.

⚠⚠ **A baseline you control is worthless unless every modelling choice is made
in its favour.** These tests pin the choices that keep it honest, because each
one is a lever that would flatter us if quietly reversed:

* the headline grep cost is `rg -l` (paths only), the *leanest* real output —
  `rg` with matched lines is measured too and is strictly larger, and using it
  would roughly double the baseline and hand us ~49x instead of ~28x;
* files are ranked by match count, giving the baseline a better-than-chance
  shot at the right file, where real grep output has no ranking at all;
* matching is case-insensitive substring on ANY term, the most permissive
  reading;
* both baselines read through the **same** reader, so the ratio between them
  describes two workflows and not two corpora.

⚠ It must also stay measured **in the same run** as the jCodeMunch side. A live
number beside a stored constant is the defect that ran four months here — see
`tests/test_benchmark_reference.py` and jcm CLAUDE.md maintenance rule 4.
"""

import ast
import importlib.util
import pathlib
import sys

import pytest
from importlib.util import find_spec

BENCH = pathlib.Path(__file__).resolve().parents[1] / "benchmarks"
HARNESS_PATH = BENCH / "harness" / "run_benchmark.py"

# ⚠⚠ `find_spec`, NOT `pytest.importorskip`. At module scope importorskip
# RAISES during import, so this whole file would collapse to a single
# "1 skipped" line however many tests it holds -- a CI box quietly missing
# tiktoken would look like a healthy run rather than one 9 tests short.
# find_spec asks the same question without raising: every test is collected
# and skipped individually. The imports below need the package present, so
# they move under the flag.
_HAS_TIKTOKEN = find_spec("tiktoken") is not None
pytestmark = pytest.mark.skipif(
    not _HAS_TIKTOKEN, reason="tiktoken not installed"
)


def _load_harness():
    spec = importlib.util.spec_from_file_location("_bench_harness", HARNESS_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_bench_harness"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def harness():
    return _load_harness()


class _FakeIndex:
    def __init__(self, files):
        self.source_files = list(files)


class _FakeStore:
    """Duck-types the two IndexStore members the baselines actually use."""

    def __init__(self, tmp_path, files: dict[str, str]):
        self._dir = tmp_path
        for rel, text in files.items():
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")

    def _content_dir(self, owner, name):
        return self._dir

    def get_file_content(self, owner, name, rel_path, index):
        return ""


CORPUS = {
    "router.py": "def route():\n    # ROUTER dispatch\n    return handler\n" * 4,
    "middleware.py": "def middleware():\n    pass\n" * 3,
    "unrelated.py": "x = 1\n" * 40,
}


@pytest.fixture
def store_and_index(tmp_path):
    return _FakeStore(tmp_path, CORPUS), _FakeIndex(CORPUS)


def test_grep_baseline_is_measured_not_constant(harness):
    """It must be a function of the corpus, not a literal parked in the file."""
    src = HARNESS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "measure_grep_baseline"
    )
    # It has to actually read the corpus it was handed.
    calls = {
        n.func.id for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "_read_source" in calls, "the grep baseline must read real file content"
    assert "count_tokens" in calls, "the grep baseline must count real tokens"


def test_both_baselines_share_one_reader(harness):
    """A ratio between two baselines reading different bytes is meaningless."""
    src = HARNESS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for name in ("measure_baseline", "measure_grep_baseline"):
        fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == name
        )
        calls = {
            n.func.id for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        assert "_read_source" in calls, f"{name} must read through _read_source"


def test_headline_excludes_match_lines(harness, store_and_index):
    """`rg -l` is the headline; `rg` with lines is reported but never added in.

    Folding matched lines into the headline would roughly double the baseline
    and inflate our ratio. It is measured so the choice is auditable, and it
    must stay out of `tokens`.
    """
    store, index = store_and_index
    r = harness.measure_grep_baseline(store, "o", "n", index, "router")
    assert r["tokens"] == r["grep_tokens"] + r["read_tokens"]
    assert r["match_lines_tokens"] > 0, "the larger variant must still be measured"
    assert r["match_lines_tokens"] not in (r["tokens"], r["grep_tokens"])


def test_reads_at_most_n_files(harness, store_and_index):
    store, index = store_and_index
    r = harness.measure_grep_baseline(store, "o", "n", index, "router")
    assert r["files_read"] <= harness.GREP_FILES_READ


def test_ranking_is_deterministic_and_match_count_ordered(harness, tmp_path):
    """Ties break on path, not on index insertion order.

    A file set that depends on iteration order makes the baseline drift
    silently between runs — the class of defect v1.108.228 fixed in the ranker.
    """
    files = {f"f{i}.py": "alpha\n" for i in range(6)}   # identical match counts
    store, index = _FakeStore(tmp_path, files), _FakeIndex(files)
    first = harness.measure_grep_baseline(store, "o", "n", index, "alpha")
    # Same corpus, reversed iteration order.
    index_rev = _FakeIndex(reversed(list(files)))
    second = harness.measure_grep_baseline(store, "o", "n", index_rev, "alpha")
    assert first == second, "tie-break must not depend on source_files order"


def test_matching_is_case_insensitive_and_any_term(harness, store_and_index):
    """The permissive reading — it finds MORE for the baseline, not less."""
    store, index = store_and_index
    upper = harness.measure_grep_baseline(store, "o", "n", index, "ROUTER")
    lower = harness.measure_grep_baseline(store, "o", "n", index, "router")
    assert upper["files_matched"] == lower["files_matched"] > 0

    # A multi-term query is an OR, so it cannot match fewer files than one term.
    one = harness.measure_grep_baseline(store, "o", "n", index, "router")
    both = harness.measure_grep_baseline(store, "o", "n", index, "router middleware")
    assert both["files_matched"] >= one["files_matched"]


def test_empty_query_is_an_error_not_a_zero(harness, store_and_index):
    """Zero tokens would divide into an infinite ratio in our favour."""
    store, index = store_and_index
    r = harness.measure_grep_baseline(store, "o", "n", index, "   ")
    assert "error" in r and "tokens" not in r


def test_derived_ratios_are_excluded_from_the_reproducibility_signature(harness):
    """`grep_ratio` divides into `jmunch_tokens`, so it inherits its jitter.

    The grep baseline's own counts carry no wall-clock field and must stay
    INSIDE the signature — if grep-then-read is not bit-reproducible that is a
    real defect and the gate has to say so.
    """
    excluded = harness._WALLCLOCK_DERIVED_FIELDS
    assert "grep_ratio" in excluded
    assert "grep_reduction_pct" in excluded
    for stable in (
        "grep_baseline_tokens", "grep_grep_tokens", "grep_read_tokens",
        "grep_files_matched", "grep_files_read", "grep_match_lines_tokens",
    ):
        assert stable not in excluded, (
            f"{stable} has no wall-clock input and must be compared across runs"
        )


def test_report_names_both_baselines(harness):
    """Two baselines in one report must be labelled, or they read as a conflict."""
    rendered = harness.render_markdown(
        [{
            "repo": "o/n", "display": "n", "file_count": 3, "symbol_count": 9,
            "baseline_tokens": 1000,
            "corpus": {"pin": "verified", "complete": True, "files_accepted": 3,
                       "git_head": "a" * 40, "pinned_sha": "a" * 40},
            "tasks": [{
                "query": "router", "baseline_tokens": 1000, "jmunch_tokens": 10,
                "reduction_pct": 99.0, "ratio": 100.0,
                "grep_baseline_tokens": 100, "grep_grep_tokens": 10,
                "grep_read_tokens": 90, "grep_files_matched": 2,
                "grep_files_read": 2, "grep_match_lines_tokens": 40,
                "grep_ratio": 10.0, "grep_reduction_pct": 90.0,
                "search_tokens": 4, "fetch_tokens": 6, "hits_fetched": 3,
                "search_ms": 1.0, "stable_tokens": 10,
                "stable_search_tokens": 4, "stable_fetch_tokens": 6,
            }],
        }],
        harness.TOKENIZER,
    )
    assert "read-all" in rendered
    assert f"grep-top-{harness.GREP_FILES_READ}" in rendered
    # The weaker-for-us number must be the one flagged as quotable.
    assert "Baseline B is the number to quote" in rendered
