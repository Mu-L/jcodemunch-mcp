"""`install-status` reports whether the RUNNING code matches its own tree.

⚠⚠ **Measured 2026-08-29: this box ran 1.108.293 against a 1.108.307 tree --
fourteen releases and six days.** We develop jcodemunch using jcodemunch, so
every tool call in that window exercised six-day-old code. It happened because
the package was installed as a regular (copied) distribution and **the release
checklist's eight steps never touch the dev box**.

⚠⚠ **`verify_package_integrity()` cannot see this and is not meant to.** It asks
whether the running module belongs to the OFFICIAL distribution -- a
supply-chain question -- and would certify a fourteen-release-old official
install without complaint. **Ownership and freshness are different properties**,
and having a check that inspects the distribution made it feel covered.

⚠ The tell was subtler than the version gap: with the dogfood that stale, every
fix that week was verified with `PYTHONPATH=src` rather than through the server.
The verification path routed AROUND the product without anyone deciding to.
"""

from __future__ import annotations

import pytest

from jcodemunch_mcp.cli import init as _init


@pytest.fixture
def tree(tmp_path):
    """A source layout: <root>/src/jcodemunch_mcp/__init__.py + pyproject."""
    pkg = tmp_path / "src" / "jcodemunch_mcp"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    return tmp_path, str(pkg / "__init__.py")


def _drift(monkeypatch, *, running, module_file, pyproject_text=None, root=None):
    monkeypatch.setattr(_init, "_module_file_of", lambda name: module_file)
    monkeypatch.setattr("jcodemunch_mcp.__version__", running, raising=False)
    if pyproject_text is not None and root is not None:
        (root / "pyproject.toml").write_text(pyproject_text, encoding="utf-8")
    return _init._running_source_drift()


class TestTheDefectThatHappened:

    def test_a_stale_install_is_reported(self, tree, monkeypatch):
        """The real 2026-08-29 state: running .293 from a .307 tree."""
        root, modfile = tree
        out = _drift(monkeypatch, running="1.108.293", module_file=modfile,
                     pyproject_text='version = "1.108.307"\n', root=root)
        assert out["drifted"] is True
        assert out["running_version"] == "1.108.293"
        assert out["tree_version"] == "1.108.307"
        assert "restart" in (out["reason"] or "").lower(), out["reason"]

    def test_a_matching_tree_is_not_drifted(self, tree, monkeypatch):
        """Non-vacuity: without this, 'always report drift' passes above."""
        root, modfile = tree
        out = _drift(monkeypatch, running="1.108.307", module_file=modfile,
                     pyproject_text='version = "1.108.307"\n', root=root)
        assert out["drifted"] is False
        assert out["editable"] is True


class TestUnknownIsNeverFalse:
    """⚠⚠ `drifted: None` means COULD NOT ESTABLISH. Reporting `False` for a
    comparison that was never made is the defect this project keeps finding in
    its own instruments -- the .305 churn axis, the .306 test axis, the dead-code
    refusal published as a zero."""

    def test_unknown_running_version_does_not_claim_fresh(self, tree, monkeypatch):
        """`__version__` is "unknown" under PYTHONPATH=src, which is how the
        whole test suite and CI run. That must not read as 'not drifted'."""
        _root, modfile = tree
        out = _drift(monkeypatch, running="unknown", module_file=modfile)
        assert out["drifted"] is None
        assert out["reason"]

    def test_an_installed_copy_is_unknown_not_fresh(self, tmp_path, monkeypatch):
        """site-packages has no pyproject.toml above it -- nothing to compare."""
        pkg = tmp_path / "site-packages" / "jcodemunch_mcp"
        pkg.mkdir(parents=True)
        out = _drift(monkeypatch, running="1.108.293",
                     module_file=str(pkg / "__init__.py"))
        assert out["drifted"] is None
        assert out["editable"] is False

    def test_an_unreadable_pyproject_is_unknown(self, tree, monkeypatch):
        root, modfile = tree
        out = _drift(monkeypatch, running="1.108.307", module_file=modfile,
                     pyproject_text="[project]\nname = 'x'\n", root=root)
        assert out["drifted"] is None
        assert "version" in (out["reason"] or "")

    def test_a_missing_module_is_unknown(self, monkeypatch):
        def _boom(_name):
            raise ImportError("no such module")
        monkeypatch.setattr(_init, "_module_file_of", _boom)
        monkeypatch.setattr("jcodemunch_mcp.__version__", "1.108.307", raising=False)
        out = _init._running_source_drift()
        assert out["drifted"] is None


class TestItReachesTheReport:

    def test_install_status_carries_the_block(self):
        """⚠ Verify at the entry point: a helper nobody calls is the shape of
        `entry_point_patterns`, written in one place and read in none."""
        report = _init.install_status()
        assert "source_drift" in report
        assert set(report["source_drift"]) >= {
            "running_version", "tree_version", "editable", "drifted", "reason",
        }

    @staticmethod
    def _report_with(drift: dict) -> dict:
        """⚠ Build on a REAL report rather than a hand-written stub. An earlier
        version of these two tests passed `hooks: {}` and died on
        `report["hooks"]["claude_settings"]` -- a fabricated shape that does not
        match the producer, which is the same defect class as #559's mocks."""
        report = _init.install_status()
        report["source_drift"] = drift
        return report

    def test_the_renderer_says_stale_when_it_is(self, capsys):
        _init.print_status(self._report_with({
            "running_version": "1.108.293", "tree_version": "1.108.307",
            "tree_path": "C:/x", "editable": True, "drifted": True,
            "reason": "reinstall and RESTART the MCP clients",
        }))
        out = capsys.readouterr().out
        assert "STALE" in out and "1.108.293" in out and "1.108.307" in out

    def test_the_renderer_shows_unknown_rather_than_silence(self, capsys):
        """⚠ An UNKNOWN that prints nothing is indistinguishable from fresh."""
        _init.print_status(self._report_with({
            "running_version": "unknown", "tree_version": None,
            "tree_path": None, "editable": None, "drifted": None,
            "reason": "running version is unknown",
        }))
        assert "unknown" in capsys.readouterr().out

    def test_a_fresh_install_prints_no_drift_noise(self, capsys):
        """Non-vacuity for the two above: the block must be SILENT when fresh,
        or 'always print something' would satisfy them."""
        _init.print_status(self._report_with({
            "running_version": "1.108.307", "tree_version": "1.108.307",
            "tree_path": "C:/x", "editable": True, "drifted": False,
            "reason": None,
        }))
        out = capsys.readouterr().out
        assert "STALE" not in out and "Running code:" not in out
