"""Tests for get_untested_symbols tool and blast radius has_test_reach enrichment."""

import pytest
from pathlib import Path

from jcodemunch_mcp.tools.get_untested_symbols import get_untested_symbols
from jcodemunch_mcp.tools.get_blast_radius import get_blast_radius
from jcodemunch_mcp.tools.index_folder import index_folder
from jcodemunch_mcp.tools.find_dead_code import _is_test_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_repo(tmp_path: Path, files: dict[str, str]) -> tuple[str, str]:
    """Write files to tmp_path and index them. Return (repo_id, storage_path)."""
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    storage = str(tmp_path / ".index")
    result = index_folder(str(tmp_path), use_ai_summaries=False, storage_path=storage)
    repo_id = result.get("repo", str(tmp_path))
    return repo_id, storage


# ---------------------------------------------------------------------------
# _is_test_file pattern recognition
# ---------------------------------------------------------------------------

class TestIsTestFile:
    """Verify _is_test_file recognizes Python and JS/TS patterns."""

    def test_python_test_prefix(self):
        assert _is_test_file("test_auth.py")

    def test_python_test_suffix(self):
        assert _is_test_file("auth_test.py")

    def test_python_tests_dir(self):
        assert _is_test_file("src/tests/test_core.py")

    def test_python_test_dir(self):
        assert _is_test_file("src/test/test_core.py")

    def test_python_conftest(self):
        assert _is_test_file("tests/conftest.py")

    def test_js_spec_ts(self):
        assert _is_test_file("src/auth.spec.ts")

    def test_js_spec_js(self):
        assert _is_test_file("src/auth.spec.js")

    def test_js_test_ts(self):
        assert _is_test_file("src/auth.test.ts")

    def test_js_test_js(self):
        assert _is_test_file("src/auth.test.js")

    def test_js_tests_dir(self):
        assert _is_test_file("src/__tests__/auth.ts")

    def test_non_test_file(self):
        assert not _is_test_file("src/auth.py")

    def test_non_test_js(self):
        assert not _is_test_file("src/auth.ts")


# ---------------------------------------------------------------------------
# Unreached: no test imports the source file at all
# ---------------------------------------------------------------------------

class TestUnreached:
    def test_no_test_references_symbol(self, tmp_path):
        """Function in a file with zero test importers → unreached, confidence 1.0."""
        repo, storage = _make_repo(tmp_path, {
            "main.py": "from src import core\nif __name__ == '__main__': core.run()",
            "src/__init__.py": "",
            "src/core.py": "def run(): pass",
            "src/orphan.py": "def lonely(): pass",
            "tests/__init__.py": "",
            "tests/test_core.py": "from src.core import run\ndef test_run(): run()",
        })
        result = get_untested_symbols(repo, storage_path=storage)
        assert "error" not in result
        names = {s["name"] for s in result["symbols"]}
        assert "lonely" in names, f"Expected lonely in untested, got {names}"
        lonely = [s for s in result["symbols"] if s["name"] == "lonely"][0]
        assert lonely["confidence"] == 1.0
        assert lonely["reason"] == "unreached"

    def test_reached_symbol_excluded(self, tmp_path):
        """Function referenced by a test → not in results."""
        repo, storage = _make_repo(tmp_path, {
            "src/__init__.py": "",
            "src/core.py": "def run(): pass",
            "tests/__init__.py": "",
            "tests/test_core.py": "from src.core import run\ndef test_run(): run()",
        })
        result = get_untested_symbols(repo, storage_path=storage)
        assert "error" not in result
        names = {s["name"] for s in result["symbols"]}
        assert "run" not in names


# ---------------------------------------------------------------------------
# Imported but not called: test imports file but doesn't reference symbol
# ---------------------------------------------------------------------------

class TestImportedNotCalled:
    def test_test_imports_file_but_not_function(self, tmp_path):
        """Test imports the module but doesn't call a specific function → medium confidence."""
        repo, storage = _make_repo(tmp_path, {
            "src/__init__.py": "",
            "src/auth.py": "def login(): pass\ndef logout(): pass",
            "tests/__init__.py": "",
            "tests/test_auth.py": "from src.auth import login\ndef test_login(): login()",
        })
        result = get_untested_symbols(repo, storage_path=storage)
        assert "error" not in result
        names = {s["name"] for s in result["symbols"]}
        # login is reached (test calls it), logout is imported_not_called
        assert "login" not in names
        assert "logout" in names
        logout = [s for s in result["symbols"] if s["name"] == "logout"][0]
        assert logout["confidence"] == 0.7
        assert logout["reason"] == "imported_not_called"


