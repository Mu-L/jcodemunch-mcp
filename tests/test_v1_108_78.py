"""Regression tests for the v1.108.78 mmashwani issue batch (#351/#352/#353/#354).

- #352: Python 3.12 `type` alias statements emit kind="type" symbols.
- #354: get_ranked_context compact rows are populated (no blank rows); the
  schema-driven encoder fails closed on a producer/schema mismatch.
- #353: a missing watcher dependency / crashed watch task is surfaced by
  reindex_state (fatal) instead of reporting healthy.
- #351: source modules named *secret* are indexable; index_file refuses real
  credential files so it agrees with index_folder eligibility.
"""

import builtins

import pytest

from jcodemunch_mcp.parser.extractor import parse_file


# ── #352: Python 3.12 type alias symbols ──────────────────────────────────────

class TestPythonTypeAlias:
    def test_simple_type_alias_emits_type_symbol(self):
        src = "type JsonReportValue = str | int\n"
        syms = parse_file(src, "redaction.py", "python")
        types = [s for s in syms if s.kind == "type"]
        assert len(types) == 1
        sym = types[0]
        assert sym.name == "JsonReportValue"
        assert sym.signature == "type JsonReportValue = str | int"
        assert sym.line == 1

    def test_generic_type_alias_name_is_alias_not_param(self):
        src = "type Vec[T] = list[T]\n"
        syms = parse_file(src, "redaction.py", "python")
        types = [s for s in syms if s.kind == "type"]
        assert [s.name for s in types] == ["Vec"]

    def test_functions_and_classes_unaffected(self):
        src = (
            "type Alias = int\n\n"
            "def f(x: Alias) -> Alias:\n    return x\n\n"
            "class C:\n    pass\n"
        )
        syms = parse_file(src, "m.py", "python")
        by_kind = {}
        for s in syms:
            by_kind.setdefault(s.kind, []).append(s.name)
        assert "Alias" in by_kind["type"]
        assert "f" in by_kind["function"]
        assert "C" in by_kind["class"]


# ── #354: ranked-context compact rows ─────────────────────────────────────────

class TestRankedContextCompact:
    def test_compact_fields_populated(self):
        from jcodemunch_mcp.tools.get_ranked_context import _compact_fields

        sym = {"id": "f.py::foo#function", "name": "foo", "kind": "function",
               "file": "f.py", "line": 12, "signature": "def foo()"}
        fields = _compact_fields(sym, 0.5, 42)
        assert fields["id"] == "f.py::foo#function"
        assert fields["name"] == "foo"
        assert fields["kind"] == "function"
        assert fields["file"] == "f.py"
        assert fields["line"] == 12
        assert fields["score"] == 0.5
        assert fields["token_cost"] == 42
        assert fields["summary"]

    def test_good_shape_encodes_nonblank_rows(self):
        from jcodemunch_mcp.encoding import encode_response
        from jcodemunch_mcp.encoding.schemas.get_ranked_context import decode

        resp = {
            "context_items": [
                {"id": "a#function", "name": "a", "kind": "function",
                 "file": "a.py", "line": 1, "score": 0.9, "token_cost": 10,
                 "summary": "does a"},
            ],
            "total_tokens": 10, "budget_tokens": 100,
            "items_included": 1, "items_considered": 1,
        }
        payload, meta = encode_response("get_ranked_context", resp, "compact")
        assert meta["encoding"] == "rc1"
        rows = decode(payload)["context_items"]
        assert len(rows) == 1
        assert rows[0]["id"] == "a#function"
        assert rows[0]["file"] == "a.py"

    def test_legacy_shape_falls_back_to_json(self):
        """A producer dict with only legacy keys (no declared cols) must not
        silently encode to blank rows — the encoder fails closed and the
        dispatcher returns JSON so the data survives."""
        from jcodemunch_mcp.encoding import encode_response

        resp = {
            "context_items": [
                {"symbol_id": "x", "combined_score": 0.5, "tokens": 10},
            ],
            "total_tokens": 10, "budget_tokens": 100,
            "items_included": 1, "items_considered": 1,
        }
        _, meta = encode_response("get_ranked_context", resp, "compact")
        assert meta["encoding"] == "json"


# ── #353: watcher health visibility ───────────────────────────────────────────

