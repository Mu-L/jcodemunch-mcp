"""v1.108.57 — jcm#334 (reported by @mmashwani).

The `hook-precompact` CLI path is registered for Claude Code / Codex to inject a
jCodeMunch session snapshot before context compaction. But the hook runs as a
SEPARATE process from the MCP server, so it imported `get_session_snapshot()`,
read a fresh process-local SessionJournal, and emitted a healthy-looking but
empty "Files explored: 0 | Searches: 0" snapshot.

Fix (his durable option 1 + the explicit-fallback option 3): the live server
process persists a compact journal snapshot to a small, atomically written file
keyed by the shared CODE_INDEX_PATH (`save_live_journal`, throttled, off via
JCODEMUNCH_LIVE_JOURNAL=0). The PreCompact hook reads it back
(`snapshot_from_live`) and renders it with the same formatter the live tool
uses. When no live journal is readable, the hook emits an explicit "no live
session journal" message rather than a zero-state snapshot.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys


from jcodemunch_mcp.tools.session_journal import SessionJournal
from jcodemunch_mcp.tools.session_state import save_live_journal, load_live_journal
from jcodemunch_mcp.tools.get_session_snapshot import (
    get_session_snapshot,
    snapshot_from_live,
)


def _seeded_journal() -> SessionJournal:
    j = SessionJournal()
    j.record_read("pkg/widget.py", "get_symbol_source")
    j.record_read("pkg/widget.py", "get_file_content")
    j.record_search("widget config", 4)
    j.record_edit("pkg/widget.py")
    return j


# --------------------------------------------------------------------------- #
# live journal persistence round-trip                                         #
# --------------------------------------------------------------------------- #

class TestLiveJournalPersistence:
    def test_save_and_load_roundtrip(self, tmp_path):
        store = str(tmp_path)
        assert save_live_journal(_seeded_journal(), base_path=store) is True
        data = load_live_journal(base_path=store)
        assert data is not None
        assert data["total_unique_files"] == 1
        assert data["total_unique_queries"] == 1
        assert any(f["file"] == "pkg/widget.py" for f in data["files_accessed"])
        assert any(e["file"] == "pkg/widget.py" for e in data["files_edited"])
        assert "pid" in data and "updated_at" in data

    def test_load_missing_returns_none(self, tmp_path):
        assert load_live_journal(base_path=str(tmp_path / "nope")) is None

    def test_load_respects_max_age(self, tmp_path):
        store = str(tmp_path)
        save_live_journal(_seeded_journal(), base_path=store)
        # Any elapsed time exceeds a 0-minute budget → treated as stale.
        assert load_live_journal(base_path=store, max_age_minutes=0) is None
        # A generous budget still loads.
        assert load_live_journal(base_path=store, max_age_minutes=60) is not None

    def test_save_is_best_effort(self):
        # An object that raises in get_context must not propagate.
        class Boom:
            def get_context(self, **kw):
                raise RuntimeError("nope")
        assert save_live_journal(Boom(), base_path=os.devnull) is False


# --------------------------------------------------------------------------- #
# snapshot_from_live rendering                                                 #
# --------------------------------------------------------------------------- #

class TestSnapshotFromLive:
    def test_renders_seeded_journal(self, tmp_path):
        store = str(tmp_path)
        save_live_journal(_seeded_journal(), base_path=store)
        snap = snapshot_from_live(base_path=store)
        assert snap is not None
        assert "## Session Snapshot (jCodemunch)" in snap["snapshot"]
        assert "widget.py" in snap["snapshot"]
        assert snap["_meta"]["source"] == "live_journal"
        assert snap["structured"]["total_files_explored"] == 1

    def test_none_when_no_file(self, tmp_path):
        assert snapshot_from_live(base_path=str(tmp_path / "nope")) is None

    def test_none_when_journal_empty(self, tmp_path):
        store = str(tmp_path)
        save_live_journal(SessionJournal(), base_path=store)  # no activity
        assert snapshot_from_live(base_path=store) is None


# --------------------------------------------------------------------------- #
# in-process tool still works after the renderer refactor                      #
# --------------------------------------------------------------------------- #

class TestInProcessSnapshotRegression:
    def test_get_session_snapshot_shape(self):
        from jcodemunch_mcp.tools.session_journal import get_journal
        get_journal().record_read("regression_marker.py", "get_file_content")
        snap = get_session_snapshot()
        assert "## Session Snapshot (jCodemunch)" in snap["snapshot"]
        assert snap["structured"]["total_files_explored"] >= 1
        assert "timing_ms" in snap["_meta"]


# --------------------------------------------------------------------------- #
# the actual #334 bug: the hook is a separate process                          #
# --------------------------------------------------------------------------- #

class TestSnapshotHooksAcrossProcesses:
    def _run_hook(self, store: str, subcommand: str = "hook-sessionstart",
                  stdin: str = '{"source": "compact"}'):
        env = dict(os.environ)
        env["CODE_INDEX_PATH"] = store
        return subprocess.run(
            [sys.executable, "-m", "jcodemunch_mcp", subcommand],
            input=stdin, text=True, capture_output=True, env=env,
        )

    # The observable moved: PreCompact turned out to have NO exit-0 output
    # channel (Claude Code discards its systemMessage), so the cross-process
    # live-journal read is asserted through SessionStart(compact), the route
    # that actually delivers the snapshot.

    def test_snapshot_reads_live_journal_from_a_fresh_process(self, tmp_path):
        store = str(tmp_path / "idx")
        # Seed + persist in THIS process; the hook runs in a brand-new one.
        assert save_live_journal(_seeded_journal(), base_path=store) is True

        proc = self._run_hook(store)
        assert proc.returncode == 0, proc.stderr
        msg = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
        assert "widget.py" in msg, msg
        assert "Files explored: 0" not in msg, msg

    def test_silent_when_no_journal(self, tmp_path):
        """The no-journal fallback text is not model-steering — stay silent."""
        store = str(tmp_path / "empty_idx")  # nothing persisted here
        proc = self._run_hook(store)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout == ""

    def test_precompact_emits_nothing_cross_process(self, tmp_path):
        """PreCompact's stdout is a discarded channel; the handler no longer
        writes to it even with a populated live journal."""
        store = str(tmp_path / "idx2")
        assert save_live_journal(_seeded_journal(), base_path=store) is True
        proc = self._run_hook(store, subcommand="hook-precompact", stdin="{}")
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout == ""
