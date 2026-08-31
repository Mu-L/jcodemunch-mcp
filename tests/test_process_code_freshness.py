"""A process registry's `version` cannot answer "is this old server running old code?"

⚠⚠ `version` is the RECORDED metadata number, frozen in `.dist-info` at install
time. On a source/editable install every live process reports the SAME string no
matter when it started -- so the one question an operator brings to a process
registry was unanswerable from the row, while a field that looked like it
answered it sat right there.

A start timestamp can answer it; a version string never could. Third reader of
the same conflation, after the drift verdict and the install-status renderer.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from jcodemunch_mcp import install_layout
from jcodemunch_mcp.storage.process_registry import ProcessEntry, sprawl_report


def _entry(started: datetime, *, pid: int = 111, version: str = "1.108.309") -> ProcessEntry:
    return ProcessEntry(
        pid=pid,
        client_id="claude",
        transport="stdio",
        version=version,
        started_at=started.isoformat(),
        create_time=1.0,
    )


NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


# --- the question `version` could not answer -------------------------------- #


def test_source_newer_than_the_process_is_stale_code():
    e = _entry(NOW)
    changed = (NOW + timedelta(minutes=5)).timestamp()
    assert e.code_stale(changed) is True


def test_source_older_than_the_process_is_current_code():
    """Non-vacuity: without this, 'always stale' passes above."""
    e = _entry(NOW)
    changed = (NOW - timedelta(minutes=5)).timestamp()
    assert e.code_stale(changed) is False


def test_identical_versions_get_different_verdicts():
    """⚠⚠ THE test. This is the defect stated as a property.

    Two processes reporting the SAME `version` -- which is what every process on
    a source install reports -- must be graded differently when one started
    before the last source change and one after. If the verdict ever tracks
    `version`, this fails.
    """
    changed = NOW.timestamp()
    old = _entry(NOW - timedelta(hours=1), pid=1, version="1.108.309")
    new = _entry(NOW + timedelta(hours=1), pid=2, version="1.108.309")
    assert old.version == new.version
    assert old.code_stale(changed) is True
    assert new.code_stale(changed) is False


# --- UNKNOWN is never False -------------------------------------------------- #


def test_a_copied_install_cannot_establish_freshness():
    """⚠ The tree's mtimes say nothing about what a COPY loaded, so the question
    is unanswerable rather than answerable-as-fresh."""
    assert _entry(NOW).code_stale(None) is None


@pytest.mark.parametrize("started", ["", "not-a-date", "2026-13-45"])
def test_an_unparseable_start_time_is_unknown(started):
    e = ProcessEntry(
        pid=1, client_id="c", transport="stdio", version="1.1", started_at=started
    )
    assert e.code_stale(NOW.timestamp()) is None


def test_a_naive_start_time_is_read_as_utc_not_rejected():
    """Rows written by older versions may lack an offset; they are still usable."""
    e = ProcessEntry(
        pid=1, client_id="c", transport="stdio", version="1.1",
        started_at="2026-08-31T12:00:00",
    )
    assert e.code_stale((NOW + timedelta(minutes=1)).timestamp()) is True


# --- the row still says what it always said --------------------------------- #


def test_version_is_still_reported_and_labelled_as_recorded():
    """The metadata version stays -- it is what `serverInfo` hands the host, so
    it answers a real question. It just is not THIS question."""
    row = _entry(NOW).as_dict((NOW + timedelta(minutes=1)).timestamp())
    assert row["version"] == "1.108.309"
    assert row["code_stale"] is True


def test_code_stale_is_omitted_rather_than_guessed_when_unknown():
    """⚠ Omit-when-unestablished: a `code_stale: false` we did not measure would
    be read as a clean bill of health."""
    assert "code_stale" not in _entry(NOW).as_dict(None)


# --- the authority ----------------------------------------------------------- #


def test_src_component_is_required_not_just_depth(tmp_path):
    """⚠⚠ `<x>/site-packages/jcodemunch_mcp/__init__.py` is ALSO three levels
    under `<x>`. A positional check calls a copied install editable whenever a
    pyproject sits that far up -- the defect the first draft shipped."""
    (tmp_path / "pyproject.toml").write_text("version = '1.0'\n", encoding="utf-8")

    src = tmp_path / "src" / "jcodemunch_mcp"
    src.mkdir(parents=True)
    assert install_layout.is_source_layout(src / "__init__.py") is True

    copied = tmp_path / "site-packages" / "jcodemunch_mcp"
    copied.mkdir(parents=True)
    assert install_layout.is_source_layout(copied / "__init__.py") is False


def test_a_source_layout_without_a_pyproject_is_not_one(tmp_path):
    src = tmp_path / "src" / "jcodemunch_mcp"
    src.mkdir(parents=True)
    assert install_layout.is_source_layout(src / "__init__.py") is False


def test_newest_source_mtime_finds_the_newest(tmp_path):
    pkg = tmp_path / "pkg"
    (pkg / "sub").mkdir(parents=True)
    old = pkg / "a.py"
    new = pkg / "sub" / "b.py"
    old.write_text("", encoding="utf-8")
    new.write_text("", encoding="utf-8")
    import os

    os.utime(old, (1_000_000, 1_000_000))
    os.utime(new, (2_000_000, 2_000_000))
    assert install_layout.newest_source_mtime(pkg) == pytest.approx(2_000_000)


def test_an_unreadable_package_dir_is_unknown(tmp_path):
    assert install_layout.newest_source_mtime(tmp_path / "nope") is None


def _rederives_src_rule(src: str) -> bool:
    """Does this source re-derive the `<...>.parent.parent.name == "src"` rule?"""
    import ast

    try:
        tree = ast.parse(src)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Compare)
            and isinstance(node.left, ast.Attribute)
            and node.left.attr == "name"
            and any(
                isinstance(c, ast.Constant) and c.value == "src"
                for c in node.comparators
            )
        ):
            return True
    return False


def test_the_ratchet_fires_against_a_reintroduced_copy():
    """⚠⚠ Non-vacuity, and it is not optional here: a ratchet that scans only a
    clean tree is indistinguishable from one that matches nothing. Run it
    against the defect put back.
    """
    bad = (
        "def f(mf):\n"
        '    return mf.parent.parent.name == "src"\n'
    )
    good = (
        "def f(mf):\n"
        "    from ..install_layout import is_source_layout\n"
        "    return is_source_layout(mf)\n"
    )
    assert _rederives_src_rule(bad) is True
    assert _rederives_src_rule(good) is False, "must not flag the correct shape"


def test_the_authority_has_one_definition_of_the_src_rule():
    """⚠⚠ Extracted because this question had THREE readers with three answers.
    A fourth copy is the mechanism this project keeps paying for, so no other
    module may re-derive the rule.
    """
    root = Path(install_layout.__file__).parent
    offenders = [
        str(f.relative_to(root))
        for f in root.rglob("*.py")
        if f.name != "install_layout.py"
        and _rederives_src_rule(_safe_read(f))
    ]
    assert not offenders, f"re-derives the src-layout rule: {offenders}"


def _safe_read(f: Path) -> str:
    try:
        return f.read_text(encoding="utf-8")
    except OSError:
        return ""


# --- it reaches the report --------------------------------------------------- #


def test_sprawl_report_is_silent_about_code_when_alone(monkeypatch):
    """⚠ Gated: with no other process there is nothing to judge, and the walk is
    not paid."""
    called = []
    monkeypatch.setattr(
        install_layout, "running_source_changed_at",
        lambda: called.append(1) or 0.0,
    )
    monkeypatch.setattr(
        "jcodemunch_mcp.storage.process_registry.live_processes", lambda *a, **k: []
    )
    report = sprawl_report()
    assert "source_changed_at" not in report
    assert not called, "the mtime walk must not run with nothing to judge"


def test_sprawl_report_names_the_stale_processes(monkeypatch):
    changed = NOW.timestamp()
    monkeypatch.setattr(
        "jcodemunch_mcp.storage.process_registry.live_processes",
        lambda *a, **k: [
            _entry(NOW - timedelta(hours=1), pid=1),
            _entry(NOW + timedelta(hours=1), pid=2),
        ],
    )
    monkeypatch.setattr(
        "jcodemunch_mcp.install_layout.running_source_changed_at", lambda: changed
    )
    report = sprawl_report()
    assert report["processes_running_stale_code"] == 1
    assert "cannot show this" in report["hint_stale_code"]
    verdicts = {r["pid"]: r["code_stale"] for r in report["processes"]}
    assert verdicts == {1: True, 2: False}
