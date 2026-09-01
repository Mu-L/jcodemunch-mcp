"""Tests for repos_report (the cockpit view powering `list-repos --json`)."""

from __future__ import annotations

from jcodemunch_mcp.tools.index_folder import index_folder
from jcodemunch_mcp.tools.list_repos import repos_report


def test_repos_report_shape(tmp_path):
    src = tmp_path / "src"
    store = tmp_path / "store"
    src.mkdir()
    store.mkdir()
    (src / "a.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
    r = index_folder(str(src), use_ai_summaries=False, storage_path=str(store))
    assert r["success"] is True

    report = repos_report(storage_path=str(store))
    assert isinstance(report, list) and report
    entry = report[0]
    assert {
        "repo_id", "display_name", "source_root", "file_count", "symbol_count",
        "languages", "indexed_at", "freshness", "watcher_state", "lock_holder",
    } <= entry.keys()
    assert entry["source_root"]  # path is needed by the Console launcher
    assert entry["symbol_count"] >= 1
    assert entry["file_count"] >= 1
    assert isinstance(entry["languages"], dict)
    # ⚠ Read the vocabulary off the mapping instead of restating it: this
    # literal was ("fresh", "edited_uncommitted", "stale_index"), complete
    # only while the field could not say "we did not establish it". #565
    # added `unknown` and `not_tracked`, and a hand-kept list is a second
    # roster that goes stale the next time one is added.
    from jcodemunch_mcp.tools.list_repos import _FRESHNESS_LABEL

    assert entry["freshness"] in set(_FRESHNESS_LABEL.values())
    assert entry["watcher_state"] in ("idle", "watching", "reindexing")
    # Fresh, unwatched index in a throwaway store: no watcher holder.
    assert entry["watcher_state"] == "idle"
    assert entry["lock_holder"] is None
