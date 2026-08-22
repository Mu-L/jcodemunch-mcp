"""Regression tests for the 2026-08 hook-steering fix batch.

Each class pins one confirmed defect from the "Claude forgets to call
jCodeMunch" investigation: coverage gaps (Bash/Glob unhooked), silently dead
hooks (empty in-process journal, absent owner/name keys, bare-name spawn,
symlink-blind root comparison, stale installed matchers), and mis-steering
(Read nudge outside indexed repos, surface-blind subagent catalog).
"""

import io
import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

from jcodemunch_mcp.cli.hooks import (
    _norm_path,
    _repo_owner_name,
    _self_invocation,
    run_pretooluse,
    run_subagentstart,
    run_taskcomplete,
)


def _run(func, stdin_text: str) -> tuple[int, str, str]:
    fake_in, fake_out, fake_err = (
        io.StringIO(stdin_text), io.StringIO(), io.StringIO(),
    )
    with mock.patch.object(sys, "stdin", fake_in), \
         mock.patch.object(sys, "stdout", fake_out), \
         mock.patch.object(sys, "stderr", fake_err):
        rc = func()
    return rc, fake_out.getvalue(), fake_err.getvalue()


def _norm(p) -> str:
    return _norm_path(str(p))  # the production comparison rule, not a copy


@pytest.fixture
def indexed_tmp(tmp_path, monkeypatch):
    """Pretend tmp_path is an indexed repo root."""
    monkeypatch.setattr(
        "jcodemunch_mcp.cli.hooks._indexed_source_roots",
        lambda: [_norm(tmp_path)],
    )
    return tmp_path


def _pretool(tool_name: str, tool_input: dict, cwd: str = "") -> str:
    return json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "cwd": cwd,
    })


def _mock_store(monkeypatch, repos, loaded=None, idx=None):
    """Install a store fake with the REAL list_repos() entry shape."""
    if idx is None:
        idx = mock.MagicMock()
        idx.symbols = []
        idx.source_files = ["main.py"]
        idx.imports = {}
    def _load(self, owner, name):
        if loaded is not None:
            loaded.append(name)
        return idx

    MockStore = type("MockStore", (), {
        "__init__": lambda self, **kw: None,
        "list_repos": lambda self: repos,
        "load_index": _load,
    })
    monkeypatch.setattr("jcodemunch_mcp.storage.IndexStore", MockStore)


