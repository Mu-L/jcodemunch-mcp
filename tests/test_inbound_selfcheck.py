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


@pytest.mark.parametrize("rc,red", [(0, False), (1, True), (2, False), (4, False), (5, False)])
def test_only_pytest_exit_one_is_red(rc, red):
    """Item-5 review, finding 2: the exit-code rule is the one discriminator
    in clause (b) and survived mutation to `!= 0` with no test. 2 is a
    collection error, 5 is nothing collected, 0 is green or all skipped."""
    assert sc.red_from_returncode(rc) is red


def _git(repo, *a):
    import subprocess
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@x", *a], cwd=repo, check=True, capture_output=True, text=True)


def test_red_run_files_must_match_the_pr_head(tmp_path):
    """Item-5 review, finding 1: `assert False` committed first and the
    real test written in the fix commit satisfied clause (b); the files
    the red run executed must be byte-identical at the head."""
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "base")
    _git(repo, "checkout", "-q", "-b", "inbound/fix-1-x")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_x.py").write_text("def test_x():\n    assert False\n", encoding="utf-8")
    _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "red")
    test_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    # an honest fix commit leaves the test alone
    (repo / "src").mkdir(); (repo / "src" / "x.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "fix")
    assert sc.test_files_rewritten_after(test_sha, ["tests/test_x.py"], "HEAD", cwd=repo) == []
    # a rewritten reproduction is named
    (repo / "tests" / "test_x.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "rewrite the test")
    assert sc.test_files_rewritten_after(test_sha, ["tests/test_x.py"], "HEAD", cwd=repo) == ["tests/test_x.py"]
    # a file deleted at the head is named too
    assert sc.test_files_rewritten_after(test_sha, ["tests/gone.py"], "HEAD", cwd=repo) == ["tests/gone.py"]


def test_red_run_through_the_worktree_binds_every_touched_path(tmp_path, monkeypatch):
    """Item-5 review round 2: the wiring (`head_ref` into the red run) and
    the fixture spelling. A test that reads a fixture, both committed
    first, then the FIXTURE rewritten in the fix commit: clause (b) must
    fail naming the fixture, through `test_commit_is_red_on_main` itself."""
    import sys
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "README").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "checkout", "-q", "-b", "inbound/fix-1-x")
    (repo / "tests" / "fixtures").mkdir(parents=True)
    (repo / "tests" / "fixtures" / "f.txt").write_text("bad", encoding="utf-8")
    (repo / "tests" / "test_x.py").write_text(
        "import pathlib\ndef test_x():\n    assert pathlib.Path(__file__).with_name('fixtures').joinpath('f.txt').read_text() == 'ok'\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "red")
    test_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    monkeypatch.setattr(sc, "ROOT", repo)
    monkeypatch.setattr(sc, "_pytest_cmd", lambda: [sys.executable, "-m", "pytest"])
    # honest: the test commit is red on main and untouched at the head
    red, why = sc.test_commit_is_red_on_main(test_sha, "main", tmp_path / "wt1", head_ref="HEAD")
    assert red is True and "pytest exit 1" in why, why
    # the fixture is rewritten in the "fix" commit; the test now passes at the head
    (repo / "tests" / "fixtures" / "f.txt").write_text("ok", encoding="utf-8")
    _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "fix by editing the fixture")
    red, why = sc.test_commit_is_red_on_main(test_sha, "main", tmp_path / "wt2", head_ref="HEAD")
    assert red is False and "tests/fixtures/f.txt" in why, why
    # without a head ref the identity check cannot run, and the red run alone still passes: that is the hole the ref closes
    red, _ = sc.test_commit_is_red_on_main(test_sha, "main", tmp_path / "wt3")
    assert red is True


def test_main_passes_head_ref_into_the_red_run(tmp_path, monkeypatch):
    seen = {}

    def fake(test_sha, base_ref, worktree, head_ref=None):
        seen["head_ref"] = head_ref
        return True, "ok"

    monkeypatch.setattr(sc, "test_commit_is_red_on_main", fake)
    pr = {"number": 1, "author": {"login": "jcodemunch-inbound"}, "headRefName": "inbound/fix-1-x",
          "body": "\n".join(HEADINGS) + "\nCloses #1", "files": [{"path": "tests/test_x.py"}]}
    (tmp_path / "pr.json").write_text(json.dumps(pr), encoding="utf-8")
    (tmp_path / "pr.diff").write_text("", encoding="utf-8")
    (tmp_path / "commits.json").write_text(json.dumps([{"sha": "a" * 40, "files": ["tests/test_x.py"]}]), encoding="utf-8")
    rc = sc.main(["--pr-json", str(tmp_path / "pr.json"), "--diff", str(tmp_path / "pr.diff"),
                  "--commits", str(tmp_path / "commits.json"), "--issue-labels", "agent-fix",
                  "--head-ref", "refs/inbound/pr-head"])
    assert rc == 0 and seen["head_ref"] == "refs/inbound/pr-head"
