"""A campaign that saw nothing must not certify everything (2026-08-25).

`_finish` re-runs discovery before stamping `parser_generation`, and asked only
whether the corpus had GROWN::

    added = sorted(current - known)
    if added: ... return

It could not see the opposite failure. When the source root goes away -- moved,
renamed, unmounted, a removed worktree, a cleaned scratch dir -- discovery
returns an empty list, so `current` and `known` are both empty, nothing has
drifted, no batch errored, and the campaign stamps the target generation having
re-parsed zero files.

⚠⚠ The damage is UNREPAIRABLE, which is what lifts this above a wrong number. A
stamp EQUAL to the constant is indistinguishable from a genuine one, so the
index is exempt from every future upgrade -- the exact bucket `PARSER_GENERATION`
exists to drain. Found by running the documented command against the three
pinned benchmark corpora: bare `.git` directories with no working tree, 8,220
pre-`.246` symbols between them, all three stamped `2` after re-parsing 0 files.

The non-vacuity pass is the point of this file. `TestTheGuardIsWhatBlocks`
reinstates the old one-directional check and asserts the false certificate comes
back -- a guard that is merely present looks identical to one that fires.
"""

import sqlite3

import pytest

from jcodemunch_mcp.tools import refresh
from jcodemunch_mcp.tools.index_folder import index_folder
from jcodemunch_mcp.storage.index_store import PARSER_GENERATION

NEWLINE = chr(10)


@pytest.fixture
def repo(tmp_path):
    """An indexed 6-file repo, its store, and a handle on the .db."""
    src = tmp_path / "repo" / "pkg"
    src.mkdir(parents=True)
    for i in range(1, 7):
        (src / f"m{i}.py").write_text(
            f"def f{i}():{NEWLINE}    return {i}{NEWLINE}", encoding="utf-8"
        )
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    out = index_folder(
        path=str(tmp_path / "repo"), use_ai_summaries=False, storage_path=str(store_dir)
    )
    assert out.get("success"), out
    (db,) = list(store_dir.glob("*.db"))
    return {"root": str(tmp_path / "repo"), "store": str(store_dir), "db": db, "src": src}


def _generation(db) -> int:
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute("SELECT value FROM meta WHERE key='parser_generation'").fetchall()
    finally:
        conn.close()
    return int(rows[0][0]) if rows else 0


def _set_generation(db, value: int) -> None:
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO meta(key,value) VALUES('parser_generation',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(value),),
        )
        conn.commit()
    finally:
        conn.close()


def _symbol_count(db) -> int:
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
    finally:
        conn.close()


def _empty_the_working_tree(repo) -> None:
    """Delete every source file, leave the directory. The shape a cleaned
    scratch dir, an unmounted drive and a removed worktree all present as."""
    for f in repo["src"].glob("*.py"):
        f.unlink()


class TestTheControl:
    """Without this, every assertion below could pass because nothing ever
    stamps -- the vacuity that makes a guard look like it works."""

    def test_an_intact_repo_still_stamps(self, repo):
        _set_generation(repo["db"], PARSER_GENERATION - 1)
        out = refresh.run(repo["root"], storage_path=repo["store"])
        assert out.get("success"), out
        assert out.get("stamped") is True, out
        assert out.get("stamp_skipped_reason") is None
        assert _generation(repo["db"]) == PARSER_GENERATION


class TestAVanishedCorpusDoesNotStamp:
    def test_empty_discovery_refuses_the_stamp(self, repo):
        _set_generation(repo["db"], PARSER_GENERATION - 1)
        before = _symbol_count(repo["db"])
        assert before > 0

        _empty_the_working_tree(repo)
        out = refresh.run(repo["root"], reset=True, storage_path=repo["store"])

        assert out.get("stamped") is not True, out
        assert out.get("stamp_skipped_reason") == "corpus_unreadable", out
        assert _generation(repo["db"]) == PARSER_GENERATION - 1, (
            "the index was certified at the target generation having re-parsed "
            "nothing, which no later upgrade can undo"
        )

    def test_it_says_how_many_rows_it_refused_to_certify(self, repo):
        """The count is the whole reason a caller can act on this."""
        _set_generation(repo["db"], PARSER_GENERATION - 1)
        _empty_the_working_tree(repo)
        out = refresh.run(repo["root"], reset=True, storage_path=repo["store"])
        assert out.get("indexed_files_not_reparsed") == 6, out

    def test_the_symbols_are_left_alone(self, repo):
        """Refusing to stamp must not also mean discarding the index."""
        _set_generation(repo["db"], PARSER_GENERATION - 1)
        before = _symbol_count(repo["db"])
        _empty_the_working_tree(repo)
        refresh.run(repo["root"], reset=True, storage_path=repo["store"])
        assert _symbol_count(repo["db"]) == before


class TestUnknownBlocksToo:
    """`None` from `_index_files` is could-not-establish, never "empty"."""

    def test_an_unreadable_index_refuses_the_stamp(self, repo, monkeypatch):
        _set_generation(repo["db"], PARSER_GENERATION - 1)
        _empty_the_working_tree(repo)
        monkeypatch.setattr(refresh, "_index_files", lambda *a, **k: None)
        out = refresh.run(repo["root"], reset=True, storage_path=repo["store"])
        assert out.get("stamped") is not True, out
        assert out.get("stamp_skipped_reason") == "index_unreadable", out
        assert _generation(repo["db"]) == PARSER_GENERATION - 1


class TestTheGuardIsWhatBlocks:
    """⚠⚠ NON-VACUITY. Reinstate the one-directional check and the false
    certificate must come back. A green suite proves nothing about a guard that
    was never the thing doing the blocking."""

    def test_without_the_guard_the_defect_returns(self, repo, monkeypatch):
        _set_generation(repo["db"], PARSER_GENERATION - 1)
        _empty_the_working_tree(repo)

        # The pre-fix world: nothing to compare discovery against, so the
        # emptiness cannot be noticed.
        monkeypatch.setattr(refresh, "_index_files", lambda *a, **k: set())

        out = refresh.run(repo["root"], reset=True, storage_path=repo["store"])
        assert out.get("stamped") is True, (
            "the defect did not reproduce, so the assertions above are not "
            "evidence that the guard fires"
        )
        assert _generation(repo["db"]) == PARSER_GENERATION