class TestBashSearchInterception:
    """Bash `grep`/`rg`/`find` was the dominant unhooked search route — and the
    escape hatch a strict-denied Grep funneled the model into."""

    def test_leading_grep_in_indexed_repo_nudges(self, indexed_tmp):
        rc, out, _ = _run(run_pretooluse, _pretool(
            "Bash", {"command": "grep -rn TODO src/"}, cwd=str(indexed_tmp)))
        assert rc == 0
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        assert "search_text" in ctx

    def test_leading_rg_strict_denies(self, indexed_tmp, monkeypatch):
        monkeypatch.setenv("JCODEMUNCH_ENFORCE", "strict")
        rc, out, _ = _run(run_pretooluse, _pretool(
            "Bash", {"command": "rg foo"}, cwd=str(indexed_tmp)))
        assert rc == 0
        hso = json.loads(out)["hookSpecificOutput"]
        assert hso["permissionDecision"] == "deny"

    def test_piped_grep_passes_silently(self, indexed_tmp):
        """A grep after a pipe filters other output — jcm cannot serve it."""
        rc, out, _ = _run(run_pretooluse, _pretool(
            "Bash", {"command": "git log --oneline | grep fix"},
            cwd=str(indexed_tmp)))
        assert (rc, out) == (0, "")

    def test_non_search_bash_passes_silently(self, indexed_tmp, monkeypatch):
        monkeypatch.setenv("JCODEMUNCH_ENFORCE", "strict")
        rc, out, _ = _run(run_pretooluse, _pretool(
            "Bash", {"command": "pytest tests/ -q"}, cwd=str(indexed_tmp)))
        assert (rc, out) == (0, "")

    def test_outside_indexed_repo_passes_silently(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "jcodemunch_mcp.cli.hooks._indexed_source_roots", lambda: []
        )
        rc, out, _ = _run(run_pretooluse, _pretool(
            "Bash", {"command": "grep -rn TODO ."}, cwd=str(tmp_path)))
        assert (rc, out) == (0, "")

    def test_absolute_target_outside_repo_passes_even_strict(
        self, indexed_tmp, monkeypatch
    ):
        """`grep foo /etc/hosts` from an indexed-repo cwd targets a path jcm
        cannot serve — denying it (or claiming it targets the repo) is false."""
        monkeypatch.setenv("JCODEMUNCH_ENFORCE", "strict")
        rc, out, _ = _run(run_pretooluse, _pretool(
            "Bash", {"command": "grep -n root /etc/hosts"}, cwd=str(indexed_tmp)))
        assert (rc, out) == (0, "")

    def test_pipeline_grep_is_nudged_not_denied(self, indexed_tmp, monkeypatch):
        """A deny is only coherent for a PURE search: `rg | xargs sed -i` or
        `grep -q x && make` do work the jcm routes cannot replace."""
        monkeypatch.setenv("JCODEMUNCH_ENFORCE", "strict")
        for cmd in ("rg -l foo | xargs sed -i 's/a/b/'",
                    "grep -q foo src/x.py && make build"):
            rc, out, _ = _run(run_pretooluse, _pretool(
                "Bash", {"command": cmd}, cwd=str(indexed_tmp)))
            assert rc == 0
            hso = json.loads(out)["hookSpecificOutput"]
            assert "permissionDecision" not in hso, cmd
            assert "search_text" in hso["additionalContext"], cmd

    def test_dotdot_target_passes_even_strict(self, indexed_tmp, monkeypatch):
        """`grep foo ../sibling/` escapes cwd — the one relative shape that
        provably leaves the repo; silence, never a false deny."""
        monkeypatch.setenv("JCODEMUNCH_ENFORCE", "strict")
        rc, out, _ = _run(run_pretooluse, _pretool(
            "Bash", {"command": "grep -rn foo ../sibling/"},
            cwd=str(indexed_tmp)))
        assert (rc, out) == (0, "")

    def test_find_is_never_strict_denied(self, indexed_tmp, monkeypatch):
        """`find ... -delete` opens with the same word as a search — a deny
        steering to search routes cannot do the deletion, so find only nudges."""
        monkeypatch.setenv("JCODEMUNCH_ENFORCE", "strict")
        rc, out, _ = _run(run_pretooluse, _pretool(
            "Bash", {"command": "find . -name '*.pyc' -delete"},
            cwd=str(indexed_tmp)))
        assert rc == 0
        hso = json.loads(out)["hookSpecificOutput"]
        assert "permissionDecision" not in hso
        assert "get_file_tree" in hso["additionalContext"]


class TestGlobInterception:
    def test_glob_in_indexed_repo_nudges(self, indexed_tmp):
        rc, out, _ = _run(run_pretooluse, _pretool(
            "Glob", {"pattern": "**/*.py"}, cwd=str(indexed_tmp)))
        assert rc == 0
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        assert "get_file_tree" in ctx

    def test_glob_strict_denies(self, indexed_tmp, monkeypatch):
        monkeypatch.setenv("JCODEMUNCH_ENFORCE", "strict")
        rc, out, _ = _run(run_pretooluse, _pretool(
            "Glob", {"pattern": "**/*.py"}, cwd=str(indexed_tmp)))
        assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"


