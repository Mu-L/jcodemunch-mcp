"""The documented CI-environment reproduce must install what CI installs.

⚠⚠ **The release checklist's step 2c read `uv run --python 3.13 python -m
pytest tests/ -q` and NEVER built CI's environment.** CI runs
`uv sync --locked --group dev --extra watch` first; the documented command
synced nothing and named no extra, so it inherited whatever `.venv` happened to
hold. It looked correct for as long as a previous sync's packages survived.

⚠⚠ **How it surfaced, and why the usual signals missed it.** Mid-release on
2026-08-28 the reproduce returned **exit 0** and the totals reconciled exactly
(8,740 + 18 new tests = 8,758) -- the two things "green" normally means here.
But `passed` fell 8,721 -> 8,634 while `skipped` rose 19 -> 124: **105 tests had
silently not executed**, because `watchfiles` (the `[watch]` extra CI installs
BY NAME) was absent from the environment.

⚠ Third instance of one family, and the sentence is already in CONTRIBUTING.md:
*CI installs with `uv sync` and never runs the command the docs give a human, so
the thing we test is not the thing they do.* The first was
`pip install -e ".[test]"` (an extra no repo declares); the second was
`-n 4 --dist loadfile` under a bare `python -m pytest`, which collects nothing
and exits 0.

⚠⚠ **The checklist itself cannot be tested from here.** It lives in
`.claude/skills/release/SKILL.md`, which is gitignored -- the v0.2.6
credential-leak fix -- so a correction there is machine-local and gone on a
fresh checkout. **Do not un-ignore `.claude/` to make it testable**; that
reintroduces the vector that got five releases yanked. This module instead binds
the durable copy in `CLAUDE.md` to the workflow, so the two cannot drift apart
unnoticed.
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "test.yml"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"


def _test_job_sync_line() -> str:
    """The install command from the job that runs the test matrix.

    ⚠ `test.yml` carries more than one `uv sync`; the coverage job installs
    without `--extra watch` deliberately. The matrix job is the one a human is
    trying to reproduce, and it is identified by being the sync that names an
    extra -- not by line order, which moves.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    syncs = re.findall(r"uv sync[^\n]*", text)
    assert syncs, "no `uv sync` in test.yml; did the install step move?"
    with_extra = [s.strip() for s in syncs if "--extra" in s]
    assert with_extra, (
        "no `uv sync ... --extra ...` in test.yml. If the matrix job stopped "
        "installing an extra, update this test AND the documented reproduce "
        "command together -- they are the same fact in two places."
    )
    return with_extra[0]


def _documented_flags() -> set[str]:
    """Flags in the reproduce command recorded in CLAUDE.md."""
    text = CLAUDE_MD.read_text(encoding="utf-8")
    m = re.search(r"uv sync --locked[^\n`]*", text)
    assert m, (
        "CLAUDE.md no longer documents a `uv sync --locked ...` reproduce "
        "command. It is the only copy that survives a fresh checkout, because "
        "the release skill is gitignored."
    )
    return set(re.findall(r"--[a-z-]+(?:\s+[\w.-]+)?", m.group(0)))


def test_the_documented_reproduce_installs_what_ci_installs():
    """⚠⚠ The property: every flag CI uses appears in the documented command.

    Asserted as a SUBSET rather than string equality — the documented form adds
    `--python 3.13` to pin the version, which CI gets from its matrix instead.
    Equality would fail on a difference that is correct.
    """
    ci = _test_job_sync_line()
    ci_flags = set(re.findall(r"--[a-z-]+(?:\s+[\w.-]+)?", ci))
    documented = _documented_flags()
    missing = ci_flags - documented
    assert not missing, (
        f"the documented reproduce omits {sorted(missing)}, which CI installs.\n"
        f"  CI:         {ci}\n"
        f"  documented: flags {sorted(documented)}\n"
        "A reproduce that installs less than CI cannot reproduce CI. Fix "
        "CLAUDE.md and .claude/skills/release/SKILL.md together."
    )


def test_the_watch_extra_is_named_explicitly():
    """⚠ `watchfiles` is what went missing, so name it rather than trusting a set.

    A regex over flags would still pass if `--extra watch` became
    `--extra something-else`; this pins the extra whose absence hid 105 tests.
    """
    assert "--extra watch" in _test_job_sync_line()
    text = CLAUDE_MD.read_text(encoding="utf-8")
    assert "--extra watch" in text, (
        "CLAUDE.md must name `--extra watch`; its absence is what silently "
        "skipped 105 tests while the run reported exit 0"
    )


def test_the_documented_command_syncs_before_it_runs():
    """⚠⚠ `uv run` alone inherits an environment it did not create.

    That is the entire defect: the old command tested whatever `.venv` last held.
    A sync must precede the test run in the documented text.
    """
    text = CLAUDE_MD.read_text(encoding="utf-8")
    sync = text.find("uv sync --locked")
    assert sync != -1, "no sync in the documented reproduce"
    run = text.find("uv run --python 3.13 pytest", sync)
    assert run != -1, (
        "the documented reproduce must run pytest THROUGH uv after syncing; "
        "a bare `python -m pytest` uses a different interpreter than the one "
        "just synced"
    )


@pytest.mark.parametrize("bad", [
    "uv run --python 3.13 python -m pytest tests/ -q",
])
def test_the_broken_form_is_not_documented_anywhere(bad):
    """⚠ The exact string that shipped this defect, pinned so it cannot return.

    It is a *documentation* string, so nothing else would ever fail if someone
    pasted it back.
    """
    text = CLAUDE_MD.read_text(encoding="utf-8")
    # Allowed only where it is explicitly called out as the WRONG form.
    # ⚠ The window spans BOTH sides. The disclaimer can precede the command
    # ("the old step read X") or follow it ("X ... never built CI's env"), and
    # the first version of this test looked only backwards -- so it failed on
    # correct prose, which is a guard that trains people to weaken it.
    for m in re.finditer(re.escape(bad), text):
        window = text[max(0, m.start() - 400):m.end() + 400]
        assert any(w in window for w in ("NEVER built", "WRONG", "until 2026-08-28")), (
            "CLAUDE.md documents the pre-2026-08-28 reproduce command without "
            "marking it as the broken form; it installs neither the dev group "
            "nor `--extra watch`"
        )
