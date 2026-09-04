"""The self-check reads the never-touch list and the template from the
policy and design, and every clause (a) to (f) fails for its own reason
(DESIGN section 5).

Red arms: a PR touching `.claude/settings.json` passing (a); a src/ commit
before the first test commit passing (b); a body with the headings out of
order passing (c); a version-pin diff passing (a).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INBOUND = ROOT / ".github" / "inbound"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, INBOUND / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sc = _load("selfcheck")
PATTERNS = sc.never_touch_patterns((ROOT / "docs" / "inbound" / "POLICY.md").read_text(encoding="utf-8"))
HEADINGS = sc.template_headings((ROOT / "docs" / "inbound" / "DESIGN.md").read_text(encoding="utf-8"))


def test_patterns_come_from_the_policy_block():
    assert ".claude/**" in PATTERNS and "harness/thresholds.json" in PATTERNS and ".github/inbound/**" in PATTERNS
    assert "pyproject.toml" not in PATTERNS, "the version pin is checked by diff, not by path"


@pytest.mark.parametrize(
    "path",
    [
        ".claude/settings.json",
        ".claude/hooks/deny_guard.py",
        ".github/workflows/pr-gate.yml",
        ".github/inbound/prompts/fix.md",
        "harness/thresholds.json",
        "harness/retired.json",
        "docs/harness/ARCHAEOLOGY.md",
        "docs/standard/STANDARD.md",
        "SECURITY.md",
        "CLAUDE.md",
        "server.json",
    ],
)
def test_never_touch_paths_are_caught(path):
    assert sc.touches_never_touch([path, "src/x.py"], PATTERNS) == [path]


def test_ordinary_paths_pass():
    assert sc.touches_never_touch(["src/jcodemunch_mcp/server.py", "tests/test_x.py", "CHANGELOG.md", "docs/inbound/FINDINGS.md"], PATTERNS) == []


def test_version_pin_change_is_caught():
    assert sc.version_pin_changed('-version = "1.108.317"\n+version = "1.108.318"\n') is True
    assert sc.version_pin_changed('+    "tree-sitter>=0.25",\n') is False


def test_commit_order_requires_test_first_and_alone():
    ok, problems = sc.commit_order([{"sha": "a" * 40, "files": ["tests/test_new.py"]}, {"sha": "b" * 40, "files": ["src/x.py", "CHANGELOG.md"]}])
    assert ok == "a" * 40 and problems == []
    _, problems = sc.commit_order([{"sha": "b" * 40, "files": ["src/x.py"]}, {"sha": "a" * 40, "files": ["tests/test_new.py"]}])
    assert any("before the first test commit" in p for p in problems)
    _, problems = sc.commit_order([{"sha": "c" * 40, "files": ["tests/test_new.py", "src/x.py"]}])
    assert any("also touches src/" in p for p in problems)
    assert sc.commit_order([{"sha": "d" * 40, "files": ["src/x.py"]}])[1] == ["no commit touches tests/"]


def test_template_headings_are_read_from_design_and_order_matters():
    assert HEADINGS[0] == "## What was asked" and HEADINGS[-1] == "## Audit" and len(HEADINGS) == 9
    body = "\n".join(HEADINGS)
    assert sc.body_follows_template(body, HEADINGS) == []
    swapped = "\n".join([HEADINGS[1], HEADINGS[0]] + HEADINGS[2:])
    assert any("out of order" in x for x in sc.body_follows_template(swapped, HEADINGS))
    assert "## Audit" in sc.body_follows_template("\n".join(HEADINGS[:-1]), HEADINGS)


def test_main_names_every_failed_clause(tmp_path, capsys):
    pr = {
        "number": 1,
        "author": {"login": "someone"},
        "headRefName": "feature/x",
        "body": "no template, no closes",
        "files": [{"path": ".claude/settings.json"}, {"path": "src/x.py"}],
    }
    (tmp_path / "pr.json").write_text(json.dumps(pr), encoding="utf-8")
    (tmp_path / "pr.diff").write_text('-version = "1.0"\n+version = "1.1"\n', encoding="utf-8")
    (tmp_path / "commits.json").write_text(json.dumps([{"sha": "b" * 40, "files": ["src/x.py"]}]), encoding="utf-8")
    rc = sc.main([
        "--pr-json", str(tmp_path / "pr.json"), "--diff", str(tmp_path / "pr.diff"),
        "--commits", str(tmp_path / "commits.json"), "--skip-red-run",
    ])
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    clauses = {x[:3] for x in out["failed"]}
    assert clauses == {"(a)", "(b)", "(c)", "(d)", "(e)", "(f)"}, out["failed"]