class TestSymlinkedRootsStillOverlap:
    """index_folder records source_root via Path.resolve(); the hook compared
    abspath only, so any symlink component (macOS /tmp -> /private/tmp) made
    the whole steering layer silently inert."""

    def test_symlink_alias_of_indexed_root_fires_nudge(self, tmp_path, monkeypatch):
        real = tmp_path / "repo"
        real.mkdir()
        alias = tmp_path / "alias"
        os.symlink(real, alias)
        monkeypatch.setattr(
            "jcodemunch_mcp.cli.hooks._indexed_source_roots",
            lambda: [_norm(real)],  # stored resolved, as index_folder does
        )
        rc, out, _ = _run(run_pretooluse, _pretool(
            "Grep", {"pattern": "foo"}, cwd=str(alias)))
        assert rc == 0
        assert "search_text" in json.loads(out)["hookSpecificOutput"]["additionalContext"]


class TestRepoOwnerName:
    """list_repos() entries carry {"repo": "owner/name"} — never owner/name
    keys. Three hook loops read the absent keys and skipped every repo."""

    def test_real_store_shape(self):
        assert _repo_owner_name({"repo": "local/proj-abc"}) == ("local", "proj-abc")

    def test_wrong_mock_shape_is_rejected(self):
        """The owner/name shape only ever came from wrong test mocks; accepting
        it would re-license the mock shape that masked this defect."""
        assert _repo_owner_name({"owner": "o", "name": "n"}) == ("", "")

    def test_garbage(self):
        assert _repo_owner_name({}) == ("", "")
        assert _repo_owner_name({"repo": "noslash"}) == ("", "")


class TestTaskCompleteLiveJournal:
    """run_taskcomplete read the empty in-process journal (#334 class) — the
    diagnostics never fired in any real deployment. It must read the persisted
    live journal, like PreCompact/SessionStart already do."""

    def test_live_journal_drives_diagnostics(self, monkeypatch):
        monkeypatch.setattr(
            "jcodemunch_mcp.tools.session_state.load_live_journal",
            lambda **kw: {"files_edited": [{"file": "src/a.py", "edits": 1}]},
        )
        idx = mock.MagicMock()
        idx.source_files = ["src/a.py", "src/b.py"]
        idx.symbols = [{"name": "f", "file": "src/a.py", "line": 1}]
        _mock_store(monkeypatch, [{"repo": "local/proj"}], idx=idx)
        monkeypatch.setattr(
            "jcodemunch_mcp.tools.find_dead_code.find_dead_code",
            lambda repo_id, granularity: {
                "dead_symbols": [{"name": "f", "file": "src/a.py", "line": 1}],
            },
        )
        monkeypatch.setattr(
            "jcodemunch_mcp.tools.get_untested_symbols.get_untested_symbols",
            lambda *a, **kw: {"untested_symbols": []},
        )
        monkeypatch.setattr(
            "jcodemunch_mcp.tools.check_references.check_references",
            lambda *a, **kw: {
                "results": [{"identifier": "f", "is_referenced": True}],
            },
        )
        rc, out, _ = _run(run_taskcomplete, '{"hook_event_name": "TaskCompleted"}')
        assert rc == 0
        assert out, "live journal with edits must produce diagnostics"
        msg = json.loads(out)["systemMessage"]
        assert "local/proj" in msg
        assert "Possibly orphaned" in msg


class TestSelfInvocation:
    """The reindex child must reuse THIS install's invocation — a bare-name
    Popen died silently under the hook shell's minimal PATH, on exactly the
    installs init's absolute-path resolution exists for."""

    def test_never_bare_name(self):
        inv = _self_invocation()
        assert inv != ["jcodemunch-mcp"]
        assert os.path.isabs(inv[0])

    def test_fallback_is_python_dash_m(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["/nonexistent/whatever"])
        assert _self_invocation() == [sys.executable, "-m", "jcodemunch_mcp"]

    def test_prefers_own_executable_when_it_exists(self, tmp_path, monkeypatch):
        exe = tmp_path / "jcodemunch-mcp"
        exe.write_text("#!/bin/sh\n")
        monkeypatch.setattr(sys, "argv", [str(exe)])
        assert _self_invocation() == [str(exe)]


