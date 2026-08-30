"""analyze_perf: honest baseline deltas, and where the time actually went.

Two defects, one release:

⚠⚠ A delta was computed as ``current - b.get(key, 0.0)``, so a baseline that
never recorded latency produced ``p95_delta_ms`` equal to the CURRENT p95 --
published under a name asserting a comparison happened. The only baseline that
ships carries ``tokens_saved`` and nothing else, so this was the live path.

⚠⚠ Only ``slowest_by_p95`` existed, which ranks how slow ONE call is. Nothing
reported the wall-clock a tool consumed, and the two orderings disagree whenever
a fast tool is called often -- the ordinary case.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jcodemunch_mcp.storage.token_tracker import latency_bucket
from jcodemunch_mcp.tools.analyze_perf import _diff_baseline, _rank_by_total

BASELINE_DIR = Path(__file__).resolve().parents[1] / "benchmarks" / "token_baselines"

_LATENCY_KEYS = {"p50_delta_ms": "p50_ms", "p95_delta_ms": "p95_ms"}


# --------------------------------------------------------------------------- #
# A delta against an absent measurement
# --------------------------------------------------------------------------- #

def test_no_shipped_baseline_produces_a_delta_against_an_absent_measurement():
    """⚠ Read off disk, never from a fixture. A synthetic baseline authored
    beside the schema carries every key the schema mentions, which is exactly
    how this survived: the existing test's baseline had p50_ms/p95_ms/calls that
    the real artifact has for no tool at all.
    """
    files = sorted(BASELINE_DIR.glob("v*.json"))
    assert files, "no baselines on disk -- this test is asserting nothing"

    current = {"search_symbols": {"count": 40, "p50_ms": 120.0, "p95_ms": 900.0}}
    for path in files:
        baseline = json.loads(path.read_text(encoding="utf-8"))
        diff = _diff_baseline(baseline, current, {})
        for tool, entry in diff.items():
            recorded = baseline.get("tools", {}).get(tool, {})
            for out_key, base_key in _LATENCY_KEYS.items():
                if base_key not in recorded:
                    assert entry[out_key] is None, (
                        f"{path.name}:{tool} differenced {out_key} against a "
                        f"{base_key} it never recorded"
                    )
                    assert entry["not_comparable"][base_key].startswith("absent")


def test_a_tokens_only_baseline_entry_refuses_the_latency_delta():
    """The shape of the shipped artifact, pinned. ⚠⚠ Under the old default the
    assertion below read 900.0 -- the current value, wearing the word delta."""
    baseline = {"tools": {"search_symbols": {"tokens_saved": 5000}}}
    current = {"search_symbols": {"count": 40, "p50_ms": 120.0, "p95_ms": 900.0}}

    entry = _diff_baseline(baseline, current, {"search_symbols": 6000})["search_symbols"]
    assert entry["p95_delta_ms"] is None, "the current p95 was published as a delta"
    assert entry["p50_delta_ms"] is None
    assert entry["calls_delta"] is None
    assert entry["not_comparable"] == {
        "p50_ms": "absent_in_baseline",
        "p95_ms": "absent_in_baseline",
        "calls": "absent_in_baseline",
    }
    assert entry["tokens_saved_delta"] == 1000, "the field the baseline HAS still differences"


def test_a_fully_populated_baseline_still_differences():
    """The control. Without it, every assertion above is satisfied by a function
    that returns None for everything."""
    baseline = {"tools": {"search_symbols": {
        "tokens_saved": 5000, "calls": 10, "p50_ms": 100.0, "p95_ms": 800.0,
    }}}
    current = {"search_symbols": {"count": 40, "p50_ms": 120.0, "p95_ms": 900.0}}

    entry = _diff_baseline(baseline, current, {"search_symbols": 6000})["search_symbols"]
    assert entry["p50_delta_ms"] == 20.0
    assert entry["p95_delta_ms"] == 100.0
    assert entry["calls_delta"] == 30
    assert entry["tokens_saved_delta"] == 1000
    assert "not_comparable" not in entry, "nothing was missing; nothing to disclose"


def test_absent_in_current_reads_differently_from_absent_in_baseline():
    """⚠ Which side could not answer is the whole diagnostic. Collapsing both to
    a bare null tells the reader a comparison failed and not why."""
    baseline = {"tools": {"gone": {"tokens_saved": 10, "calls": 5,
                                   "p50_ms": 1.0, "p95_ms": 2.0}}}
    entry = _diff_baseline(baseline, {}, {})["gone"]
    assert entry["not_comparable"] == {"p50_ms": "absent_in_current",
                                       "p95_ms": "absent_in_current"}


def test_calls_and_tokens_keep_their_meaningful_zero():
    """⚠ A tool nobody called really did save nothing and really was called zero
    times -- those deltas stay computable. It has no p50, and inventing one is
    the same defect from the other end."""
    baseline = {"tools": {"gone": {"tokens_saved": 10, "calls": 5,
                                   "p50_ms": 1.0, "p95_ms": 2.0}}}
    entry = _diff_baseline(baseline, {}, {})["gone"]
    assert entry["calls_delta"] == -5
    assert entry["tokens_saved_delta"] == -10
    assert entry["p50_delta_ms"] is None


def test_a_tool_absent_from_the_baseline_says_so():
    entry = _diff_baseline({"tools": {}}, {"new": {"count": 2, "p50_ms": 1.0,
                                                  "p95_ms": 2.0}}, {})["new"]
    assert entry["in_baseline"] is False
    assert entry["p95_delta_ms"] is None


# --------------------------------------------------------------------------- #
# Where the time went
# --------------------------------------------------------------------------- #

def _stats():
    return {
        # fast, called constantly -- an hour of wall clock
        "get_file_outline": latency_bucket(sorted([900.0] * 4000), 0),
        # slow per call, called three times -- 36 seconds
        "index_folder": latency_bucket(sorted([12000.0] * 3), 0),
    }


def test_the_two_rankings_disagree_when_a_fast_tool_is_called_often():
    """⚠⚠ The property. slowest_by_p95 puts the three-call tool first; the
    four-thousand-call tool consumed 100x the wall clock. Both orderings are
    correct answers to different questions, and only one of them was published.
    """
    stats = _stats()
    by_p95 = [n for n, _ in sorted(stats.items(),
                                   key=lambda kv: kv[1]["p95_ms"], reverse=True)]
    rows, meta = _rank_by_total(stats, top=20)

    assert by_p95[0] == "index_folder"
    assert rows[0]["tool"] == "get_file_outline"
    assert rows[0]["share"] > 0.98
    assert meta["measurable"] is True
    assert meta["total_ms"] == 3_636_000.0


def test_the_share_is_over_the_grand_total():
    rows, meta = _rank_by_total(_stats(), top=20)
    assert sum(r["share"] for r in rows) == pytest.approx(1.0, abs=0.002)
    assert sum(r["total_ms"] for r in rows) == meta["total_ms"]


def test_a_zero_total_refuses_rather_than_dividing():
    """⚠⚠ Same rule as the inflation concentration: a share of nothing is
    undefined, not even."""
    for stats in ({}, {"t": latency_bucket([0.0, 0.0], 0)}):
        rows, meta = _rank_by_total(stats, top=20)
        assert rows == []
        assert meta["measurable"] is False
        assert meta["reason"] == "no_time_recorded"
        assert "total_ms" not in meta


def test_a_ring_capped_tool_is_named_because_its_share_is_a_lower_bound():
    """⚠⚠ The cap bites hardest on the busiest tool -- the one this ranking
    exists to find -- so an undisclosed cap understates exactly the wrong row."""
    from jcodemunch_mcp.storage.token_tracker import _LATENCY_RING_DEFAULT

    stats = _stats()
    stats["search_symbols"] = latency_bucket(
        sorted([5.0] * _LATENCY_RING_DEFAULT), 0, ring_capped=True
    )
    rows, meta = _rank_by_total(stats, top=20)
    assert meta["ring_capped_tools"] == ["search_symbols"]
    assert "lower bound" in meta["note"]
    assert any(r.get("count_is_ring_capped") for r in rows)
    assert not any(r.get("count_is_ring_capped") for r in rows
                   if r["tool"] != "search_symbols")


def test_a_bucket_with_no_total_is_excluded_and_counted():
    """A foreign producer's shape must not be silently ranked as zero."""
    stats = dict(_stats(), legacy={"count": 5, "p95_ms": 10.0})
    rows, meta = _rank_by_total(stats, top=20)
    assert meta["tools_without_total_ms"] == 1
    assert "legacy" not in [r["tool"] for r in rows]