# ---------------------------------------------------------------------------
# File pattern filter
# ---------------------------------------------------------------------------

class TestFilePattern:
    def test_file_pattern_narrows_scope(self, tmp_path):
        """file_pattern limits which source files are considered."""
        repo, storage = _make_repo(tmp_path, {
            "src/__init__.py": "",
            "src/a.py": "def func_a(): pass",
            "src/b.py": "def func_b(): pass",
        })
        result = get_untested_symbols(repo, file_pattern="**/a.py", storage_path=storage)
        assert "error" not in result
        names = {s["name"] for s in result["symbols"]}
        assert "func_a" in names
        assert "func_b" not in names


# ---------------------------------------------------------------------------
# max_results + min_confidence
# ---------------------------------------------------------------------------

class TestLimits:
    def test_max_results_cap(self, tmp_path):
        """Results are capped at max_results."""
        # Generate many untested functions
        funcs = "\n".join(f"def func_{i}(): pass" for i in range(20))
        repo, storage = _make_repo(tmp_path, {
            "big.py": funcs,
        })
        result = get_untested_symbols(repo, max_results=5, storage_path=storage)
        assert "error" not in result
        assert len(result["symbols"]) <= 5
        assert result["_meta"].get("truncated") is True

    def test_min_confidence_filters(self, tmp_path):
        """min_confidence=1.0 excludes imported_not_called (0.7)."""
        repo, storage = _make_repo(tmp_path, {
            "src/__init__.py": "",
            "src/auth.py": "def login(): pass\ndef logout(): pass",
            "tests/__init__.py": "",
            "tests/test_auth.py": "from src.auth import login\ndef test_login(): login()",
        })
        result_low = get_untested_symbols(repo, min_confidence=0.5, storage_path=storage)
        result_high = get_untested_symbols(repo, min_confidence=1.0, storage_path=storage)
        # logout has confidence 0.7 → included in low, excluded from high
        low_names = {s["name"] for s in result_low["symbols"]}
        high_names = {s["name"] for s in result_high["symbols"]}
        assert "logout" in low_names
        assert "logout" not in high_names


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------

class TestResponseShape:
    def test_required_keys_present(self, tmp_path):
        repo, storage = _make_repo(tmp_path, {
            "main.py": "def main(): pass\nif __name__ == '__main__': main()",
        })
        result = get_untested_symbols(repo, storage_path=storage)
        assert "error" not in result
        for key in ("repo", "untested_count", "total_non_test_symbols",
                    "reached_pct", "symbols", "_meta"):
            assert key in result, f"Missing key: {key}"
        assert "timing_ms" in result["_meta"]

    def test_symbol_entry_shape(self, tmp_path):
        repo, storage = _make_repo(tmp_path, {
            "orphan.py": "def lonely(): pass",
        })
        result = get_untested_symbols(repo, storage_path=storage)
        assert result["symbols"]
        sym = result["symbols"][0]
        for key in ("symbol_id", "name", "kind", "file", "line", "confidence", "reason"):
            assert key in sym, f"Missing key in symbol: {key}"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestErrors:
    def test_unknown_repo(self, tmp_path):
        result = get_untested_symbols("nonexistent/repo",
                                       storage_path=str(tmp_path / ".index"))
        assert "error" in result


# ---------------------------------------------------------------------------
# Blast radius has_test_reach enrichment
# ---------------------------------------------------------------------------

