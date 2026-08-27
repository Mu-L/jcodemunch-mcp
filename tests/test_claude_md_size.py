"""`CLAUDE.md` is loaded into every session under this directory, so its size is
a per-turn cost paid by every reader forever.

Maintenance Practice 5 has said "keep `Current State` to the 3 newest releases"
since 2026-07-25, when the file was ~233k chars. On 2026-08-21 it was 200,543 --
over the harness ceiling, refusing to load, with the section the practice names
accounting for 14% of it. The practice was followed and the file grew anyway,
because the growth was in the sections it does not name: dated issue history
(82k) and a `Tests:` line carrying per-release counts back to 1.108.268 (16k).

⚠⚠ **A budget stated only in prose is not a budget.** Same argument as
`test_schema_budget.py` and `test_claude_md_rotation.py`: a convention that has
already failed needs a gate.

⚠ The budget is a DECISION, not a constant of nature, and it moved once already
(130k -> 140k, 2026-08-27). Raising it is legitimate and must be deliberate:
record who, when and why at the constant, because a number that drifts upward
whenever it is inconvenient is the prose convention again with extra steps.

Failure here means rotate, do not delete: closed history goes to
`ISSUE-HISTORY.md`, which is not loaded into a session, and `CLAUDE.md`
keeps the pointer plus whatever standing lesson the entries earned.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# The harness refuses to load a project instruction file above this. It is not a
# style preference and it is not ours to raise.
HARNESS_LIMIT = 150_000

# Where the gate fires. The gap to HARNESS_LIMIT is deliberate: a ceiling that
# fires exactly at the cliff fires for the first time in the session it breaks.
#
# ⚠⚠ Raised 130_000 -> 140_000 by jjg on 2026-08-27, which HALVES that gap from
# 20k to 10k. The pressure was structural rather than sloppy: the rotation gate
# in test_claude_md_rotation.py mandates EXACTLY three release entries, and
# those three plus the standing sections had left 5 characters of headroom, so
# the next addition of any size failed the build. Trimming further would have
# meant deleting reasoning to satisfy an arithmetic limit.
#
# ⚠ 10k is still a buffer, and it is the last one. The next time this is tight
# the answer is NOT another raise -- HARNESS_LIMIT is not ours to move, and at
# 150k the file stops loading with no warning at all. Rotate a standing section
# instead, or split the file.
BUDGET = 140_000

ARCHIVE = "ISSUE-HISTORY.md"


def _claude_md() -> str:
    return (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def test_claude_md_fits_the_session_budget():
    size = len(_claude_md())
    assert size <= BUDGET, (
        f"CLAUDE.md is {size:,} chars against a {BUDGET:,} budget "
        f"({HARNESS_LIMIT:,} is where the harness stops loading it). Rotate the "
        f"oldest dated entries into {ARCHIVE} rather than deleting them, and keep "
        f"the lesson they earned in the Standing lessons list."
    )


def test_the_archive_exists_and_is_pointed_at():
    """⚠ The two halves fail differently and both matter.

    A missing archive means someone deleted history instead of rotating it. A
    missing pointer means the history survives and nobody can find it, which is
    the same outcome for every reader.
    """
    assert (ROOT / ARCHIVE).is_file(), (
        f"{ARCHIVE} is gone. Closed history is rotated OUT of CLAUDE.md, never "
        f"deleted -- the entries are the evidence behind the standing lessons."
    )
    assert ARCHIVE in _claude_md(), (
        f"CLAUDE.md no longer points at {ARCHIVE}, so the rotated history is "
        f"unreachable from the file every session actually reads."
    )


def test_the_archive_is_tracked_by_git():
    """⚠⚠ Present on disk is not the same as kept.

    The rotation first wrote the archive to `docs/`, which this repo gitignores.
    Every check above passed -- the file existed, the pointer resolved, the
    budget was met -- while the history it holds would have vanished on the next
    clone and taken CI red with it. **A test that asks "does the file exist"
    answers a question about THIS working tree, not about the repository.**
    """
    import subprocess

    try:
        rc = subprocess.run(
            ["git", "ls-files", "--error-unmatch", ARCHIVE],
            cwd=ROOT, capture_output=True, stdin=subprocess.DEVNULL, timeout=10,
        ).returncode
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("no usable git here (sdist checkout or git absent)")
    assert rc == 0, (
        f"{ARCHIVE} is not tracked by git -- check .gitignore. The rotated "
        f"history exists only in this working tree and will not survive a clone."
    )


def test_no_dated_entry_survives_outside_the_archive():
    """The rotated section was ~40 dated `**YYYY-MM-DD: ...**` entry headers.

    ⚠ This does NOT forbid dates in CLAUDE.md -- the policy blocks and Standing
    lessons cite them constantly. It forbids the ENTRY SHAPE, which is what grows
    without bound: one bolded date opening a multi-paragraph write-up.
    """
    import re

    headers = re.findall(r"^\*\*(?:\w+ )?20\d\d-\d\d-\d\d:", _claude_md(), re.MULTILINE)
    assert not headers, (
        f"CLAUDE.md has {len(headers)} dated entry header(s) that belong in "
        f"{ARCHIVE}: {headers[:5]}"
    )
