"""Every `inbound-*.yml` keeps the properties DESIGN section 9 promises:
no `pull_request_target`; write permissions only on triggers with no
external actor; the kill switch is the first step after checkout; the
model action is pinned to the recorded commit and given the prompt's own
model and turn ceiling; every checkout is `ref: main` or a same-repo ref;
`timeout-minutes` matches the POLICY section 7 row.

Red arms: a workflow that adds `pull_request_target`; a `contents: write`
on an `issues:` trigger; a kill-switch step moved below the first write; a
`--max-turns` above the budget; an unpinned or moved action SHA.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"
INBOUND = ROOT / ".github" / "inbound"
FILES = sorted(WF.glob("inbound-*.yml"))

# DESIGN D4 / AUDIT 3.4: the one commit the action is pinned to. Bumping it is
# a deliberate edit here AND in every workflow.
ACTION_SHA = "ef8bb1e43bf303cff727a1dd0b8837029fe982a2"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, INBOUND / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


budget = _load("budget")
rp = _load("render_prompts")


def _wf(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _triggers(doc: dict) -> dict:
    on = doc.get("on") or doc.get(True)  # PyYAML reads a bare `on:` as True
    return on if isinstance(on, dict) else {t: {} for t in (on or [])}


def _jobs(doc: dict) -> dict:
    return doc.get("jobs", {})


def _steps(job: dict) -> list:
    return job.get("steps", [])


def _perm_values(doc: dict) -> set[str]:
    out = set()
    for scope in [doc.get("permissions", {})] + [
        j.get("permissions", {}) for j in _jobs(doc).values()
    ]:
        if isinstance(scope, dict):
            out |= {f"{k}: {v}" for k, v in scope.items()}
    return out


def test_the_layer_has_workflows():
    assert FILES, "no inbound-*.yml; the item-2 PR adds the first two"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_no_pull_request_target_and_no_fork_checkout(path: Path):
    text = path.read_text(encoding="utf-8")
    assert "pull_request_target" not in text
    doc = _wf(path)
    for job in _jobs(doc).values():
        for s in _steps(job):
            uses = s.get("uses", "")
            if uses.startswith("actions/checkout@"):
                ref = (s.get("with") or {}).get("ref", "")
                assert (
                    ref == "main"
                    or ref.startswith("${{ github.event.pull_request.head") is False
                ), f"{path.name}: checkout of a PR head at the workspace root"
                assert (s.get("with") or {}).get("persist-credentials") is False, (
                    f"{path.name}: checkout persists credentials"
                )


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_write_permissions_only_on_actorless_or_same_repo_triggers(path: Path):
    doc = _wf(path)
    triggers = set(_triggers(doc))
    writes = {
        p
        for p in _perm_values(doc)
        if p.endswith(": write") and not p.startswith("id-token")
    }
    if not writes:
        return
    allowed = {
        "issues",
        "schedule",
        "workflow_dispatch",
        "workflow_run",
        "pull_request",
        "issue_comment",
    }
    assert triggers <= allowed, (path.name, triggers)
    if "pull_request" in triggers:
        text = path.read_text(encoding="utf-8")
        assert (
            "github.event.pull_request.head.repo.full_name == github.repository" in text
        ), (
            f"{path.name}: pull_request with a write permission needs the same-repo guard"
        )
    if "contents: write" in writes:
        assert path.stem in ("inbound-fix", "inbound-sweep"), (
            f"{path.name}: contents: write is reserved for the fix job and the sweep (DESIGN D7)"
        )


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_kill_switch_precedes_every_write(path: Path):
    """The self-check is the one job that runs with the switch off (DESIGN 5)."""
    if path.stem == "inbound-selfcheck":
        return
    doc = _wf(path)
    for name, job in _jobs(doc).items():
        steps = _steps(job)
        runs = [
            (i, (s.get("run") or "") + " " + (s.get("uses") or ""))
            for i, s in enumerate(steps)
        ]
        kill = [i for i, r in runs if "killswitch.py" in r]
        assert kill, f"{path.name}:{name} has no kill-switch step"
        first_write = [
            i
            for i, r in runs
            if re.search(
                r"gh (issue|pr) (edit|comment|create|ready)|git push|claude-code-action|apply_triage",
                r,
            )
        ]
        if first_write:
            assert kill[0] < first_write[0], (
                f"{path.name}:{name}: a write precedes the kill switch"
            )


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_event_text_never_reaches_run_by_interpolation(path: Path):
    """Item-2 review, finding 4: `${{ github.event.* }}` inside a `run:` is
    template injection; event text reaches the shell only through `env:`."""
    doc = _wf(path)
    bad = []
    for name, job in _jobs(doc).items():
        for s in _steps(job):
            run = s.get("run") or ""
            for m in re.finditer(
                r"\$\{\{\s*github\.event\.(?!workflow_run\.(?:id|conclusion)\b)[\w.]+",
                run,
            ):
                bad.append((name, m.group(0)))
    assert not bad, bad


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_the_model_step_holds_no_write_scope(path: Path):
    """Item-2 review, finding 1: the job that runs the model has read-only
    permissions and the read-only GITHUB_TOKEN; the App token lives in a
    job with no model."""
    doc = _wf(path)
    for name, job in _jobs(doc).items():
        steps = _steps(job)
        has_model = any("claude-code-action" in (s.get("uses") or "") for s in steps)
        if not has_model:
            continue
        perms = job.get("permissions") or doc.get("permissions") or {}
        writes = {k for k, v in perms.items() if v == "write" and k != "id-token"}
        assert not writes, (
            f"{path.name}:{name} runs the model with write scope {writes}"
        )
        for s in steps:
            if "claude-code-action" in (s.get("uses") or ""):
                tok = (s.get("with") or {}).get("github_token", "")
                assert "secrets.GITHUB_TOKEN" in tok, (
                    f"{path.name}:{name}: the model step must use GITHUB_TOKEN, not the App"
                )
                assert (
                    "gh api"
                    not in (s.get("with") or {})
                    .get("claude_args", "")
                    .split("--disallowedTools")[0]
                ), "`gh api` admits POST forms; never in the model's allow-list"
            assert "create-github-app-token" not in (s.get("uses") or ""), (
                f"{path.name}:{name}: the App token in a model job"
            )


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_timeouts_and_turns_match_the_policy(path: Path):
    doc = _wf(path)
    row = budget.BUDGETS.get(path.stem)
    if row is None:
        assert path.stem in (
            "inbound-intake",
            "inbound-selfcheck",
            "inbound-fix-promote",
        ), path.stem
        return
    for name, job in _jobs(doc).items():
        assert job.get("timeout-minutes", 0) <= row["timeout_min"], (path.name, name)
        for s in _steps(job):
            if "claude-code-action" in (s.get("uses") or ""):
                args = (s.get("with") or {}).get("claude_args", "")
                m = re.search(r"--max-turns (\d+)", args)
                assert m and int(m.group(1)) <= row["turns"], (path.name, name, args)
                assert (
                    "--permission-mode dontAsk" in args
                    and "--permission-prompts none" in args
                )


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_model_action_is_pinned_and_given_the_prompts_model(path: Path):
    doc = _wf(path)
    for name, job in _jobs(doc).items():
        for s in _steps(job):
            uses = s.get("uses") or ""
            if "claude-code-action" not in uses:
                continue
            assert uses == f"anthropics/claude-code-action@{ACTION_SHA}", (
                path.name,
                uses,
            )
            with_ = s.get("with") or {}
            assert "prompt" in with_ and "prompt_file" not in with_, (
                "the action has a `prompt` input only"
            )
            assert "WebFetch" in with_.get(
                "claude_args", ""
            ) and "WebSearch" in with_.get("claude_args", ""), (
                "WebFetch/WebSearch must be disallowed by name (DESIGN 9)"
            )
    text = path.read_text(encoding="utf-8")
    for m in re.finditer(r"\.github/inbound/prompts/(\w+)\.md", text):
        fm = rp.front_matter(
            (INBOUND / "prompts" / f"{m.group(1)}.md").read_text(encoding="utf-8")
        )
        assert fm["model"] in text, (
            f"{path.name}: prompt {m.group(1)} pins {fm['model']} but the workflow does not pass it"
        )
