"""Retrieval inflation: what one information need actually cost in calls.

arXiv:2608.13571 defines token inflation as true workflow cost over single-call
cost. ``_meta.tokens_saved`` has only ever reported the saving on the call that
worked; this is the first number that charges us for the calls before it.

⚠ The basis is CALLS. ``ranking_events`` has no token column, and these tests pin
that the field says so -- a ratio named after tokens while counting calls is the
defect, not a rounding of it.
"""
from __future__ import annotations

import sqlite3

import pytest

from jcodemunch_mcp.retrieval.regret import (
    INFLATION_MIN_NEEDS,
    _detect_inflation,
    analyze_regret,
)
from jcodemunch_mcp.storage import token_tracker as tt


def _row(session, qhash, tool="search_symbols", query="find the thing", ts=0.0, stale=0):
    return (session, qhash, tool, query, ts, stale)


def _needs(n, session="s1"):
    """``n`` distinct information needs, one call each -- a clean ledger."""
    return [_row(session, f"q{i}", ts=float(i)) for i in range(n)]


# --------------------------------------------------------------------------- #
# Could-not-ask is not zero
# --------------------------------------------------------------------------- #

def test_none_rows_are_unmeasurable_not_uninflated():
    """⚠⚠ The whole asymmetry. A ledger that cannot answer must not answer 1.0x.

    Same rule as ``_paths_changed_between`` returning None and
    ``freshness.classify`` refusing ``fresh`` for a comparison it could not make.
    """
    out = _detect_inflation(None)
    assert out["measurable"] is False
    assert out["reason"] == "ledger_has_no_session_column"
    assert "ratio" not in out, "an unmeasurable ledger must not carry a ratio"


def test_the_basis_is_named_calls_in_every_shape():
    """Measurable or not, the reader is told what was counted."""
    for rows in (None, [], _needs(2), _needs(INFLATION_MIN_NEEDS)):
        assert _detect_inflation(rows)["basis"] == "calls"


def test_too_few_needs_refuses_rather_than_reporting_noise():
    out = _detect_inflation(_needs(INFLATION_MIN_NEEDS - 1))
    assert out["measurable"] is False
    assert out["reason"] == "too_few_needs"
    assert out["needs"] == INFLATION_MIN_NEEDS - 1
    assert "ratio" not in out


# --------------------------------------------------------------------------- #
# The ratio
# --------------------------------------------------------------------------- #

def test_a_clean_ledger_is_exactly_one():
    out = _detect_inflation(_needs(INFLATION_MIN_NEEDS))
    assert out["measurable"] is True
    assert out["ratio"] == 1.0
    assert out["excess_calls"] == 0
    assert out["worst"] == [], "nothing was re-asked, so nothing is worst"


def test_repeats_within_one_session_are_charged():
    rows = _needs(4) + [
        _row("s1", "hot", query="where is the parser", ts=10.0 + i) for i in range(4)
    ]
    out = _detect_inflation(rows)
    assert out["needs"] == 5          # q0..q3 plus `hot`
    assert out["calls"] == 8
    assert out["ratio"] == 1.6
    assert out["excess_calls"] == 3
    assert out["worst"][0]["calls"] == 4
    assert out["worst"][0]["excess_calls"] == 3
    assert out["worst"][0]["query"] == "where is the parser"


def test_the_same_query_in_two_sessions_is_two_needs_not_one_re_ask():
    """⚠ A need is (session, query_hash). Keying on query_hash alone would charge
    us for the agent having a second conversation a week later."""
    rows = _needs(4) + [
        _row("s1", "same", ts=1.0),
        _row("s2", "same", ts=2.0),
    ]
    out = _detect_inflation(rows)
    assert out["needs"] == 6
    assert out["ratio"] == 1.0
    assert out["excess_calls"] == 0


# --------------------------------------------------------------------------- #
# Unknown session
# --------------------------------------------------------------------------- #

def test_rows_without_a_session_are_excluded_and_disclosed():
    rows = _needs(INFLATION_MIN_NEEDS) + [_row(None, "orphan", ts=99.0)]
    out = _detect_inflation(rows)
    assert out["events_without_session"] == 1
    assert out["needs"] == INFLATION_MIN_NEEDS
    assert out["ratio"] == 1.0


def test_null_sessions_do_not_fuse_into_one_enormous_need():
    """⚠⚠ The failure this exists to prevent. #456 added ``session_uid`` by
    ALTER, so every pre-#456 row carries NULL. Folding NULL into a synthetic
    session would collapse the entire historical ledger into one need and report
    a spectacular fake ratio."""
    rows = _needs(INFLATION_MIN_NEEDS) + [
        _row(None, "q0", ts=float(i)) for i in range(40)
    ]
    out = _detect_inflation(rows)
    assert out["events_without_session"] == 40
    assert out["ratio"] == 1.0, "NULL-session rows inflated the ratio"