class TestSubagentCatalogMatchesSurface:
    """Under tool_surface=counter the raw catalog names are not callable; the
    briefing must describe the order/menu/route front door instead."""

    @pytest.fixture
    def _store(self, monkeypatch):
        _mock_store(monkeypatch, [{"repo": "test/repo"}])

    def test_counter_surface_briefs_front_door(self, _store, monkeypatch):
        monkeypatch.setenv("JCODEMUNCH_TOOL_SURFACE", "counter")
        _, out, _ = _run(run_subagentstart, "{}")
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        assert "`menu`" in ctx and "`order`" in ctx and "`route`" in ctx
        assert "search_symbols," not in ctx  # the 41-name list is uncallable here

    def test_cwd_scopes_briefing_to_containing_repo(self, monkeypatch, tmp_path):
        """A subagent spawned into repo A must not pay hydration + PageRank
        for every other indexed repo on the box (nor read briefings about
        them). No cwd overlap keeps the brief-everything fallback."""
        a = tmp_path / "a"
        a.mkdir()
        loaded: list = []
        _mock_store(monkeypatch, [
            {"repo": "test/a", "source_root": str(a)},
            {"repo": "test/b", "source_root": str(tmp_path / "b")},
        ], loaded=loaded)
        monkeypatch.setenv("JCODEMUNCH_TOOL_SURFACE", "full")
        _, out, _ = _run(run_subagentstart, json.dumps({"cwd": str(a)}))
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        assert "test/a" in ctx
        assert "test/b" not in ctx
        assert loaded == ["a"]  # the unrelated repo was never hydrated

    def test_full_surface_briefs_catalog(self, _store, monkeypatch):
        monkeypatch.setenv("JCODEMUNCH_TOOL_SURFACE", "full")
        _, out, _ = _run(run_subagentstart, "{}")
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        assert "search_symbols" in ctx

    def _fresh_config_state(self, monkeypatch, store):
        """Force config's lazy load to run against *store* (conftest pre-seeds
        DEFAULTS with _CONFIG_LOADED=True, which would bypass the file read)."""
        import jcodemunch_mcp.config as cfg
        monkeypatch.delenv("JCODEMUNCH_TOOL_SURFACE", raising=False)
        monkeypatch.setenv("CODE_INDEX_PATH", str(store))
        monkeypatch.setattr(cfg, "_GLOBAL_CONFIG", {})
        monkeypatch.setattr(cfg, "_CONFIG_LOADED", False)

    def test_counter_from_config_file_not_env(self, _store, monkeypatch, tmp_path):
        """The defect's primary scenario: fresh installs get counter via
        config.jsonc, not the env var. _tool_surface must read it through
        config.get — load_config() returns None, so the old
        load_config().get(...) raised into the except and silently resolved
        to 'full' forever, keeping the surface-blind briefing alive."""
        store = tmp_path / "store"
        store.mkdir()
        (store / "config.jsonc").write_text(
            '{"tool_surface": "counter"}', encoding="utf-8"
        )
        self._fresh_config_state(monkeypatch, store)
        from jcodemunch_mcp.cli.hooks import _tool_surface
        assert _tool_surface() == "counter"

    def test_tool_surface_read_never_writes_config(self, monkeypatch, tmp_path):
        """A config READ from a hook process must never create config.jsonc
        (Maintenance Practice 8; load_config's default create_missing=True
        did exactly that before the fix)."""
        store = tmp_path / "store2"
        store.mkdir()
        (store / "index.db").write_text("", encoding="utf-8")  # looks installed
        self._fresh_config_state(monkeypatch, store)
        from jcodemunch_mcp.cli.hooks import _tool_surface
        _tool_surface()
        assert not (store / "config.jsonc").exists()


