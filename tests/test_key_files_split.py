"""The Key Files split: CLAUDE.md holds invariants, KEY-FILES.md holds the map.

⚠⚠ Key Files was **44.4% of a 140,000-char session budget** and Maintenance
Practice 5 named it the next lever. It was split on 2026-08-29 along the one axis
that costs nothing: **what is DERIVABLE leaves, what is NOT stays.** jcodemunch
answers "what is this module" live; nothing answers "this cache is evicted on
every write, so it is not a cache".

⚠⚠ **The failure this file exists to prevent is silent drift between two
committed artifacts** -- the same defect as a benchmark whose four mirrors
disagree. An entry in both files is a copy that will diverge; an entry in
neither is documentation that was deleted by a careless edit and missed, because
no session loads the second file and nobody would notice.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLAUDE_MD = ROOT / "CLAUDE.md"
KEY_FILES = ROOT / "KEY-FILES.md"

_ENTRY = re.compile(r"^(\s{2,})(\S+)\s+#")
_DIR = re.compile(r"^(\s*)(\S+/)\s*$")

# ⚠ The 15 entries that stay in CLAUDE.md WITHOUT carrying a warning marker.
# Each states a prohibition, a constraint whose violation causes a defect, or a
# rationale -- the things the marker heuristic could not see. Adding a name here
# is a claim that the entry is load-bearing; adding one to buy budget is the
# whole thing this split was meant to stop.
# ⚠ Qualified by directory, never bare: two of these names appear twice in the
# tree, and a bare-name entry here would exempt both.
_SRC = "src/jcodemunch_mcp/"
RATIONALE_ENTRIES = frozenset(_SRC + n for n in (
    "counter.py",                  # pure, no server import -- prevents a cycle
    "investigator/deletion_safety.py",  # NOT an MCP tool (item 3 moratorium)
    "storage/sqlite_store.py",     # indexwrite lock ordering, across processes
    "retrieval/subject_state.py",  # UNKNOWN is never a change
    "tools/_scip_consume.py",      # honest-None when scip_edges absent
    "tools/get_pr_risk_profile.py",# static callers keep the 5-signal mix bit-for-bit
    "tools/check_delete_safe.py",  # honest-hint caveat; test-only consumption downgrades
    "tools/health_radar.py",       # 7th axis omitted so composites stay comparable
    "tools/find_unused_paths.py",  # refuses on an empty table rather than flagging all
    "runtime/redact.py",           # single chokepoint
    "runtime/http_routes.py",      # off by default, two-key turn, gzip-bomb guard
    "runtime/confidence.py",       # mode=ro&immutable=1, never bumps WAL mtime
    "evidence/receipts.py",        # fail-closed on id reuse
    "evidence/producers.py",       # THE GATE; immune to early returns by construction
    "evidence/scip.py",            # honest ValueError; display_name is a fallback only
))


def _section(text: str) -> str:
    if "## Key Files" not in text:
        return text
    return text.split("## Key Files", 1)[1].split("\n## ", 1)[0]


def _entries(path: Path) -> "dict[str, str]":
    """Module entries QUALIFIED BY DIRECTORY, walked off the tree's indentation.

    ⚠⚠ Keying on the bare filename is wrong here, and this check caught it on its
    own first run: `redact.py` and `confidence.py` each name TWO different
    modules (`src/jcodemunch_mcp/redact.py` vs `runtime/redact.py`;
    `runtime/confidence.py` vs `retrieval/confidence.py`). A bare-name key
    reported them duplicated across the split when nothing was, and would
    equally have let one allowlist entry exempt both. Same defect as the Rust
    fidelity harness keying bare names into a set: **a name is not an identity.**

    ⚠ Returns {qualified name: whole line}. The name is the IDENTITY; the LINE is
    what carries the warning marker. An earlier draft returned names alone and
    then tested the NAME for a marker, so every entry read as warning-free and
    the budget check could never fire.
    """
    out: dict[str, str] = {}
    stack: list[tuple[int, str]] = []
    for ln in _section(path.read_text(encoding="utf-8")).split("\n"):
        d = _DIR.match(ln)
        if d:
            indent = len(d.group(1))
            while stack and stack[-1][0] >= indent:
                stack.pop()
            stack.append((indent, d.group(2)))
            continue
        m = _ENTRY.match(ln)
        if m:
            indent = len(m.group(1))
            out["".join(seg for i, seg in stack if i < indent) + m.group(2)] = ln
    return out


@pytest.fixture(scope="module")
def split():
    return _entries(CLAUDE_MD), _entries(KEY_FILES)


def test_both_halves_exist_and_are_populated(split):
    """The control. Every assertion below is satisfied by two empty files."""
    claude, doc = split
    assert len(claude) >= 30, "CLAUDE.md's Key Files lost its entries"
    assert len(doc) >= 50, "KEY-FILES.md lost its entries"


def test_no_entry_lives_in_both_files(split):
    """⚠⚠ A duplicated entry is two artifacts that will disagree, and the one
    nobody loads is the one that goes stale unnoticed."""
    claude, doc = split
    both = set(claude) & set(doc)
    assert not both, f"duplicated across CLAUDE.md and KEY-FILES.md: {sorted(both)}"


def test_claude_md_keeps_only_entries_that_earn_their_context(split):
    """⚠⚠ The budget rule, made mechanical. An entry stays in the always-loaded
    file only if it carries a warning marker or is a named rationale entry.

    ⚠ If this fails on a module you just documented, the fix is one of three,
    and NOT raising the budget: state the invariant with a warning marker, put
    the description in KEY-FILES.md, or add the name to RATIONALE_ENTRIES
    with a comment saying what it is load-bearing for.
    """
    claude, _ = split
    freeloaders = sorted(
        name for name, line in claude.items()
        if "⚠" not in line and name not in RATIONALE_ENTRIES
    )
    assert not freeloaders, (
        "warning-free entries in the always-loaded file: " + ", ".join(freeloaders)
    )


def test_every_rationale_entry_is_actually_present(split):
    """⚠ The allowlist must describe the file. An entry that leaves and keeps
    its exemption makes the list stop being a description of what is there --
    the same rule as asserting the sdist allowlist in both directions."""
    claude, _ = split
    missing = sorted(RATIONALE_ENTRIES - set(claude))
    assert not missing, f"RATIONALE_ENTRIES names entries that are gone: {missing}"


def test_claude_md_points_at_the_other_half(split):
    """⚠ A split with no pointer is a deletion. A reader who cannot find the map
    concludes the module is undocumented and writes it again."""
    text = CLAUDE_MD.read_text(encoding="utf-8")
    assert "KEY-FILES.md" in text
    assert "KEY-FILES.md" in _section(text), "the pointer must be IN the section"


def test_the_moved_half_says_it_is_not_loaded():
    """The counterpart: someone reading KEY-FILES.md must know why a module is
    missing from it, or they will 'restore' an invariant that never left."""
    text = KEY_FILES.read_text(encoding="utf-8")
    assert "NOT loaded" in text
    assert "CLAUDE.md" in text
