"""Tests for storage.process_locks — the v1.106.0 multi-process coordination
primitive used by watcher slots, save_index, and migrate_from_json.

Existing watcher-specific behavior is also covered in test_watcher_lock.py;
this file focuses on the generic (scope, target) API and the new metadata
fields (client_id, scope, target).
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from jcodemunch_mcp.storage import process_locks
from jcodemunch_mcp.storage.process_locks import (
    LockHolder,
    acquire,
    current_holder_diagnostic,
    held,
    inspect,
    lock_path,
    release,
    _client_id,
    _is_pid_alive,
    _path_hash,
)


# ---------------------------------------------------------------------------
# _path_hash
# ---------------------------------------------------------------------------

class TestPathHash:
    def test_same_target_same_hash(self):
        assert _path_hash("/foo/bar") == _path_hash("/foo/bar")

    def test_different_targets_different_hash(self):
        assert _path_hash("/foo/bar") != _path_hash("/foo/baz")

    def test_owner_slug_format(self):
        # Non-path targets like "owner/name" hash deterministically too.
        assert _path_hash("acme/widget") == _path_hash("acme/widget")
        assert _path_hash("acme/widget") != _path_hash("acme/gadget")


# ---------------------------------------------------------------------------
# _client_id
# ---------------------------------------------------------------------------

class TestClientId:
    def test_explicit_env_var_wins(self, monkeypatch):
        monkeypatch.setenv("JCODEMUNCH_CLIENT_ID", "my-test-client")
        assert _client_id() == "my-test-client"

    def test_falls_back_to_argv0_basename(self, monkeypatch):
        monkeypatch.delenv("JCODEMUNCH_CLIENT_ID", raising=False)
        monkeypatch.setattr(sys, "argv", ["/some/path/claude"])
        assert _client_id() == "claude"

    def test_unknown_when_nothing_useful(self, monkeypatch):
        monkeypatch.delenv("JCODEMUNCH_CLIENT_ID", raising=False)
        monkeypatch.setattr(sys, "argv", [""])
        # Empty argv falls through to "unknown"
        assert _client_id() in {"unknown", ""}  # Allow either; both are safe sentinels


# ---------------------------------------------------------------------------
# acquire / release / inspect round-trip
# ---------------------------------------------------------------------------

class TestAcquireReleaseRoundTrip:
    def test_acquire_then_release(self, tmp_path):
        assert acquire("test", "alpha", str(tmp_path)) is True
        release("test", "alpha", str(tmp_path))
        # Acquiring again after release must succeed
        assert acquire("test", "alpha", str(tmp_path)) is True
        release("test", "alpha", str(tmp_path))

    def test_acquire_blocks_duplicate(self, tmp_path):
        assert acquire("test", "alpha", str(tmp_path)) is True
        try:
            assert acquire("test", "alpha", str(tmp_path)) is False
        finally:
            release("test", "alpha", str(tmp_path))

    def test_different_scopes_independent(self, tmp_path):
        # watcher + indexwrite on the same target must not collide
        assert acquire("watcher", "alpha", str(tmp_path)) is True
        try:
            assert acquire("indexwrite", "alpha", str(tmp_path)) is True
            release("indexwrite", "alpha", str(tmp_path))
        finally:
            release("watcher", "alpha", str(tmp_path))

    def test_different_targets_independent(self, tmp_path):
        assert acquire("test", "alpha", str(tmp_path)) is True
        try:
            assert acquire("test", "beta", str(tmp_path)) is True
            release("test", "beta", str(tmp_path))
        finally:
            release("test", "alpha", str(tmp_path))


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------

class TestInspect:
    def test_no_holder_returns_none(self, tmp_path):
        assert inspect("test", "nothing", str(tmp_path)) is None

    def test_holder_metadata_complete(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JCODEMUNCH_CLIENT_ID", "test-runner")
        acquire("test", "alpha", str(tmp_path))
        try:
            h = inspect("test", "alpha", str(tmp_path))
            assert h is not None
            assert h.pid == os.getpid()
            assert h.client_id == "test-runner"
            assert h.scope == "test"
            assert h.target == "alpha"
            assert h.started_at  # ISO timestamp populated
            assert h.lock_path  # file path populated
        finally:
            release("test", "alpha", str(tmp_path))

    def test_stale_holder_returns_none(self, tmp_path):
        # Manually write a lock file with a dead PID
        dead_pid = os.getpid() + 999_999
        lf = lock_path("test", "alpha", str(tmp_path))
        lf.write_text(json.dumps({
            "scope": "test",
            "target": "alpha",
            "pid": dead_pid,
            "client_id": "ghost",
            "started_at": "2026-01-01T00:00:00+00:00",
        }), encoding="utf-8")
        assert inspect("test", "alpha", str(tmp_path)) is None

    def test_corrupt_metadata_returns_none(self, tmp_path):
        lf = lock_path("test", "alpha", str(tmp_path))
        lf.write_text("not valid json {{{", encoding="utf-8")
        assert inspect("test", "alpha", str(tmp_path)) is None


# ---------------------------------------------------------------------------
# LockHolder
# ---------------------------------------------------------------------------

class TestLockHolder:
    def test_as_dict_omits_invalid_age(self):
        h = LockHolder(
            scope="test", target="alpha", pid=1, client_id="x",
            started_at="not-a-timestamp", lock_path="/tmp/x.lock",
        )
        d = h.as_dict()
        assert "age_seconds" not in d
        assert d["pid"] == 1

    def test_as_dict_includes_age_when_parseable(self):
        h = LockHolder(
            scope="test", target="alpha", pid=1, client_id="x",
            started_at="2026-01-01T00:00:00+00:00", lock_path="/tmp/x.lock",
        )
        d = h.as_dict()
        assert "age_seconds" in d
        assert isinstance(d["age_seconds"], float)
        assert d["age_seconds"] > 0  # 2026-01-01 is in the past


# ---------------------------------------------------------------------------
# held() context manager
# ---------------------------------------------------------------------------

class TestHeldContextManager:
    def test_acquire_release_via_ctxmgr(self, tmp_path):
        with held("test", "alpha", str(tmp_path)) as got:
            assert got is True
        # Released — next acquire succeeds
        with held("test", "alpha", str(tmp_path)) as got2:
            assert got2 is True

    def test_returns_false_when_busy_and_no_wait(self, tmp_path):
        acquire("test", "alpha", str(tmp_path))
        try:
            with held("test", "alpha", str(tmp_path)) as got:
                assert got is False
        finally:
            release("test", "alpha", str(tmp_path))

    def test_wait_polls_until_the_lock_is_released(self, tmp_path, monkeypatch):
        """``held(wait_seconds=...)`` retries until the holder lets go.

        ⚠⚠ **Pinned by INTERLEAVING, not by wall clock.** The previous version
        released the lock from a thread that slept 0.5s and asserted the elapsed
        time landed inside ``0.4 < elapsed < 3.0``. That is a bet on the
        scheduler: ``time.sleep(N)`` is a floor, not a ceiling, and a contended
        Actions runner can stretch it past any ceiling worth asserting. It had
        already been re-tuned once for "Windows CI jitter" and it failed again on
        windows-3.12 during the 1.108.290 release -- green on the other eight
        jobs, green on two local Windows runs, and reproducing nothing.

        The property under test was never "this takes about half a second". It
        is "the loop polls, and it acquires once the lock is free". Releasing on
        the third poll states exactly that and costs no wall-clock time.
        """
        acquire("test", "alpha", str(tmp_path))
        clock = _FakeClock()
        clock.on_poll = lambda n: (
            release("test", "alpha", str(tmp_path)) if n == 3 else None
        )
        monkeypatch.setattr(process_locks, "time", clock)

        with held(
            "test", "alpha", str(tmp_path),
            wait_seconds=5.0, poll_seconds=0.1,
        ) as got:
            assert got is True

        # Three polls, each at poll_seconds -- it retried rather than spinning,
        # and it stopped as soon as the lock was free.
        assert clock.sleeps == [0.1, 0.1, 0.1]

    def test_wait_gives_up_at_the_deadline(self, tmp_path, monkeypatch):
        """A lock held past ``wait_seconds`` yields False.

        ⚠ Same treatment as its sibling above, and it needed it more: the old
        ceiling was ``elapsed < 1.5`` on a 0.3s wait, i.e. it tolerated 5x jitter
        and no more.
        """
        acquire("test", "alpha", str(tmp_path))
        clock = _FakeClock()
        monkeypatch.setattr(process_locks, "time", clock)
        try:
            with held(
                "test", "alpha", str(tmp_path),
                wait_seconds=0.3, poll_seconds=0.1,
            ) as got:
                assert got is False
        finally:
            release("test", "alpha", str(tmp_path))

        # Polled until the deadline, then stopped -- not one poll more.
        assert clock.sleeps == [0.1, 0.1, 0.1]
        assert clock.now == pytest.approx(0.3)


class _FakeClock:
    """Deterministic stand-in for the ``time`` module inside ``process_locks``.

    ``held.__enter__`` reads ``time.monotonic()`` once for its deadline and calls
    ``time.sleep(poll_seconds)`` between attempts. Advancing the clock BY the
    sleep amount, inside the patched sleep, reproduces the real relationship
    between the two while spending no wall-clock time at all.

    ⚠⚠ **Unknown attributes RAISE rather than falling through to the real
    module.** A pass-through would look harmless and be the worst outcome: if
    ``process_locks`` ever switches a deadline to ``time.perf_counter()``, half
    the clock would be fake and half real, and the test would go quietly wrong
    instead of loudly absent. Model the new call here.
    """

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []
        self.on_poll = None

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
        if self.on_poll is not None:
            self.on_poll(len(self.sleeps))

    def __getattr__(self, name):
        raise AttributeError(
            f"process_locks now calls time.{name}, which this fake clock does "
            f"not model. Model it here rather than letting a real clock leak "
            f"back into a deterministic test."
        )

# ---------------------------------------------------------------------------
# current_holder_diagnostic
# ---------------------------------------------------------------------------

class TestDiagnostic:
    def test_empty_when_no_holder(self, tmp_path):
        assert current_holder_diagnostic("test", "alpha", str(tmp_path)) == ""

    def test_includes_holder_details(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JCODEMUNCH_CLIENT_ID", "diagnostic-test")
        acquire("test", "alpha", str(tmp_path))
        try:
            d = current_holder_diagnostic("test", "alpha", str(tmp_path))
            assert "pid" in d
            assert "diagnostic-test" in d
        finally:
            release("test", "alpha", str(tmp_path))


# ---------------------------------------------------------------------------
# Integration: save_index serialises across processes (simulated)
# ---------------------------------------------------------------------------

class TestSaveIndexLock:
    def test_save_index_acquires_indexwrite_lock(self, tmp_path):
        """If indexwrite lock for owner/name is already held, save_index raises."""
        from jcodemunch_mcp.storage.sqlite_store import SQLiteIndexStore
        store = SQLiteIndexStore(base_path=str(tmp_path))

        # Pre-acquire the indexwrite lock to simulate another process holding it
        assert acquire("indexwrite", "test/repo", str(tmp_path)) is True
        try:
            # Use a very short wait so the test doesn't hang
            with patch.object(
                process_locks, "held",
                lambda *a, **kw: held(*a, **{**kw, "wait_seconds": 0.3, "poll_seconds": 0.1}),
            ):
                with pytest.raises(RuntimeError, match="index-write lock"):
                    store.save_index(
                        owner="test", name="repo",
                        source_files=["x.py"], symbols=[],
                        raw_files={"x.py": "print(1)"},
                    )
        finally:
            release("indexwrite", "test/repo", str(tmp_path))
