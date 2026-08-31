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

import pathlib

import pytest

from jcodemunch_mcp.cli import init as _init


@pytest.fixture
def tree(tmp_path):
    """A source layout: <root>/src/jcodemunch_mcp/__init__.py + pyproject."""
    pkg = tmp_path / "src" / "jcodemunch_mcp"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    return tmp_path, str(pkg / "__init__.py")


def _drift(monkeypatch, *, running, module_file, pyproject_text=None, root=None,
           recorded=None):
    """Drive `_running_source_drift` with every environment input pinned.

    ⚠⚠ `recorded` is ALWAYS patched, defaulting to None. `_recorded_source_dir`
    reads the REAL installed distribution's `direct_url.json` (PEP 610), so a
    test that leaves it alone inherits whatever this machine happens to have
    installed. That is not hypothetical: it shipped red for exactly one release
    candidate. Under `PYTHONPATH=src` there is no jcodemunch distribution at
    all, so it returned None and every test passed; under
    `uv run --python 3.13` the project IS installed editable, so it resolved to
    the real tree and a fake copied-install fixture suddenly had something to
    compare against -- `drifted: True` where the test demanded None.

    ⚠ Practice 8's family: a test reading real machine state, green on one
    interpreter and red on another for a reason neither run could show on its
    own. Pin the input at the helper so no test can forget.
    """
    monkeypatch.setattr(_init, "_module_file_of", lambda name: module_file)
    monkeypatch.setattr("jcodemunch_mcp.__version__", running, raising=False)
    monkeypatch.setattr(_init, "_recorded_source_dir", lambda: recorded)
    if pyproject_text is not None and root is not None:
        (root / "pyproject.toml").write_text(pyproject_text, encoding="utf-8")
    return _init._running_source_drift()


class TestTheDefectThatHappened:
    """⚠⚠ Rewritten 2026-08-31 (Practice 9): the original
    `test_a_stale_install_is_reported` claimed to reproduce the 2026-08-29 state
    but built a SOURCE TREE fixture, while the incident was a **regular copied
    install** -- this file's own opening docstring says so. It asserted
    `drifted is True` for the one configuration where code CANNOT go stale, so
    it could only pass while the conflation existed. The test stated the
    mechanism; the property is "does a version gap mean a CODE gap here?"
    """

    def test_a_stale_copied_install_is_reported(self, tree, tmp_path, monkeypatch):
        """The real 2026-08-29 shape: a COPY in site-packages, 14 releases old.

        The copy is only as new as its last install, so here the version gap IS
        a code gap. ⚠ Before the fix this returned UNKNOWN -- the check could
        not see the very incident it was written for.
        """
        root, _modfile = tree
        (root / "pyproject.toml").write_text('version = "1.108.307"\n', encoding="utf-8")
        copied = tmp_path / "site-packages" / "jcodemunch_mcp"
        copied.mkdir(parents=True)
        out = _drift(monkeypatch, running="1.108.293",
                     module_file=str(copied / "__init__.py"), recorded=root)
        assert out["drifted"] is True
        assert out["editable"] is False
        assert out["running_version"] == "1.108.293"
        assert out["tree_version"] == "1.108.307"
        assert "restart" in (out["reason"] or "").lower(), out["reason"]

    def test_a_copied_install_that_matches_is_not_drifted(self, tree, tmp_path, monkeypatch):
        """Non-vacuity: without this, 'always report drift' passes above."""
        root, _modfile = tree
        (root / "pyproject.toml").write_text('version = "1.108.307"\n', encoding="utf-8")
        copied = tmp_path / "site-packages" / "jcodemunch_mcp"
        copied.mkdir(parents=True)
        out = _drift(monkeypatch, running="1.108.307",
                     module_file=str(copied / "__init__.py"), recorded=root)
        assert out["drifted"] is False
        assert out["metadata_stale"] is False


class TestEditableCodeCannotGoStale:
    """⚠⚠ `__version__` is `importlib.metadata`, frozen in `.dist-info` at
    install time. An editable install imports straight from the tree, so a NEW
    process always loads current code -- while the version comparison differs
    after every bump. Reporting that as STALE fired forever, under a remedy
    (`pip install -e .`) that does not change which code runs, and this is the
    check written to stop a fourteen-release drift going unnoticed.
    """

    def test_a_version_gap_on_editable_is_metadata_not_code(self, tree, monkeypatch):
        root, modfile = tree
        out = _drift(monkeypatch, running="1.108.309", module_file=modfile,
                     pyproject_text='version = "1.108.312"\n', root=root)
        assert out["editable"] is True
        assert out["drifted"] is False, "the module IS the tree; code cannot lag"
        assert out["metadata_stale"] is True

    def test_the_reason_names_serverinfo_and_keeps_the_restart_advice(self, tree, monkeypatch):
        """⚠ `server = Server("jcodemunch-mcp", version=__version__)`, so a stale
        number is what the MCP host is handed -- that is the real consequence
        and it must be named. ⚠⚠ RESTART stays: a long-running server holds the
        code it loaded at startup, which is the one way editable code goes
        stale. Only the `reinstall` claim was wrong.
        """
        root, modfile = tree
        out = _drift(monkeypatch, running="1.108.309", module_file=modfile,
                     pyproject_text='version = "1.108.312"\n', root=root)
        reason = out["reason"] or ""
        assert "serverInfo" in reason
        assert "RESTART" in reason
        assert "does not change which code runs" in reason
        assert "STALE" not in reason

    def test_a_matching_editable_install_is_silent(self, tree, monkeypatch):
        """Non-vacuity: nothing to say when nothing is behind."""
        root, modfile = tree
        out = _drift(monkeypatch, running="1.108.307", module_file=modfile,
                     pyproject_text='version = "1.108.307"\n', root=root)
        assert out["drifted"] is False
        assert out["metadata_stale"] is False
        assert out["reason"] is None

    def test_the_verdict_is_not_computed_from_source_timestamps(self, tree, monkeypatch):
        """Pins what this check does NOT claim.

        Touching a source file must not move the verdict -- it reads versions,
        not mtimes. Recorded so nobody reads `drifted: False` as "no edits since
        this process started"; that question belongs to the process registry,
        which has start times.
        """
        root, modfile = tree
        kw = dict(running="1.108.309", module_file=modfile,
                  pyproject_text='version = "1.108.312"\n', root=root)
        before = _drift(monkeypatch, **kw)
        pathlib.Path(modfile).touch()
        assert _drift(monkeypatch, **kw) == before


class TestRecordedSourceDir:

    def test_a_pypi_wheel_has_no_tree_and_stays_unknown(self, tmp_path, monkeypatch):
        """⚠ A wheel off PyPI has no local directory. Inventing one would
        manufacture a comparison; "newer than the tree" is not a question that
        exists for it."""
        copied = tmp_path / "site-packages" / "jcodemunch_mcp"
        copied.mkdir(parents=True)
        out = _drift(monkeypatch, running="1.108.293",
                     module_file=str(copied / "__init__.py"))
        assert out["drifted"] is None
        assert out["editable"] is False


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
        """A copy with NO recorded source directory -- nothing to compare.

        ⚠ "Installed copy" alone no longer implies UNKNOWN: a copy that records
        where it was installed FROM is comparable, which is the whole point of
        the fix. The discriminator is the recorded directory, so this test names
        it rather than leaving it to the machine.
        """
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
