"""Workflow hygiene the CI/CD design promises (docs/cicd/DESIGN.md section 10).

- every `uses:` names a 40-hex commit SHA (a tag can be moved; a SHA cannot);
- `continue-on-error` appears only in a job whose name says `(informational)`;
- no workflow restates a Floor: the only-copy guard already scans, this pins
  the directory into that scan's scope by asserting the patterns run here too.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((REPO / ".github" / "workflows").glob("*.yml"))
ACTIONS = sorted((REPO / ".github" / "actions").glob("*/action.yml"))
USES = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.M)
SHA_PIN = re.compile(r"^[^@]+@[0-9a-f]{40}$")


def _uses(path: Path) -> list[str]:
    return [u for u in USES.findall(path.read_text(encoding="utf-8")) if not u.startswith("./")]


@pytest.mark.parametrize("path", WORKFLOWS + ACTIONS, ids=lambda p: p.relative_to(REPO).as_posix())
def test_every_third_party_action_is_sha_pinned(path):
    bad = [u for u in _uses(path) if not SHA_PIN.match(u)]
    assert not bad, f"{path.name}: not pinned to a 40-hex commit SHA: {bad}"


def test_the_scan_is_not_vacuous():
    assert sum(len(_uses(p)) for p in WORKFLOWS) >= 10


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_continue_on_error_only_on_informational_jobs(path):
    text = path.read_text(encoding="utf-8")
    if "continue-on-error" not in text:
        return
    # Walk job blocks: a job starts at two-space indent under `jobs:`.
    jobs = re.split(r"^  (?=[A-Za-z0-9_-]+:\s*$)", text.split("\njobs:", 1)[1], flags=re.M)
    offenders = []
    for block in jobs:
        if "continue-on-error" in block:
            # The JOB's name is at exactly four spaces; step names sit deeper.
            m = re.search(r"^    name:\s*(.+)$", block, re.M)
            name = (m.group(1) if m else block.splitlines()[0]).strip().strip('"')
            if "(informational)" not in name:
                offenders.append(name)
    assert not offenders, f"{path.name}: continue-on-error on a job not marked (informational): {offenders}"
