"""Tests for the retrieval-regret loop (regret.py + suggest_corrections).

Seeds the ranking_events ledger directly (mirrors test_weight_tuning::_seed),
then asserts: each regret signal is extracted; the no-telemetry path is honest
(no fabricated corrections); synthesis produces explainable corrections; and
the charter holds — suggest_corrections writes no user file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jcodemunch_mcp.retrieval import regret as _regret
from jcodemunch_mcp.retrieval.regret import analyze_regret
from jcodemunch_mcp.storage import token_tracker as tt
from jcodemunch_mcp.tools.suggest_corrections import suggest_corrections


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch, tmp_path):
    fresh = tt._State()
    fresh._base_path = str(tmp_path)
    monkeypatch.setattr(tt, "_state", fresh)
    yield


def _enable(monkeypatch):
    from jcodemunch_mcp import config as _config
    real_get = _config.get

    def patched_get(key, default=None, *args, **kwargs):
        if key == "perf_telemetry_enabled":
            return True
        return real_get(key, default, *args, **kwargs)

    monkeypatch.setattr(_config, "get", patched_get)


def _ev(repo, query, *, tool="search_symbols", returned=None, top1=None, top2=None,
        conf=None, sem=False, idhit=False, stale=False):
    tt.record_ranking_event(
        tool=tool, repo=repo, query=query, returned_ids=returned or [],
        top1_score=top1, top2_score=top2, confidence=conf,
        semantic_used=sem, identity_hit=idhit, repo_is_stale=stale,
    )


REPO = "local/x"


# --- Extraction (Phase 1) --------------------------------------------------- #

def test_requery_churn_detected(monkeypatch, tmp_path):
    _enable(monkeypatch)
    for _ in range(6):
        _ev(REPO, "where is the auth middleware", returned=["a"], conf=0.5)
    out = analyze_regret(REPO, storage_path=str(tmp_path))
    sigs = {c["signal"] for c in out["clusters"]}
    assert "requery_churn" in sigs
    churn = next(c for c in out["clusters"] if c["signal"] == "requery_churn")
    assert churn["event_count"] == 6
    assert churn["query_examples"] == ["where is the auth middleware"]


def test_thin_and_low_confidence_detected(monkeypatch, tmp_path):
    _enable(monkeypatch)
    for _ in range(3):
        _ev(REPO, "frobnicate widget", tool="search_text", returned=[])  # thin (empty)
    for _ in range(3):
        _ev(REPO, "parse config blob", returned=["a"], conf=0.1)        # low confidence
    out = analyze_regret(REPO, storage_path=str(tmp_path))
    sigs = {c["signal"] for c in out["clusters"]}
    assert "thin_result" in sigs
    assert "low_confidence" in sigs


def test_stale_at_query_detected(monkeypatch, tmp_path):
    _enable(monkeypatch)
    for _ in range(8):
        _ev(REPO, f"q{_}", returned=["a"], conf=0.6, stale=True)
    out = analyze_regret(REPO, storage_path=str(tmp_path))
    stale = [c for c in out["clusters"] if c["signal"] == "stale_at_query"]
    assert stale and stale[0]["evidence"]["stale_rate"] == 1.0


def test_vocabulary_gap_detected(monkeypatch, tmp_path):
    _enable(monkeypatch)
    for _ in range(4):
        _ev(REPO, "tokenizer", returned=["a"], conf=0.6, sem=True, idhit=False)
    out = analyze_regret(REPO, storage_path=str(tmp_path))
    assert any(c["signal"] == "vocabulary_gap" for c in out["clusters"])


def test_ambiguous_top_detected(monkeypatch, tmp_path):
    _enable(monkeypatch)
    for _ in range(3):
        _ev(REPO, "handler", returned=["a", "b"], top1=0.5, top2=0.49, conf=0.5)
    out = analyze_regret(REPO, storage_path=str(tmp_path))
    assert any(c["signal"] == "ambiguous_top" for c in out["clusters"])


def test_severity_ranking_high_first(monkeypatch, tmp_path):
    _enable(monkeypatch)
    for _ in range(10):  # high-severity churn
        _ev(REPO, "big churn query", returned=["a"], conf=0.5)
    for _ in range(2):   # low-severity ambiguous
        _ev(REPO, "minor", returned=["a", "b"], top1=0.5, top2=0.49, conf=0.5)
    out = analyze_regret(REPO, storage_path=str(tmp_path))
    assert out["clusters"][0]["severity"] == "high"


# --- Honest no-telemetry path ----------------------------------------------- #

def test_no_events_returns_honest_hint(monkeypatch, tmp_path):
    _enable(monkeypatch)
    out = analyze_regret(REPO, storage_path=str(tmp_path))
    assert out["events_analyzed"] == 0
    assert out["clusters"] == []
    assert "hint" in out and out["hint"]


def test_telemetry_off_flagged(tmp_path):
    # Telemetry not enabled => record is a no-op => no events, telemetry_present False.
    out = analyze_regret(REPO, storage_path=str(tmp_path))
    assert out["telemetry_present"] is False
    assert out["clusters"] == []


# --- Synthesis (Phase 2) ---------------------------------------------------- #

def test_suggest_corrections_routing_from_text_scan(monkeypatch, tmp_path):
    _enable(monkeypatch)
    # Thin results recurring on search_text => routing correction toward search_symbols.
    for _ in range(4):
        _ev(REPO, "find the retry policy", tool="search_text", returned=[])
    project = tmp_path / "proj"
    project.mkdir()
    (project / "CLAUDE.md").write_text("# Project\n\nExisting policy.\n", encoding="utf-8")
    out = suggest_corrections(
        repo=REPO, project_path=str(project), storage_path=str(tmp_path))
    assert out["telemetry_present"] is True
    kinds = {c["kind"] for c in out["corrections"]}
    assert "routing" in kinds
    routing = next(c for c in out["corrections"] if c["kind"] == "routing")
    assert "search_symbols" in routing["recommended_action"]
    # A unified-diff preview was rendered against CLAUDE.md.
    assert routing["suggested_patch"] and "+++ b/CLAUDE.md" in routing["suggested_patch"]


def test_charter_writes_no_user_file(monkeypatch, tmp_path):
    _enable(monkeypatch)
    for _ in range(4):
        _ev(REPO, "find the retry policy", tool="search_text", returned=[])
    project = tmp_path / "proj"
    project.mkdir()
    claude = project / "CLAUDE.md"
    original = "# Project\n\nExisting policy.\n"
    claude.write_text(original, encoding="utf-8")
    suggest_corrections(repo=REPO, project_path=str(project), storage_path=str(tmp_path))
    # The user's CLAUDE.md is untouched — suggestions only.
    assert claude.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("service_active,expected", [
    (False, "watch-install"),
    (True, "get_watch_status"),
])
def test_freshness_correction_no_patch(monkeypatch, tmp_path, service_active, expected):
    """⚠⚠ The advice has TWO branches and this test used to assert one of them
    while reading the DEVELOPER'S REAL MACHINE for which. It passed only while
    nobody running it had the watch service installed; installing it flipped
    `service_active` to True and the assertion failed with the code correct.
    Same #437 shape as the config-isolation guard -- a test whose verdict is
    decided by ambient state it never declares.

    ⚠ `_freshness_correction` imports `get_watch_status` INSIDE the function,
    so the patch target is the source module, not `suggest_corrections`.
    Parametrised over both branches, which is strictly more coverage than the
    original: whichever branch the dev box was not in had never run."""
    _enable(monkeypatch)
    monkeypatch.setattr(
        "jcodemunch_mcp.tools.get_watch_status.get_watch_status",
        lambda **kw: {"service": {"active": service_active}},
    )
    for _ in range(8):
        _ev(REPO, f"q{_}", returned=["a"], conf=0.6, stale=True)
    out = suggest_corrections(repo=REPO, storage_path=str(tmp_path))
    fresh = [c for c in out["corrections"] if c["kind"] == "index_freshness"]
    assert fresh and fresh[0]["suggested_patch"] is None
    assert expected in fresh[0]["recommended_action"]


def test_convergent_signals_dedupe(monkeypatch, tmp_path):
    """thin_result + requery_churn on the same search_text query both steer
    search_text -> search_symbols; the loop must emit ONE routing correction,
    not a duplicate, and merge the evidence."""
    _enable(monkeypatch)
    # 6 empty search_text results on one query => both thin_result (empty) AND
    # requery_churn (>=5 repeats) fire for the same redirect.
    for _ in range(6):
        _ev(REPO, "where is rate limiting", tool="search_text", returned=[])
    out = suggest_corrections(repo=REPO, storage_path=str(tmp_path))
    routing = [c for c in out["corrections"] if c["kind"] == "routing"]
    actions = [c["recommended_action"] for c in routing]
    assert len(actions) == len(set(actions)), f"duplicate routing corrections: {actions}"
    assert len(routing) == 1


def test_no_repo_path_is_honest(tmp_path):
    out = suggest_corrections(storage_path=str(tmp_path))
    assert out["telemetry_present"] is False
    assert out["corrections"] == []
    assert "read-only" in out["_meta"]["charter"]
