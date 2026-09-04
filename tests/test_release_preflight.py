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

REQUIRED = ["license/cla", "lint", "Harness fast tier", "test (ubuntu-latest, 3.12)"]


def _runs(**conclusions):
    return [{"name": n, "conclusion": c} for n, c in conclusions.items()]


def test_ci_passes_only_when_every_required_context_succeeded():
    ok, msg = pf.ci_verdict(
        REQUIRED,
        _runs(
            **{
                "lint": "success",
                "Harness fast tier": "success",
                "test (ubuntu-latest, 3.12)": "success",
            }
        ),
    )
    assert ok, msg


def test_ci_fails_on_a_failed_run():
    ok, msg = pf.ci_verdict(
        REQUIRED,
        _runs(
            **{
                "lint": "success",
                "Harness fast tier": "failure",
                "test (ubuntu-latest, 3.12)": "success",
            }
        ),
    )
    assert not ok and "Harness fast tier: failure" in msg


def test_ci_fails_when_a_required_context_has_no_run_at_all():
    """A renamed job silently drops out of the gate on GitHub's side; this is the only place that sees it."""
    ok, msg = pf.ci_verdict(
        REQUIRED, _runs(**{"lint": "success", "test (ubuntu-latest, 3.12)": "success"})
    )
    assert not ok and "Harness fast tier: no check-run on HEAD" in msg


def test_ci_fails_on_an_unfinished_run():
    runs = _runs(**{"lint": "success", "test (ubuntu-latest, 3.12)": "success"}) + [
        {"name": "Harness fast tier", "conclusion": None, "status": "in_progress"}
    ]
    ok, msg = pf.ci_verdict(REQUIRED, runs)
    assert not ok and "in_progress" in msg


def test_ci_does_not_expect_the_cla_status_on_a_main_commit():
    ok, _ = pf.ci_verdict(["license/cla", "lint"], _runs(lint="success"))
    assert ok


def test_ci_fails_when_nothing_is_required():
    ok, msg = pf.ci_verdict([], _runs(lint="success"))
    assert not ok and "no required checks" in msg
    ok, _ = pf.ci_verdict(["license/cla"], _runs(lint="success"))
    assert not ok


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


def _all(**conclusions):
    return [{"name": n, "conclusion": c} for n, c in conclusions.items()]


GATE_OK = {
    "fast: harness fast tier": "success",
    "full: test (ubuntu-latest, 3.12)": "success",
    "package: install and handshake (ubuntu-latest)": "success",
    "done: changelog": "success",
}


def test_fallback_passes_when_every_run_succeeded_and_the_gate_families_are_present():
    ok, msg = pf.all_runs_verdict(_all(**GATE_OK, **{"codeql (python)": "success"}))
    assert ok, msg


def test_fallback_fails_on_any_failed_or_unfinished_run():
    ok, msg = pf.all_runs_verdict(_all(**{**GATE_OK, "codeql (python)": "failure"}))
    assert not ok and "codeql (python): failure" in msg
    runs = _all(**GATE_OK) + [
        {"name": "bench: token benchmark", "conclusion": None, "status": "in_progress"}
    ]
    ok, msg = pf.all_runs_verdict(runs)
    assert not ok and "in_progress" in msg


def test_fallback_fails_when_a_gate_family_is_absent():
    runs = _all(**{k: v for k, v in GATE_OK.items() if not k.startswith("package")})
    ok, msg = pf.all_runs_verdict(runs)
    assert not ok and "package: install and handshake (" in msg


def test_fallback_fails_with_no_runs_at_all():
    ok, msg = pf.all_runs_verdict([])
    assert not ok and "no check-runs" in msg