# --------------------------------------------------------------------------- #
# The disclosed over-count
# --------------------------------------------------------------------------- #

def test_a_repeat_after_the_index_moved_is_counted_and_not_subtracted():
    """⚠⚠ Subtracting it would lower our own inflation number. A self-flattering
    adjustment applied silently is the one direction this metric must not drift,
    so it is reported beside the ratio and left in it."""
    rows = _needs(4) + [
        _row("s1", "moved", ts=1.0, stale=0),
        _row("s1", "moved", ts=2.0, stale=1),
    ]
    out = _detect_inflation(rows)
    assert out["repeats_after_index_change"] == 1
    assert out["excess_calls"] == 1, "the repeat was quietly forgiven"
    assert out["ratio"] > 1.0


def test_a_repeat_with_no_index_change_is_not_flagged():
    rows = _needs(4) + [_row("s1", "steady", ts=float(i), stale=0) for i in range(2)]
    assert _detect_inflation(rows)["repeats_after_index_change"] == 0


# --------------------------------------------------------------------------- #
# The ledger reader
# --------------------------------------------------------------------------- #

_BASE_COLUMNS = (
    "ts REAL NOT NULL, repo TEXT, tool TEXT NOT NULL, query_hash TEXT NOT NULL, "
    "query TEXT NOT NULL, returned_ids TEXT NOT NULL, top1_score REAL, "
    "top2_score REAL, confidence REAL, semantic_used INTEGER NOT NULL, "
    "identity_hit INTEGER NOT NULL, repo_is_stale INTEGER NOT NULL"
)
_BASE_ROW = (1.0, "o/n", "search_symbols", "qh", "q", "[]", 0.5, 0.4, 0.6, 0, 1, 0)


def _make_db(path, *, with_session: bool):
    columns = _BASE_COLUMNS + (", session_uid TEXT" if with_session else "")
    values = _BASE_ROW + (("sess",) if with_session else ())
    placeholders = ", ".join("?" * len(values))
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(f"CREATE TABLE ranking_events ({columns})")
        conn.execute(f"INSERT INTO ranking_events VALUES ({placeholders})", values)
        conn.commit()
    finally:
        conn.close()


def test_a_pre_456_ledger_returns_none_not_empty(tmp_path):
    """⚠⚠ ``[]`` would read as "measured, no inflation". The column is absent."""
    _make_db(tmp_path / "telemetry.db", with_session=False)
    assert tt.ranking_db_inflation_rows(base_path=str(tmp_path)) is None


def test_a_current_ledger_returns_its_rows(tmp_path):
    """The control. Without it, the None above is satisfied by a function that
    always returns None."""
    _make_db(tmp_path / "telemetry.db", with_session=True)
    rows = tt.ranking_db_inflation_rows(base_path=str(tmp_path))
    assert rows is not None and len(rows) == 1
    assert rows[0][0] == "sess" and rows[0][1] == "qh"


def test_a_missing_database_is_unknown_too(tmp_path):
    assert tt.ranking_db_inflation_rows(base_path=str(tmp_path / "nope")) is None


def test_the_reader_does_not_widen_the_shared_ranking_tuple(tmp_path):
    """⚠⚠ Why this is a second query. ``ranking_db_query``'s 12-tuple is read
    POSITIONALLY by regret, tuning, ledger_trust and analyze_perf, and it opens
    the db directly rather than through ``_ensure_perf_db`` -- so selecting a
    column that may not exist would raise, hit its catch-all, and return ``[]``
    for every ledger consumer. One missing column, all six signals dark."""
    _make_db(tmp_path / "telemetry.db", with_session=False)
    rows = tt.ranking_db_query(base_path=str(tmp_path))
    assert len(rows) == 1 and len(rows[0]) == 12


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #

def test_analyze_regret_carries_inflation_even_with_no_events(tmp_path):
    """An absent key reads as zero inflation to any caller that uses ``.get``."""
    out = analyze_regret("o/n", storage_path=str(tmp_path))
    assert out["events_analyzed"] == 0
    assert out["inflation"]["measurable"] is False
    assert out["inflation"]["reason"] == "no_events"


@pytest.mark.parametrize("field", ["basis", "measurable"])
def test_every_inflation_shape_carries_the_shape_fields(field):
    for rows in (None, [], _needs(2), _needs(INFLATION_MIN_NEEDS)):
        assert field in _detect_inflation(rows)