class TestHostileStdin:
    """A hook must never crash on unexpected payload shapes."""

    @pytest.mark.parametrize("payload", [
        "null", "[]", '"a string"', "42",
        '{"tool_name": "Read", "tool_input": null}',
        '{"tool_name": "Read", "tool_input": "nope"}',
        '{"tool_name": "Bash", "tool_input": {"command": null}}',
        '{"tool_name": "Read", "tool_input": {"file_path": 7}}',
    ])
    def test_pretooluse_survives(self, payload):
        rc, _, _ = _run(run_pretooluse, payload)
        assert rc == 0

    @pytest.mark.parametrize("payload", [
        "null", "[]", '{"tool_input": null}', '{"tool_input": {"file_path": 7}}',
    ])
    def test_posttooluse_survives(self, payload):
        from jcodemunch_mcp.cli.hooks import run_posttooluse
        rc, _, _ = _run(run_posttooluse, payload)
        assert rc == 0


class TestMinSizeGarbageEnv:
    def test_garbage_env_parses_to_default(self):
        """Garbage JCODEMUNCH_HOOK_MIN_SIZE must fall back to the default, not
        crash every hook at import time."""
        import subprocess
        r = subprocess.run(
            [sys.executable, "-c",
             "from jcodemunch_mcp.cli.hooks import _MIN_SIZE_BYTES; "
             "print(_MIN_SIZE_BYTES)"],
            env={**os.environ, "JCODEMUNCH_HOOK_MIN_SIZE": "not-a-number",
                 # Anchored to this file: a cwd-relative "src" would import
                 # whatever package the runner's cwd happens to expose.
                 "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
            capture_output=True, text=True, timeout=60,
        )
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == "4096"


class TestMatcherUpgrade:
    """_merge_hooks left a pre-1.108.47 install's matcher "Read" in place
    forever: re-running init reported success while Grep steering never fired."""

    def test_stale_matcher_upgraded_in_place(self):
        from jcodemunch_mcp.cli.init import _enforcement_hooks, _merge_hooks

        data = {"hooks": {"PreToolUse": [{
            "matcher": "Read",
            "hooks": [{"type": "command",
                       "command": "jcodemunch-mcp hook-pretooluse"}],
        }]}}
        added, updated = _merge_hooks(
            data, _enforcement_hooks(), "jcodemunch-mcp hook-p"
        )
        shipped = _enforcement_hooks()["PreToolUse"][0]["matcher"]
        assert data["hooks"]["PreToolUse"][0]["matcher"] == shipped
        assert "PreToolUse" in updated
        assert "PreToolUse" not in added
        # Still no duplicate rule for the same subcommand.
        assert len(data["hooks"]["PreToolUse"]) == 1

    def test_mixed_rule_matcher_is_not_converged(self):
        """A user who hand-merged their own hook into our rule keeps their
        trigger: the rule-level matcher is only converged when every hook in
        the rule is ours (their command string was already never touched)."""
        from jcodemunch_mcp.cli.init import _enforcement_hooks, _merge_hooks

        data = {"hooks": {"PreToolUse": [{
            "matcher": "Read",
            "hooks": [
                {"type": "command", "command": "jcodemunch-mcp hook-pretooluse"},
                {"type": "command", "command": "/home/u/my-guard.sh"},
            ],
        }]}}
        _merge_hooks(data, _enforcement_hooks(), "jcodemunch-mcp hook-p")
        rule = data["hooks"]["PreToolUse"][0]
        assert rule["matcher"] == "Read"  # user's trigger untouched
        # Our command inside the mixed rule still converges to absolute form.
        from jcodemunch_mcp.cli.init import _extract_jcm_subcommand
        jcm_cmds = [h["command"] for h in rule["hooks"]
                    if _extract_jcm_subcommand(h["command"])]
        assert jcm_cmds and all("hook-pretooluse" in c for c in jcm_cmds)
        assert rule["hooks"][1]["command"] == "/home/u/my-guard.sh"

    def test_current_matcher_untouched_and_idempotent(self):
        from jcodemunch_mcp.cli.init import _enforcement_hooks, _merge_hooks

        data: dict = {}
        _merge_hooks(data, _enforcement_hooks(), "jcodemunch-mcp hook-p")
        again = _merge_hooks(data, _enforcement_hooks(), "jcodemunch-mcp hook-p")
        assert again == ([], [])  # nothing added, nothing updated → no rewrite
