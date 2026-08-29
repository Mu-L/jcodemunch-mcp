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


# --------------------------------------------------------------------------- #
# Concentration -- what the mean cannot see
# --------------------------------------------------------------------------- #

def _distributed(spec, session="s1"):
    """One ledger from ``spec``: a list of call-counts, one per need."""
    rows = []
    for i, calls in enumerate(spec):
        rows += [_row(session, f"q{i}", query=f"query {i}", ts=float(i) + n / 100)
                 for n in range(calls)]
    return rows


_CONCENTRATED = [5] + [1] * 9   # 14 calls, 10 needs, all 4 excess in one query
_DIFFUSE = [2] * 4 + [1] * 6    # 14 calls, 10 needs, the excess spread over four


def test_the_same_ratio_can_be_one_runaway_query_or_four_ordinary_ones():
    """⚠⚠ The property the mean cannot express, and the reason this field exists.

    Both ledgers report 1.4x. One of them is a single query re-asked five times;
    the other is four queries asked twice. The action differs completely and the
    ratio is identical -- which is the Revenium distribution in miniature (top 1%
    of runs, 46% of spend).

    ⚠ If ``ratio`` is ever the only number a surface quotes, this test is the
    record that it was known to be insufficient.
    """
    hot = _detect_inflation(_distributed(_CONCENTRATED))
    even = _detect_inflation(_distributed(_DIFFUSE))

    assert hot["ratio"] == even["ratio"] == 1.4
    assert hot["excess_calls"] == even["excess_calls"] == 4

    assert hot["concentration"]["top_need_share"] == 1.0
    assert even["concentration"]["top_need_share"] == 0.25
    assert hot["concentration"]["needs_with_excess"] == 1
    assert even["concentration"]["needs_with_excess"] == 4


def test_the_share_is_over_excess_calls_not_over_calls():
    """⚠ Every need costs one call by definition, so a share over CALLS is
    diluted by the floor: the runaway query above would read 0.357 instead of
    1.0 and the tail would look ordinary again."""
    conc = _detect_inflation(_distributed(_CONCENTRATED))["concentration"]
    assert conc["basis"] == "excess_calls"
    assert conc["top_need_share"] == 1.0, "the share was computed over calls"


def test_a_clean_ledger_refuses_a_share_rather_than_reporting_zero():
    """⚠⚠ ``0.0`` would read as "the waste is spread evenly" -- the strongest
    available claim assembled from there being no waste at all. Same rule as a
    refusal never becoming ``dead_code_pct: 0.0``."""
    conc = _detect_inflation(_needs(INFLATION_MIN_NEEDS))["concentration"]
    assert conc["measurable"] is False
    assert conc["reason"] == "no_excess_calls"
    assert "top_need_share" not in conc
    assert "head_share" not in conc


def test_the_head_discloses_how_many_needs_it_covers():
    """⚠ A tenth ROUNDED UP: at the five-need floor the head is one need of
    five, not one of ten. A share quoted without the count it covers is
    unreadable, so both are emitted."""
    small = _detect_inflation(_distributed([3] + [1] * 4))["concentration"]
    assert small["head_needs"] == 1
    assert small["head_share"] == 1.0

    big = _detect_inflation(_distributed([2] * 5 + [1] * 25))["concentration"]
    assert big["head_needs"] == 3, "30 needs -> a head of three"
    assert big["needs_with_excess"] == 5
    assert big["head_share"] == 0.6, "three of the five re-asked needs"


def test_concentration_is_absent_from_every_unmeasurable_shape():
    """The refusals stay refusals -- a shape with no ratio has no tail either."""
    for rows in (None, _needs(INFLATION_MIN_NEEDS - 1)):
        assert "concentration" not in _detect_inflation(rows)


# --------------------------------------------------------------------------- #
# The digest line -- the surface that quotes the mean
# --------------------------------------------------------------------------- #
#
# ⚠ The inflation half of every fixture below comes from `_detect_inflation`
# itself, never from a hand-written dict. A stand-in producer can supply a key
# the real one never emits, which makes an absent-key defect invisible to the
# test written about that exact path.

def _regret_out(rows):
    return {
        "clusters": [{"signal": "requery_churn", "severity": "high"}],
        "events_analyzed": len(rows),
        "inflation": _detect_inflation(rows),
    }


def _digest_line(monkeypatch, rows):
    from jcodemunch_mcp.retrieval import regret as regret_mod
    from jcodemunch_mcp.tools import digest as digest_mod

    monkeypatch.setattr(regret_mod, "analyze_regret",
                        lambda repo, **kw: _regret_out(rows))
    summary = digest_mod._compose_regret("o/n", None)
    text = digest_mod._render_markdown(
        {"repo": "o/n", "n_symbols": 1, "n_files": 1, "regret": summary}
    )
    return summary, text


def test_the_digest_distinguishes_two_ledgers_the_ratio_cannot(monkeypatch):
    """⚠⚠ This line is where the mean reached a human. Both briefings say 1.4x;
    only one of them sends the reader to a single query."""
    hot_summary, hot = _digest_line(monkeypatch, _distributed(_CONCENTRATED))
    even_summary, even = _digest_line(monkeypatch, _distributed(_DIFFUSE))

    assert hot_summary["top_need_share"] == 1.0
    assert even_summary["top_need_share"] == 0.25
    assert "1.4x" in hot and "1.4x" in even
    assert "100% of it in one query" in hot
    assert "25% of it in one query" in even
    assert hot != even, "the two briefings read identically"


def test_the_line_still_renders_without_a_share(monkeypatch):
    """A summary carrying no share must not take the digest down -- the renderer
    reads it with a membership test, not a ``.get`` default that would print a
    fabricated 0%."""
    from jcodemunch_mcp.tools import digest as digest_mod

    text = digest_mod._render_markdown({
        "repo": "o/n", "n_symbols": 1, "n_files": 1,
        "regret": {"count": 1, "events": 9, "top_signal": "requery_churn",
                   "top_severity": "high", "inflation_ratio": 1.4,
                   "excess_calls": 4},
    })
    assert "1.4x" in text and "(4 excess)." in text
    assert "%" not in text.split("Retrieval inflation")[1].split("Run `reflect`")[0]
