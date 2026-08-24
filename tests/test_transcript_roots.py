"""Multi-profile transcript discovery (jcm#421).

`receipt` scanned a hardcoded ``~/.claude/projects``. Claude Code relocates the
whole config tree when ``CLAUDE_CONFIG_DIR`` is set, so every session under a
second profile was invisible: the reporter measured 12 of 348 calls counted.
These tests pin the union scan, the discovery paths that populate it, and the
two hygiene properties the union depends on (session de-duplication and the
mtime prefilter).
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import time
from pathlib import Path

import pytest

from jcodemunch_mcp.cli.receipt import _projects_roots, iter_calls_multi, main
from jcodemunch_mcp.storage import transcript_roots as tr


def _write_session(path: Path, tool: str, tu_id: str, ts: str = "2026-08-05T12:00:00Z") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    events = [
        {
            "type": "assistant",
            "timestamp": ts,
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": tu_id, "name": tool, "input": {}}],
            },
        },
        {
            "type": "user",
            "timestamp": ts,
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": tu_id, "content": "x" * 400}],
            },
        },
    ]
    with open(path, "w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")


@pytest.fixture
def store(tmp_path, monkeypatch):
    """An isolated index store, so the registry never touches the real one."""
    root = tmp_path / "index"
    root.mkdir()
    monkeypatch.setenv("CODE_INDEX_PATH", str(root))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    # Keep default_root() off the developer's real ~/.claude during the test.
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    return root


class TestRegistry:
    def test_registers_and_reads_back(self, store, tmp_path):
        profile = tmp_path / "p1" / "projects"
        profile.mkdir(parents=True)
        assert tr.register(profile) is True
        assert profile in tr.known_roots()

    def test_second_register_is_a_no_op(self, store, tmp_path):
        profile = tmp_path / "p1" / "projects"
        profile.mkdir(parents=True)
        assert tr.register(profile) is True
        assert tr.register(profile) is False
        assert [p for p in tr.known_roots() if p == profile] == [profile]

    def test_root_that_no_longer_exists_is_skipped(self, store, tmp_path):
        gone = tmp_path / "deleted" / "projects"
        gone.mkdir(parents=True)
        tr.register(gone)
        gone.rmdir()
        assert gone not in tr.known_roots()

    def test_corrupt_registry_does_not_raise(self, store, tmp_path):
        tr.registry_path().write_text("{not json", encoding="utf-8")
        assert tr.known_roots() == []  # nothing exists on this fake home
        profile = tmp_path / "p1" / "projects"
        profile.mkdir(parents=True)
        assert tr.register(profile) is True

    def test_grandparent_of_transcript_path_is_the_root(self, store, tmp_path):
        transcript = tmp_path / "prof" / "projects" / "some-slug" / "abc.jsonl"
        transcript.parent.mkdir(parents=True)
        transcript.write_text("", encoding="utf-8")
        assert tr.register_from_transcript_path(str(transcript)) is True
        assert transcript.parent.parent in tr.known_roots()

    def test_missing_transcript_path_is_ignored(self, store):
        assert tr.register_from_transcript_path(None) is False
        assert tr.register_from_transcript_path("") is False

    def test_env_root_registered_from_claude_config_dir(self, store, tmp_path, monkeypatch):
        cfg = tmp_path / "headroom-on"
        (cfg / "projects").mkdir(parents=True)
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cfg))
        assert tr.register_session_root() is True
        assert cfg / "projects" in tr.known_roots()

    def test_no_env_root_without_the_variable(self, store):
        assert tr.env_root() is None
        assert tr.register_session_root() is False


class TestUnionScan:
    def test_counts_every_profile(self, store, tmp_path):
        # The reported shape: default profile plus two CLAUDE_CONFIG_DIR ones.
        default = tmp_path / "home" / ".claude" / "projects"
        _write_session(default / "proj" / "s-default.jsonl", "mcp__jcodemunch__search_symbols", "t1")
        for i, name in enumerate(("on", "off"), start=2):
            root = tmp_path / f"prof-{name}" / "projects"
            _write_session(root / "proj" / f"s-{name}.jsonl", "mcp__jcodemunch__search_text", f"t{i}")
            tr.register(root)

        calls = list(iter_calls_multi(_projects_roots()))
        assert len(calls) == 3

    def test_default_root_alone_undercounts(self, store, tmp_path):
        """The bug, pinned: scanning only the default root loses the rest."""
        default = tmp_path / "home" / ".claude" / "projects"
        _write_session(default / "proj" / "s-default.jsonl", "mcp__jcodemunch__search_symbols", "t1")
        other = tmp_path / "prof" / "projects"
        _write_session(other / "proj" / "s-other.jsonl", "mcp__jcodemunch__search_text", "t2")
        tr.register(other)

        assert len(list(iter_calls_multi([default]))) == 1
        assert len(list(iter_calls_multi(_projects_roots()))) == 2

    def test_same_session_in_two_roots_counted_once(self, store, tmp_path):
        """A copied or symlinked tree must not double the ledger."""
        a = tmp_path / "a" / "projects"
        b = tmp_path / "b" / "projects"
        _write_session(a / "proj" / "session-uuid.jsonl", "mcp__jcodemunch__search_text", "t1")
        _write_session(b / "proj" / "session-uuid.jsonl", "mcp__jcodemunch__search_text", "t1")
        assert len(list(iter_calls_multi([a, b]))) == 1

    def test_missing_root_is_skipped_not_fatal(self, store, tmp_path):
        real = tmp_path / "real" / "projects"
        _write_session(real / "proj" / "s.jsonl", "mcp__jcodemunch__search_text", "t1")
        calls = list(iter_calls_multi([tmp_path / "nope", real]))
        assert len(calls) == 1


class TestMtimePrefilter:
    def test_file_older_than_the_window_is_not_opened(self, store, tmp_path):
        root = tmp_path / "p" / "projects"
        old = root / "proj" / "old.jsonl"
        _write_session(old, "mcp__jcodemunch__search_text", "t1", ts="2026-01-01T12:00:00Z")
        stale = time.time() - 90 * 86400
        os.utime(old, (stale, stale))

        since = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=7)
        assert list(iter_calls_multi([root], since=since)) == []

    def test_recent_file_inside_the_window_still_counted(self, store, tmp_path):
        root = tmp_path / "p" / "projects"
        now = _dt.datetime.now(_dt.timezone.utc)
        _write_session(
            root / "proj" / "new.jsonl",
            "mcp__jcodemunch__search_text",
            "t1",
            ts=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        since = now - _dt.timedelta(days=7)
        assert len(list(iter_calls_multi([root], since=since))) == 1

    def test_no_since_means_no_mtime_skipping(self, store, tmp_path):
        root = tmp_path / "p" / "projects"
        old = root / "proj" / "old.jsonl"
        _write_session(old, "mcp__jcodemunch__search_text", "t1", ts="2026-01-01T12:00:00Z")
        stale = time.time() - 90 * 86400
        os.utime(old, (stale, stale))
        assert len(list(iter_calls_multi([root]))) == 1

    def test_fresh_copy_survives_a_stale_copy_of_the_same_session(self, store, tmp_path):
        """A skipped stale file must not claim the session UUID."""
        a = tmp_path / "a" / "projects"
        b = tmp_path / "b" / "projects"
        now = _dt.datetime.now(_dt.timezone.utc)
        ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        _write_session(a / "proj" / "same-uuid.jsonl", "mcp__jcodemunch__search_text", "t1", ts=ts)
        _write_session(b / "proj" / "same-uuid.jsonl", "mcp__jcodemunch__search_text", "t1", ts=ts)
        stale = time.time() - 90 * 86400
        os.utime(a / "proj" / "same-uuid.jsonl", (stale, stale))

        since = now - _dt.timedelta(days=7)
        assert len(list(iter_calls_multi([a, b], since=since))) == 1


class TestCli:
    def test_projects_root_is_repeatable(self, store, tmp_path, capsys):
        a = tmp_path / "a" / "projects"
        b = tmp_path / "b" / "projects"
        _write_session(a / "proj" / "sa.jsonl", "mcp__jcodemunch__search_text", "t1")
        _write_session(b / "proj" / "sb.jsonl", "mcp__jcodemunch__search_text", "t2")

        out = tmp_path / "out.json"
        rc = main([
            "--days", "0",
            "--projects-root", str(a),
            "--projects-root", str(b),
            "--export", str(out),
        ])
        assert rc == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["totals"]["calls"] == 2
        assert len(payload["transcript_roots"]) >= 2

    def test_explicit_roots_override_discovery(self, store, tmp_path):
        """Compatibility: naming a root still means "scan exactly that tree".

        Making the flag additive would break the one thing it was already good
        for — pinning a scan — and every script that relied on the isolation.
        """
        registered = tmp_path / "registered" / "projects"
        _write_session(registered / "proj" / "s-reg.jsonl", "mcp__jcodemunch__search_text", "t1")
        tr.register(registered)
        pinned = tmp_path / "pinned" / "projects"
        _write_session(pinned / "proj" / "s-pin.jsonl", "mcp__jcodemunch__search_text", "t2")

        assert _projects_roots([pinned]) == [pinned]
        assert len(list(iter_calls_multi(_projects_roots([pinned])))) == 1
        assert len(list(iter_calls_multi(_projects_roots()))) == 1  # the registered one

    def test_roots_flag_lists_what_would_be_scanned(self, store, tmp_path, capsys):
        extra = tmp_path / "extra" / "projects"
        extra.mkdir(parents=True)
        tr.register(extra)
        assert main(["--roots"]) == 0
        listed = json.loads(capsys.readouterr().out)["roots"]
        assert str(extra) in listed


class TestHookSideEffect:
    def test_hook_registration_writes_nothing_to_stdout(self, store, tmp_path, capsys):
        """Claude Code parses hook stdout as the hook's reply — a stray write
        there corrupts the protocol, so the registry side effect must be mute."""
        from jcodemunch_mcp.cli.hooks._common import _note_transcript_root

        transcript = tmp_path / "prof" / "projects" / "slug" / "s.jsonl"
        transcript.parent.mkdir(parents=True)
        transcript.write_text("", encoding="utf-8")

        _note_transcript_root({"transcript_path": str(transcript)})
        captured = capsys.readouterr()
        assert captured.out == ""
        assert transcript.parent.parent in tr.known_roots()

    def test_malformed_payload_is_survivable(self, store):
        from jcodemunch_mcp.cli.hooks._common import _note_transcript_root

        _note_transcript_root(None)
        _note_transcript_root("not a dict")
        _note_transcript_root({"transcript_path": 17})
