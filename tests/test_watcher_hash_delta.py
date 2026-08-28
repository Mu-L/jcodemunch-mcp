"""The watcher refreshes its hash cache from what `index_folder` stored.

⚠⚠ This does NOT exist because the old full reload was slow. It is not:
`incremental_save` keeps the LRU entry coherent, so re-loading the index right
after saving it measures ~0.001 s. That was measured only after asserting the
opposite in the issue thread (#557, @Ticki84).

⚠⚠ It exists because a setting we ship reaches a cliff.
`JCODEMUNCH_INDEX_CACHE_TTL` evicts an index that has sat unused, and a watcher
is idle between edits BY DEFINITION -- so with the TTL set, every edit pays a
COLD hydration. Measured at TTL=1 with a 1.5 s gap between edits: 0.001 s ->
0.19 s per event on 15,075 symbols; #370 clocked a cold 665k-symbol hydration
at 7.5-11.4 minutes.

⚠ Re-reading the changed file instead is what the watcher did before, and it is
not the alternative: the file can change again between `index_folder`'s read and
the watcher's, so the cache records a hash for content nobody indexed and the
NEXT edit is skipped as unchanged (T6). The delta has no second read to race.
"""

from __future__ import annotations

import inspect
import pathlib

import pytest

from jcodemunch_mcp import watcher as watcher_mod
from jcodemunch_mcp.tools import index_folder as idx_mod

def _HELPER(*a, **k):
    """Resolved at CALL time, not import time.

    ⚠ Bound at module level, the whole file errors during COLLECTION against a
    tree without the helper -- one error instead of six named failures, so the
    non-vacuity pass cannot say WHICH property each test guards.
    """
    return idx_mod._attach_hash_delta(*a, **k)


def test_delta_is_withheld_when_no_change_set_was_supplied():
    """⚠⚠ `index_folder` is an MCP tool and this dict is unbounded in the size
    of the change set. On a full walk it would put every hash in the repository
    on the wire, against a response cap that REFUSES rather than truncates.
    Only the watcher passes `changed_paths`, so the tool response is unchanged.
    """
    r: dict = {}
    _HELPER(r, None, {"a.py": "h1"}, [])
    assert r == {}, "a non-watcher call must carry no hash delta"


def test_delta_reports_what_was_stored():
    r: dict = {}
    _HELPER(r, [object()], {"src/a.py": "h1", "src/b.py": "h2"}, ["src/gone.py"])
    assert r["file_hashes_delta"] == {"src/a.py": "h1", "src/b.py": "h2"}
    assert r["file_hashes_removed"] == ["src/gone.py"]


def test_empty_delta_is_still_a_delta():
    """⚠⚠ ABSENT and EMPTY are different answers and the consumer keeps them
    apart: absent means "this run cannot tell you" (reload), empty means
    "nothing moved". Same UNKNOWN-is-not-False rule as `has_any()`. A run that
    only touched mtimes returns empty, and that is authoritative.
    """
    r: dict = {}
    _HELPER(r, [object()], {}, [])
    assert r["file_hashes_delta"] == {}
    assert r["file_hashes_removed"] == []
    assert "file_hashes_delta" in r


def _watch_src() -> str:
    return inspect.getsource(watcher_mod._watch_single)


def test_deleted_paths_are_dropped_from_the_cache():
    """A removed file must LEAVE the cache, or its stale hash outlives it.

    ⚠ The first version of this test built a dict, called `update` and `pop` on
    it, and asserted the result -- i.e. it tested CPython's dict, passed against
    the unfixed tree, and guarded nothing. It was the one test of eight that
    survived the non-vacuity pass, which is exactly how a vacuous test announces
    itself. The property is that the watcher does the removal at all.
    """
    src = _watch_src()
    body = src[src.index("file_hashes_delta"):]
    assert "file_hashes_removed" in body, "deletions are never applied"
    assert ".pop(" in body, (
        "a deleted file must be removed from the hash cache, not merely left "
        "un-updated: `update()` alone keeps its stale hash forever"
    )


# ---------------------------------------------------------------------------
# The consumer half, asserted as a property of the source rather than by
# driving a real filesystem watcher.
# ---------------------------------------------------------------------------

def test_watcher_falls_back_when_the_delta_is_absent():
    """⚠⚠ The dangerous failure is treating a MISSING key as "nothing changed".

    That freezes the hash cache, so every later edit compares against a stale
    hash and is skipped as unchanged -- the watcher silently stops reindexing,
    which is the exact failure the cache exists to prevent. An older
    `index_folder`, a full-walk result, or any exit added later all return no
    delta, so the fallback is the common path, not the corner.
    """
    src = _watch_src()
    assert "isinstance(_delta, dict)" in src, (
        "the delta must be type-checked, not truth-checked: an empty dict is a "
        "valid authoritative answer and `if _delta:` would discard it"
    )
    assert "_build_hash_cache()" in src, "the full-reload fallback must survive"


def test_watcher_does_not_re_read_the_changed_file():
    """The T6 race, pinned. Nothing on this path may open a changed file to
    recompute a hash -- that is what the full reload replaced."""
    src = _watch_src()
    body = src[src.index("file_hashes_delta"):]
    for banned in ("_file_hash(", "open(", ".read_text("):
        assert banned not in body, (
            f"{banned!r} after the delta reintroduces the double-read race (T6)"
        )


@pytest.mark.parametrize("key", ["file_hashes_delta", "file_hashes_removed"])
def test_both_fast_path_returns_publish_the_delta(key):
    """⚠ The mtime-only early return is the one that gets forgotten.

    It exits before the main return, so a delta attached only at the bottom
    leaves that path reporting nothing and silently reloading forever.
    """
    src = pathlib.Path(idx_mod.__file__).read_text(encoding="utf-8")
    assert src.count("_attach_hash_delta(") >= 3, (
        "expected the helper plus both fast-path returns; a fast-path exit "
        "without it falls back to a full index load on every event"
    )
    assert key in src
