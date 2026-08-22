"""`config --check`'s hook report must agree with what `init` installs.

Two separate ways this diagnostic lied about a healthy machine, both fixed by
deriving the expected set from the installer instead of restating it:

1. The hand-written map omitted ``hook-sessionstart`` on the day it shipped.
2. Presence was tested with the substring ``jcodemunch-mcp <subcommand>``, which
   cannot appear in an absolute-path install — and `_hook_invocation()` writes an
   absolute path whenever ``shutil.which`` resolves, i.e. on most machines.

These assert against the CLI's real stdout, not an internal helper, because the
defect was invisible from inside: every lower layer was already correct.
"""

import json
import subprocess
import sys

import pytest

from jcodemunch_mcp.cli.init import _enforcement_hooks, _extract_jcm_subcommand


def _installer_subcommands() -> set[str]:
    return {
        sub
        for rules in _enforcement_hooks().values()
        for rule in rules
        for h in rule.get("hooks", [])
        if (sub := _extract_jcm_subcommand(h.get("command", "")))
    }


def _run_config_check(home, env_extra=None):
    env = {
        **{k: v for k, v in __import__("os").environ.items()},
        "HOME": str(home),
        "USERPROFILE": str(home),
        "PYTHONPATH": "src",
        "PYTHONIOENCODING": "utf-8",
        **(env_extra or {}),
    }
    return subprocess.run(
        [sys.executable, "-m", "jcodemunch_mcp.server", "config", "--check"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, timeout=180,
    ).stdout


def _write_settings(home, invocation: str, hooks: dict | None = None) -> None:
    """Install every enforcement hook, rewritten to use ``invocation`` as the exe.

    ``hooks`` lets a test install a pre-mutated hooks dict (e.g. a stale
    matcher) through the same writer instead of hand-rolling the file.
    """
    hooks = hooks if hooks is not None else _enforcement_hooks()
    for rules in hooks.values():
        for rule in rules:
            for h in rule.get("hooks", []):
                sub = _extract_jcm_subcommand(h["command"])
                h["command"] = f"{invocation} {sub}"
    d = home / ".claude"
    d.mkdir(parents=True, exist_ok=True)
    (d / "settings.json").write_text(
        json.dumps({"hooks": hooks}), encoding="utf-8"
    )


def test_every_installed_hook_is_reported(tmp_path):
    """The report must name every subcommand `_enforcement_hooks` writes."""
    _write_settings(tmp_path, "jcodemunch-mcp")
    out = _run_config_check(tmp_path)
    missing = [s for s in _installer_subcommands() if s not in out]
    assert not missing, f"config --check never mentions {missing}"


def test_sessionstart_is_reported_installed(tmp_path):
    """The specific omission: SessionStart shipped and the map did not know."""
    _write_settings(tmp_path, "jcodemunch-mcp")
    out = _run_config_check(tmp_path)
    assert "hook-sessionstart installed" in out
    assert "hook-sessionstart not installed" not in out


@pytest.mark.parametrize("invocation", [
    "jcodemunch-mcp",
    "C:/Python314/Scripts/jcodemunch-mcp.EXE",
    "/home/u/.local/bin/jcodemunch-mcp",
    '"C:/Program Files/py/Scripts/jcodemunch-mcp.EXE"',
])
def test_absolute_path_installs_report_installed(tmp_path, invocation):
    """`_hook_invocation()` resolves to an absolute path when PATH has the exe.

    The old substring marker could only ever match the bare-name form, so a
    correctly-installed machine read as having no hooks at all.
    """
    _write_settings(tmp_path, invocation)
    out = _run_config_check(tmp_path)
    for sub in _installer_subcommands():
        assert f"{sub} installed" in out, f"{sub} misreported for {invocation!r}"


def test_absent_hooks_still_report_missing(tmp_path):
    """Control: the check must not report everything present unconditionally."""
    d = tmp_path / ".claude"
    d.mkdir(parents=True, exist_ok=True)
    (d / "settings.json").write_text(json.dumps({"hooks": {}}), encoding="utf-8")
    out = _run_config_check(tmp_path)
    for sub in _installer_subcommands():
        assert f"{sub} not installed" in out


def test_control_pretooluse_reported_both_sides(tmp_path):
    """Control that passes with OR without the fix.

    Every other test here fails pre-fix, so one is needed to prove the harness
    is not simply broken: `hook-pretooluse` under a bare-name install is the one
    case the old substring marker handled correctly.
    """
    _write_settings(tmp_path, "jcodemunch-mcp")
    assert "hook-pretooluse installed" in _run_config_check(tmp_path)


def test_matcher_labels_match_the_installer(tmp_path):
    """A displayed matcher that differs from the installed one misleads.

    The hand-written map said PreToolUse fired on ``Read``; the installer has
    written a wider matcher since the Grep nudge landed. ``_write_settings``
    installs the current matchers, so the check must echo them back.
    """
    _write_settings(tmp_path, "jcodemunch-mcp")
    out = _run_config_check(tmp_path)
    assert "PreToolUse(Read|Grep|Glob|Bash)" in out
    assert "SessionStart(compact|resume|fork)" in out


def test_stale_installed_matcher_is_reported_not_masked(tmp_path):
    """The check must print the matcher actually INSTALLED and warn on drift.

    It used to print the EXPECTED matcher for any present hook, so a
    pre-upgrade settings.json carrying matcher "Read" read as healthy while
    the Grep steering never fired — the diagnostic masked the defect.
    """
    hooks = _enforcement_hooks()
    hooks["PreToolUse"][0]["matcher"] = "Read"  # stale pre-1.108.47 install
    _write_settings(tmp_path, "jcodemunch-mcp", hooks=hooks)
    out = _run_config_check(tmp_path)
    assert "PreToolUse(Read)" in out          # the truth, not the wish
    assert "matcher is stale" in out          # and an actionable warning
