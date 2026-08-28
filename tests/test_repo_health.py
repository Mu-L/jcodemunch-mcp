"""Tests for get_repo_health tool."""

import pytest

from jcodemunch_mcp.tools.get_repo_health import (
    _count_unstable_modules,
    _is_production_path,
    get_repo_health,
)
from jcodemunch_mcp.tools.index_folder import index_folder


def _build_repo(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    store = tmp_path / "store"
    store.mkdir()

    (src / "main.py").write_text(
        "from utils import helper\n\ndef main():\n    helper()\n"
    )
    (src / "utils.py").write_text(
        "def helper():\n    return 1\n\n"
        "def dead_fn():\n    pass\n"
    )
    r = index_folder(str(src), use_ai_summaries=False, storage_path=str(store))
    assert r["success"] is True
    return r["repo"], str(store)


class TestGetRepoHealth:
    def test_returns_required_fields(self, tmp_path):
        repo, store = _build_repo(tmp_path)
        result = get_repo_health(repo=repo, storage_path=store)
        assert "summary" in result
        assert "total_files" in result
        assert "total_symbols" in result
        assert "avg_complexity" in result
        assert "dead_code_pct" in result
        assert "dead_count" in result
        assert "cycle_count" in result
        assert "cycles_sample" in result
        assert "unstable_modules" in result
        assert "top_hotspots" in result
        assert "_meta" in result

    def test_summary_is_string(self, tmp_path):
        repo, store = _build_repo(tmp_path)
        result = get_repo_health(repo=repo, storage_path=store)
        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 0

    def test_counts_are_non_negative(self, tmp_path):
        repo, store = _build_repo(tmp_path)
        result = get_repo_health(repo=repo, storage_path=store)
        assert result["total_files"] >= 0
        assert result["total_symbols"] >= 0
        assert result["cycle_count"] >= 0
        assert result["dead_count"] >= 0
        assert result["unstable_modules"] >= 0

    def test_dead_code_pct_range(self, tmp_path):
        repo, store = _build_repo(tmp_path)
        result = get_repo_health(repo=repo, storage_path=store)
        assert 0.0 <= result["dead_code_pct"] <= 100.0

    def test_top_hotspots_is_list(self, tmp_path):
        repo, store = _build_repo(tmp_path)
        result = get_repo_health(repo=repo, storage_path=store)
        assert isinstance(result["top_hotspots"], list)
        assert len(result["top_hotspots"]) <= 5

    def test_cycles_sample_is_list(self, tmp_path):
        repo, store = _build_repo(tmp_path)
        result = get_repo_health(repo=repo, storage_path=store)
        assert isinstance(result["cycles_sample"], list)

    def test_timing_present(self, tmp_path):
        repo, store = _build_repo(tmp_path)
        result = get_repo_health(repo=repo, storage_path=store)
        assert "timing_ms" in result["_meta"]

    def test_missing_repo_returns_error(self, tmp_path):
        result = get_repo_health(repo="no_such_repo", storage_path=str(tmp_path))
        assert "error" in result

    def test_repo_field_present(self, tmp_path):
        repo, store = _build_repo(tmp_path)
        result = get_repo_health(repo=repo, storage_path=store)
        assert "repo" in result
        assert "/" in result["repo"]

    def test_fn_method_count_present(self, tmp_path):
        repo, store = _build_repo(tmp_path)
        result = get_repo_health(repo=repo, storage_path=store)
        assert "fn_method_count" in result
        assert result["fn_method_count"] >= 0

    def test_no_nameerror_when_decorators_present(self, tmp_path):
        """Regression: v1.73.1 raised NameError on _ENTRY_POINT_DECORATOR_RE
        when any symbol carried a decorator. Fixture must trigger the
        decorator-skip branch in dead-code analysis."""
        src = tmp_path / "src"
        src.mkdir()
        store = tmp_path / "store"
        store.mkdir()
        (src / "app.py").write_text(
            "from flask import Flask\n"
            "app = Flask(__name__)\n\n"
            "@app.route('/health')\n"
            "def health():\n    return 'ok'\n\n"
            "@app.route('/items')\n"
            "def items():\n    return []\n"
        )
        r = index_folder(str(src), use_ai_summaries=False, storage_path=str(store))
        assert r["success"] is True
        result = get_repo_health(repo=r["repo"], storage_path=str(store))
        assert "error" not in result, result
        assert "summary" in result


class TestProductionPathFilter:
    """v1.91.0: coupling axis excludes tests/benchmarks/scripts/examples
    from both numerator and denominator. Test files are guaranteed to look
    unstable (Ca=0) and would dominate the metric for any well-tested
    project — counting them confused the axis into reporting "coupling=4"
    on otherwise-healthy codebases."""

    @pytest.mark.parametrize("path", [
        "src/foo/bar.py",
        "jcodemunch_mcp/tools/get_repo_health.py",
        "lib/utils.py",
        "src/tools/test_summarizer.py",  # tool file with "test_" prefix — keep
        "vscode-extension/src/extension.ts",
        # Filename-suffix near-misses that should NOT be filtered:
        "pkg/foo/protest.go",            # contains "test" but no _test.go suffix
        "src/manifest.ts",               # no .spec/.test infix
        "src/Foo.java",                  # no Test suffix
        "src/foo_specifications.rb",     # _spec is part of word, not the suffix
    ])
    def test_production_paths_kept(self, path):
        assert _is_production_path(path) is True

    @pytest.mark.parametrize("path", [
        "tests/test_foo.py",
        "test/conftest.py",
        "benchmarks/harness/run.py",
        "scripts/migrate.py",
        "examples/demo.py",
        "src/foo/tests/test_bar.py",  # nested tests dir
        "tests\\test_foo.py",          # windows separators
        # v1.92.0: filename-suffix conventions across ecosystems.
        "pkg/foo/foo_test.go",                 # Go
        "src/app/foo.service.spec.ts",         # Angular/NestJS
        "src/app/foo.service.spec.tsx",        # TSX spec
        "src/app/foo.test.ts",                 # Jest TS
        "src/app/foo.test.tsx",                # Jest TSX
        "src/app/foo.test.js",                 # Jest JS
        "src/app/foo.test.jsx",                # Jest JSX
        "src/app/foo.spec.js",                 # Jasmine/Karma JS
        "src/app/foo.spec.jsx",                # Jasmine/Karma JSX
        "spec/models/user_spec.rb",            # RSpec
        "src/com/example/FooTest.java",        # JUnit
        "src/app/Foo.SPEC.TS",                 # case-insensitive
    ])
    def test_non_production_paths_excluded(self, path):
        assert _is_production_path(path) is False


class TestCountUnstableModules:
    """Regression: v1.90.x counted test files as unstable, dominating the
    coupling axis. v1.91.0 returns (unstable, production_total) and excludes
    leaf-script directories from both."""

    def _index_with_layout(self, tmp_path, files: dict[str, str]):
        src = tmp_path / "src"
        src.mkdir()
        store = tmp_path / "store"
        store.mkdir()
        for rel, content in files.items():
            f = src / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(content)
        r = index_folder(str(src), use_ai_summaries=False, storage_path=str(store))
        assert r["success"] is True
        from jcodemunch_mcp.storage import IndexStore
        owner, name = r["repo"].split("/", 1)
        return IndexStore(base_path=str(store)).load_index(owner, name)

    def test_excludes_tests_from_both_numerator_and_denominator(self, tmp_path):
        # Layout: 1 production file (lib.py, imported by main.py),
        # 1 production entrypoint (main.py, no inbound), 3 test files
        # (each imports lib, no inbound). Pre-fix: 4 unstable / 5 total.
        # Post-fix: 1 unstable / 2 production_total.
        idx = self._index_with_layout(tmp_path, {
            "lib.py":              "def helper(): return 1\n",
            "main.py":             "from lib import helper\nhelper()\n",
            "tests/test_a.py":     "from lib import helper\ndef test_a(): assert helper()\n",
            "tests/test_b.py":     "from lib import helper\ndef test_b(): assert helper()\n",
            "tests/test_c.py":     "from lib import helper\ndef test_c(): assert helper()\n",
        })
        unstable, production_total, excluded, profile = _count_unstable_modules(idx)
        # No framework detected on a bare two-file layout, so nothing is
        # excluded on that ground and the test/denominator property below is
        # measured exactly as before (#561 widened the return, not the rule).
        assert (excluded, profile) == (0, None)
        assert production_total == 2, f"expected 2 production files, got {production_total}"
        # main.py has Ca=0, Ce=1 → instability=1.0 → unstable. lib.py has
        # Ca>=1 (main + tests credit it), Ce=0 → stable.
        assert unstable == 1, f"expected 1 unstable production file, got {unstable}"

    def test_returns_pair_for_empty_index(self, tmp_path):
        from types import SimpleNamespace
        empty = SimpleNamespace(imports=[], source_files=[])
        assert _count_unstable_modules(empty) == (0, 0, 0, None)
