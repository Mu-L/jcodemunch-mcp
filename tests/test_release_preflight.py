"""`scripts/release_preflight.py` refuses on the cases it exists for.

ENFORCEMENT-PLAN item 3: four releases shipped on a RED build because the
release step trusted a local run. The pre-flight reads CI. These tests cover
its pure verdicts with data, never `gh`, and each one has a red arm: a check
that only passes against a good input can be deleted (Standing lessons).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "release_preflight.py"


def _load():
    spec = importlib.util.spec_from_file_location("_release_preflight", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


pf = _load()


def _runs(**conclusions):
    return [{"name": n, "conclusion": c} for n, c in conclusions.items()]


WITNESSES_OK = {
    "main: harness full (ubuntu, 3.12)": "success",
    "main: harness bench (online)": "success",
    "codeql (python)": "success",
}


def test_ci_passes_when_the_main_witnesses_succeeded():
    ok, pending, msg = pf.main_witness_verdict(_runs(**WITNESSES_OK))
    assert ok and pending is None, msg


def test_ci_ignores_the_release_workflows_own_running_jobs():
    runs = _runs(**WITNESSES_OK) + [
        {"name": "release: pre-flight", "conclusion": None, "status": "in_progress"}
    ]
    ok, pending, msg = pf.main_witness_verdict(runs)
    assert ok, msg


def test_ci_fails_on_a_failed_run_of_any_name():
    ok, pending, msg = pf.main_witness_verdict(
        _runs(**{**WITNESSES_OK, "codeql (python)": "failure"})
    )
    assert not ok and pending is None and "codeql (python): failure" in msg


def test_ci_fails_when_a_witness_is_absent():
    """A renamed main.yml job silently stops being a witness; this is the only place that notices."""
    ok, pending, msg = pf.main_witness_verdict(
        _runs(**{k: v for k, v in WITNESSES_OK.items() if "bench" not in k})
    )
    assert not ok and "witness absent" in msg and "main: harness bench (online)" in msg


def test_ci_reports_a_running_witness_as_pending_not_pass():
    runs = _runs(**{k: v for k, v in WITNESSES_OK.items() if "bench" not in k}) + [
        {
            "name": "main: harness bench (online)",
            "conclusion": None,
            "status": "in_progress",
        }
    ]
    ok, pending, msg = pf.main_witness_verdict(runs)
    assert (
        not ok and pending == "main: harness bench (online)" and "still running" in msg
    )


def test_ci_fails_with_no_runs_at_all():
    ok, pending, msg = pf.main_witness_verdict([])
    assert not ok and pending is None and "no check-runs" in msg
    ok, pending, msg = pf.main_witness_verdict(
        [{"name": "release: build", "conclusion": None, "status": "queued"}]
    )
    assert not ok and "no check-runs" in msg


def test_live_pin_sites_all_agree():
    pins = pf.read_pins(REPO)
    assert len(pins) == 7, sorted(pins)
    ok, msg = pf.pins_verdict(pins, None)
    assert ok, msg


def test_pins_fail_when_one_site_lags(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "jcodemunch-mcp"\nversion = "9.9.9"\n', encoding="utf-8"
    )
    (tmp_path / "server.json").write_text(
        json.dumps({"version": "9.9.9", "packages": [{"version": "9.9.8"}]}),
        encoding="utf-8",
    )
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"version": "9.9.9"}), encoding="utf-8"
    )
    (tmp_path / "whatsnew.json").write_text(
        json.dumps({"current": "9.9.9", "entries": [{"version": "9.9.9"}]}),
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "jcodemunch-mcp"\nversion = "9.9.9"\n', encoding="utf-8"
    )
    ok, msg = pf.pins_verdict(pf.read_pins(tmp_path), None)
    assert not ok and "packages[0].version=9.9.8" in msg


def test_pins_fail_when_a_site_is_unreadable(tmp_path):
    ok, msg = pf.pins_verdict(pf.read_pins(tmp_path), None)
    assert not ok and "unreadable" in msg


def test_pins_must_equal_the_requested_version():
    pins = pf.read_pins(REPO)
    ok, msg = pf.pins_verdict(pins, "0.0.0")
    assert not ok and "--version says 0.0.0" in msg


def test_changelog_heading_detection():
    text = "## [Unreleased]\n\n## [1.2.3] - 2026-01-01 - title\n"
    assert pf.changelog_has("1.2.3", text)
    assert not pf.changelog_has("1.2.4", text)
    assert not pf.changelog_has("1.2", text), "a prefix is not a heading"


def test_only_a_mergeable_clean_contributor_pr_blocks():
    prs = [
        {
            "number": 1,
            "author": {"login": "someone"},
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN",
        },
        {
            "number": 2,
            "author": {"login": "someone"},
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "BLOCKED",
        },
        {
            "number": 3,
            "author": {"login": "someone"},
            "mergeable": "CONFLICTING",
            "mergeStateStatus": "DIRTY",
        },
        {
            "number": 4,
            "author": {"login": pf.OWNER},
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN",
        },
    ]
    assert pf.mergeable_contributor_prs(prs) == ["#1 someone"]
