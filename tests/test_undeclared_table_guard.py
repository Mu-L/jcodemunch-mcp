"""#555: fail closed when a producer emits a table under a key no schema declares.

Split out of #553. The column guard (#354) raises when a table has ROWS but no
declared COLUMN was populated. It is structurally blind to a disagreement about
the KEY: `response.get(t.key, [])` returns `[]`, `out_rows` stays empty, and the
check never runs. `search_ast` declared `results` while the tool returned
`matches`, and served an empty table for every language and preset.

⚠ A green suite is weak evidence for a guard. The acceptance test here is
`test_the_553_shape_now_raises`: it rebuilds the ACTUAL pre-fix schema and
asserts the guard fires on it.

Proposed by @RascoApps in #553.
"""

from __future__ import annotations

import pytest

from jcodemunch_mcp.encoding import schema_driven as sd
from jcodemunch_mcp.encoding.schemas import search_text as st

_ROWS = [{"file": "a.py", "line": 1}, {"file": "b.py", "line": 2}]


def test_undeclared_table_raises():
    """The property: rows the schema cannot see must not pass silently."""
    with pytest.raises(ValueError, match="no TableSpec declares"):
        sd.encode("t", {"matches": _ROWS}, "x1",
                  [sd.TableSpec(key="results", tag="a", cols=["file", "line"])])


def test_the_553_shape_now_raises():
    """Acceptance: the exact pre-fix search_ast schema against a real response.

    Before this guard, encoding produced a header and an empty table and raised
    nothing. The dispatcher shipped it, and every match was lost on the wire.
    """
    pre_fix = [sd.TableSpec(
        key="results", tag="a",
        cols=["file", "line", "match_type", "snippet", "symbol_id", "symbol_name"],
    )]
    response = {
        "repo": "a/b",
        "total_matches": 2,
        "matches": [
            {"file": "a.py", "line": 10, "pattern": "todo_fixme",
             "severity": "info", "snippet": "# TODO", "marker": "TODO"},
            {"file": "b.py", "line": 4, "pattern": "nested_loops",
             "severity": "warning", "snippet": "for i", "loop_depth": 3},
        ],
    }
    with pytest.raises(ValueError, match="returned 2 row"):
        sd.encode("search_ast", response, "sa1", pre_fix,
                  ("result_count", "query", "repo"))


def test_declared_table_is_fine():
    payload, _ = sd.encode("t", {"results": _ROWS}, "x1",
                           [sd.TableSpec(key="results", tag="a", cols=["file", "line"])])
    assert payload


def test_list_of_scalars_is_not_a_table():
    """`languages_scanned: ["python"]` is a scalar list, not a missing table."""
    payload, _ = sd.encode("t", {"languages_scanned": ["python", "racket"]}, "x1", [])
    assert payload


def test_empty_list_is_not_a_table():
    payload, _ = sd.encode("t", {"matches": []}, "x1", [])
    assert payload


def test_json_blob_key_is_not_undeclared():
    """A key carried as a JSON blob IS carried, so it must not trip the guard."""
    payload, _ = sd.encode("t", {"extras": _ROWS}, "x1", [], (),
                           json_blobs=("extras",))
    assert payload


def test_allow_undeclared_is_an_explicit_per_key_opt_out():
    payload, _ = sd.encode("t", {"debug_rows": _ROWS}, "x1", [],
                           allow_undeclared=("debug_rows",))
    assert payload


def test_pre_flattened_schema_needs_no_exemption():
    """The placement argument, tested rather than asserted.

    ⚠ search_text's public key is `results`; its table key is the private
    `__rows__`. `_flatten()` removes `results` BEFORE `sd.encode` sees the
    dict, so the guard needs no allowlist entry for it. If the check ever moves
    to the raw response, this fails -- which is the point.
    """
    response = {
        "result_count": 1, "query": "x", "repo": "a/b",
        "results": [{"file": "a.py", "matches": [{"line": 1, "text": "x"}]}],
        "_meta": {"timing_ms": 1.0},
    }
    assert "results" not in st._flatten(response)
    payload, _ = st.encode("search_text", response)
    assert st.decode(payload)["results"][0]["file"] == "a.py"


def test_meta_is_never_a_table():
    payload, _ = sd.encode("t", {"_meta": {"rows": _ROWS}}, "x1", [])
    assert payload