# --------------------------------------------------------------------------- #
# One producer for the bucket
# --------------------------------------------------------------------------- #

def test_p95_is_max_is_measured_not_derived_from_the_sample_count():
    """⚠ The flag compares the computed values, so it stays correct if the
    percentile ever changes. At the time of writing it fires for every n <= 20."""
    for n in (1, 2, 10, 20):
        assert latency_bucket([float(i) for i in range(n)], 0).get("p95_is_max") is True
    for n in (21, 40, 512):
        assert "p95_is_max" not in latency_bucket([float(i) for i in range(n)], 0)


def test_analyze_perf_holds_no_percentile_of_its_own():
    """⚠⚠ It held the SECOND copy of the latency shape and the two agreed digit
    for digit, which is what makes a later divergence invisible. The local
    helper is deleted rather than kept as a wrapper -- an unused copy is what
    regrows."""
    from jcodemunch_mcp.tools import analyze_perf as ap

    assert not [n for n in vars(ap) if "percentile" in n.lower()]
    source = Path(ap.__file__).read_text(encoding="utf-8")
    assert "latency_bucket" in source, "the authority is not being called"


def test_the_totals_reach_the_response(monkeypatch, tmp_path):
    """The end-to-end half: a block computed and not emitted is the same defect
    as not computing it."""
    from jcodemunch_mcp.storage import token_tracker as tt
    from jcodemunch_mcp.tools import analyze_perf as ap

    fresh = tt._State()
    fresh._base_path = str(tmp_path)
    monkeypatch.setattr(tt, "_state", fresh)
    for ms in (10.0, 20.0, 30.0):
        tt.record_tool_latency("search_symbols", ms, ok=True)
    tt.record_tool_latency("index_folder", 900.0, ok=True)

    out = ap.analyze_perf(window="session", storage_path=str(tmp_path))
    assert out["totals"]["measurable"] is True
    assert out["totals"]["total_ms"] == 960.0
    assert out["heaviest_by_total_ms"][0]["tool"] == "index_folder"
    assert out["slowest_by_p95"][0]["tool"] == "index_folder"
    assert out["heaviest_by_total_ms"][0]["share"] == 0.938