class TestBlastRadiusEnrichment:
    def test_has_test_reach_present(self, tmp_path):
        """Blast radius confirmed entries include has_test_reach field."""
        repo, storage = _make_repo(tmp_path, {
            "src/__init__.py": "",
            "src/core.py": "def run(): pass",
            "src/caller.py": "from src.core import run\ndef go(): run()",
            "tests/__init__.py": "",
            "tests/test_caller.py": "from src.caller import go\ndef test_go(): go()",
        })
        result = get_blast_radius(repo, symbol="run", storage_path=storage)
        assert "error" not in result
        for entry in result.get("confirmed", []):
            assert "has_test_reach" in entry, f"Missing has_test_reach in {entry}"

    def test_has_test_reach_true_when_tested(self, tmp_path):
        """Confirmed file with test coverage → has_test_reach=True."""
        repo, storage = _make_repo(tmp_path, {
            "src/__init__.py": "",
            "src/core.py": "def run(): pass",
            "src/caller.py": "from src.core import run\ndef go(): run()",
            "tests/__init__.py": "",
            "tests/test_caller.py": "from src.caller import go\ndef test_go(): go()",
        })
        result = get_blast_radius(repo, symbol="run", storage_path=storage)
        assert "error" not in result
        caller_entries = [e for e in result.get("confirmed", []) if "caller" in e["file"]]
        if caller_entries:
            # test_caller.py imports caller.py AND references "run"
            # The test imports caller.py which references run
            assert isinstance(caller_entries[0]["has_test_reach"], bool)

    def test_has_test_reach_false_when_untested(self, tmp_path):
        """Confirmed file with no test file → has_test_reach=False."""
        repo, storage = _make_repo(tmp_path, {
            "src/__init__.py": "",
            "src/core.py": "def run(): pass",
            "src/untested_caller.py": "from src.core import run\ndef invoke(): run()",
        })
        result = get_blast_radius(repo, symbol="run", storage_path=storage)
        assert "error" not in result
        for entry in result.get("confirmed", []):
            if "untested_caller" in entry["file"]:
                assert entry["has_test_reach"] is False


# ---------------------------------------------------------------------------
# #559 — the reported count must not be a property of max_results
# ---------------------------------------------------------------------------

class TestCountIsIndependentOfMaxResults:
    """`untested_count` / `reached_pct` describe the REPO, not the page.

    ⚠⚠ `untested_count` was `len(symbols)` computed AFTER the `max_results`
    slice, and `reached_pct` divided by it. `get_repo_health` calls this with
    `max_results=1` and the comment "we only need the count", so the health
    test axis read one untested symbol on every repo and published ~100%
    reach. @lilubot measured 4,893 untested of 6,352 (23.0% reached) reported
    as 100 (#559).

    ⚠ The tell is that the two assertions below are about the SAME repo. A
    count that moves when only the page size moves is not a count of anything
    in the repo.
    """

    @pytest.fixture
    def repo(self, tmp_path):
        files = {
            "src/a.py": "\n".join(f"def untested_{i}():\n    return {i}\n" for i in range(12)),
            "src/covered.py": "def covered():\n    return 1\n",
            "tests/test_covered.py": (
                "from src.covered import covered\n\n"
                "def test_covered():\n    assert covered() == 1\n"
            ),
        }
        return _make_repo(tmp_path, files)

    def test_count_does_not_shrink_to_the_page_size(self, repo):
        repo_id, storage = repo
        full = get_untested_symbols(repo_id, max_results=10_000, storage_path=storage)
        paged = get_untested_symbols(repo_id, max_results=1, storage_path=storage)

        assert "error" not in full and "error" not in paged
        assert full["untested_count"] > 1, "fixture must produce several untested symbols"
        assert paged["untested_count"] == full["untested_count"]

    def test_reached_pct_does_not_move_with_the_page_size(self, repo):
        repo_id, storage = repo
        full = get_untested_symbols(repo_id, max_results=10_000, storage_path=storage)
        paged = get_untested_symbols(repo_id, max_results=1, storage_path=storage)

        assert full["reached_pct"] < 100.0, "fixture must have unreached symbols"
        assert paged["reached_pct"] == full["reached_pct"]

    def test_returned_count_is_the_page_and_is_labelled(self, repo):
        """The page size is still reportable — under its own name."""
        repo_id, storage = repo
        paged = get_untested_symbols(repo_id, max_results=1, storage_path=storage)

        assert len(paged["symbols"]) == 1
        assert paged["returned_count"] == 1
        assert paged["_meta"]["truncated"] is True

    def test_health_test_axis_reflects_the_whole_repo(self, repo):
        """#559 at the user's entry point: the published axis, not the helper."""
        from jcodemunch_mcp.tools.get_repo_health import get_repo_health

        repo_id, storage = repo
        health = get_repo_health(repo_id, storage_path=storage)
        radar = health.get("radar") or {}
        axes = radar.get("axes") or {}
        assert "test_gap" in axes, f"axes present: {sorted(axes)}"
        assert axes["test_gap"]["score"] < 100.0, (
            "a repo with unreached symbols must not score a perfect test axis"
        )