class TestWatcherHealth:
    def test_fatal_failure_surfaces_immediately(self):
        import jcodemunch_mcp.reindex_state as rs

        repo = "local/fatal-test-aaa"
        rs.mark_reindex_failed(repo, "watchfiles missing", fatal=True)
        st = rs.get_reindex_status(repo)
        assert st["reindex_failures"] == 1
        assert st["reindex_fatal"] is True
        assert "watchfiles" in st["reindex_error"]

    def test_transient_single_failure_not_surfaced(self):
        import jcodemunch_mcp.reindex_state as rs

        repo = "local/transient-test-bbb"
        rs.mark_reindex_failed(repo, "blip")
        st = rs.get_reindex_status(repo)
        assert "reindex_failures" not in st
        assert "reindex_fatal" not in st

    def test_success_clears_fatal(self):
        import jcodemunch_mcp.reindex_state as rs

        repo = "local/clears-test-ccc"
        rs.mark_reindex_failed(repo, "watchfiles missing", fatal=True)
        rs.mark_reindex_done(repo, {"ok": 1})
        st = rs.get_reindex_status(repo)
        assert "reindex_failures" not in st
        assert not st.get("reindex_fatal")

    def test_require_watchfiles_raises_when_missing(self, monkeypatch):
        from jcodemunch_mcp.watcher import _require_watchfiles, WatcherDependencyError

        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "watchfiles":
                raise ImportError("no watchfiles")
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(WatcherDependencyError):
            _require_watchfiles()

    def test_watch_status_keys_by_repo_id(self, tmp_path, monkeypatch):
        """get_watch_status must read reindex_state under the repo_id key a watch
        task writes, not the folder path, so a failing task is visible."""
        import jcodemunch_mcp.reindex_state as rs
        from jcodemunch_mcp.tools import get_watch_status as gws

        folder = str(tmp_path / "repo")
        repo_id = "local/repo-deadbeef"

        monkeypatch.setattr(gws, "discover_local_repo_entries",
                            lambda sp=None: {folder: {}})
        monkeypatch.setattr(gws, "_reindex_key", lambda f, sp: repo_id)
        monkeypatch.setattr(gws, "service_status", lambda: {"active": True})
        monkeypatch.setattr(gws.process_locks, "inspect", lambda *a, **k: None)

        rs.mark_reindex_failed(repo_id, "watchfiles missing", fatal=True)
        out = gws.get_watch_status(str(tmp_path / "store"))
        assert out["any_failing"] is True
        assert out["repos"][0].get("reindex_fatal") is True


# ── #351: index_file honors secret-file eligibility ───────────────────────────

class TestIndexFileSecretEligibility:
    def test_source_module_named_secret_is_indexable(self, tmp_path):
        from jcodemunch_mcp.tools.index_folder import index_folder
        from jcodemunch_mcp.tools.index_file import index_file

        src = tmp_path / "src"
        src.mkdir()
        store = tmp_path / "store"
        (src / "secret_redaction.py").write_text(
            "def redact(v):\n    return v\n", encoding="utf-8"
        )
        folder_res = index_folder(str(src), use_ai_summaries=False, storage_path=str(store))
        assert folder_res["success"] is True
        # The source module must be in the folder index (not skipped as secret).
        assert folder_res["file_count"] == 1

        file_res = index_file(
            path=str(src / "secret_redaction.py"),
            use_ai_summaries=False,
            storage_path=str(store),
        )
        assert file_res["success"] is True

    def test_index_file_refuses_real_credential_file(self, tmp_path):
        from jcodemunch_mcp.tools.index_folder import index_folder
        from jcodemunch_mcp.tools.index_file import index_file

        src = tmp_path / "src"
        src.mkdir()
        store = tmp_path / "store"
        (src / "app.py").write_text("x = 1\n", encoding="utf-8")
        index_folder(str(src), use_ai_summaries=False, storage_path=str(store))

        # A real credential file: index_file must refuse it (folder skips it too),
        # so it can't create an entry the next full folder index would prune.
        (src / "service.key").write_text("PRIVATE", encoding="utf-8")
        res = index_file(
            path=str(src / "service.key"),
            use_ai_summaries=False,
            storage_path=str(store),
        )
        assert res["success"] is False
        assert res.get("skipped") == "secret"
