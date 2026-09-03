"""SECURITY.md carries a vulnerability-reporting policy (DESIGN section 5, criterion 8).

The audit (docs/cicd/AUDIT.md section 5) found 360 lines of controls and no
way to report a hole in them. Offline file read, so it sits in the fast tier.
"""

from __future__ import annotations

import re
from pathlib import Path

TEXT = (Path(__file__).resolve().parents[1] / "SECURITY.md").read_text(encoding="utf-8")
HEADING = "## Reporting a vulnerability"


def _section() -> str:
    start = TEXT.find(HEADING)
    assert start >= 0, "SECURITY.md has no `## Reporting a vulnerability` section"
    rest = TEXT[start + len(HEADING):]
    nxt = re.search(r"^## ", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


def test_private_advisory_url_is_named():
    assert "github.com/jgravelle/jcodemunch-mcp/security/advisories/new" in _section()


def test_both_response_windows_are_stated_in_days():
    days = [int(d) for d in re.findall(r"\*\*(\d+) days\*\*", _section())]
    assert len(days) >= 2, f"expected an acknowledgement window and a verdict window, found {days}"
    assert days[0] <= days[1]


def test_public_issues_are_discouraged_for_reports():
    assert "Do not open a public issue" in _section()
