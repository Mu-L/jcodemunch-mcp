"""The CLI/Env split: CLAUDE.md holds invariants, CLI-AND-ENV.md holds the tables.

⚠⚠ `CLI Subcommands` (8,367 chars) and `Env Vars` (13,097) were 16.6% of a
140,000-char session budget, and every row of both was loaded into every session.
They were split on 2026-08-31 under Maintenance Practice 5, along the same axis
the Key Files split used: **what is DERIVABLE leaves, what is NOT stays.**
`jcodemunch-mcp --help` and `jcodemunch-mcp config` answer "what does this do"
live; nothing answers "this is a RESPONSE limit, deliberately NOT max_file_size".

⚠⚠ **The failure this file exists to prevent is silent drift between two
committed artifacts.** A row in both files is a copy that will diverge; a row in
neither is documentation deleted by a careless edit and missed, because no
session loads the second file and nobody would notice.

⚠ The last two tests close the "in neither" direction as far as it can honestly
be closed. A hard roster check is NOT available: 37 `JCODEMUNCH_*` variables and
12 `add_parser` names are deliberately absent from both tables (internal knobs,
sub-subcommands, `CONFIGURATION.md`'s territory). What IS assertable is the
other direction — a documented row must still name something the source has, so
a rename that orphans a row fails here instead of rotting.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLAUDE_MD = ROOT / "CLAUDE.md"
CLI_AND_ENV = ROOT / "CLI-AND-ENV.md"
SRC = ROOT / "src" / "jcodemunch_mcp"

# ⚠ Rows that stay in CLAUDE.md WITHOUT carrying a warning marker. Practice 5
# measured the ⚠ marker as a proxy that over-cut by 15 entries in the Key Files
# split, so these were read by hand. Each states a prohibition, a constraint
# whose violation causes a defect, or a rationale. Adding a name here to buy
# budget is the whole thing this split was meant to stop.
CLI_RATIONALE = frozenset({
    "uninstall",           # preserves user-authored hook rules; removes only when empty
    "import-trace",        # redacts at the chokepoint by default; exactly one source flag
    "hook-precompact",     # ⚠ snapshot DELIVERY is hook-sessionstart, not here
    "hook-sessionstart",   # silent on startup/clear; registration runs BEFORE the source gate
    "receipt",             # --rates so consumers price from one table, not a drifting copy
    "reflect",             # read-only; only --apply-weights writes, and only the sidecar
})
ENV_RATIONALE = frozenset({
    "JCODEMUNCH_TRUSTED_FOLDERS",                # whitelist mode by default
    "JCODEMUNCH_PERF_TELEMETRY",                 # the ring is ALWAYS tracked; env gates persistence
    "JCODEMUNCH_RUNTIME_REDACT",                 # never off on production traces
    "JCODEMUNCH_RUNTIME_INGEST_ENABLED",         # write endpoints are a deliberate two-key turn
    "JCODEMUNCH_RUNTIME_INGEST_MAX_BODY_BYTES",  # decompressed size checked separately: gzip bomb
    "JCODEMUNCH_OPENAI_EXTRA_BODY",              # #323: a thinking model burns the output budget
    "JCODEMUNCH_WATCH_POLL_DELAY_MS",            # garbage parses to the default; polling-only
    "JCODEMUNCH_LIVE_JOURNAL",                   # on so the out-of-process PreCompact hook can read
    "JCODEMUNCH_TOOL_SURFACE",                   # any other value preserves behaviour byte-for-byte
    "JCODEMUNCH_LICENSE_KEY",                    # gates org-rollup ONLY; everything else is free
    "JCODEMUNCH_SCIP_MAX_ROWS",                  # env-only, deliberately not a config key
    "JCODEMUNCH_LAUNCH_ID",                      # env-only, not a config key
})

_ROW = re.compile(r"^\|\s*`([^`]+)`")


def _section(text: str, heading: str) -> str:
    if "## " + heading not in text:
        return ""
    return text.split("## " + heading, 1)[1].split("\n## ", 1)[0]


def _rows(path: Path, heading: str) -> "dict[str, str]":
    """{row key: whole line} for one table.

    ⚠ The KEY is the identity; the LINE is what carries the warning marker. An
    earlier draft of the Key Files ratchet returned names alone and then tested
    the NAME for a marker, so every entry read as warning-free and the budget
    check could never fire.

    ⚠ Keys are normalised to the bare command / variable name: the table spells
    a subcommand with its arguments (``index [target]``), and those move
    between the two files as documentation is edited.
    """
    out: dict[str, str] = {}
    for ln in _section(path.read_text(encoding="utf-8"), heading).split("\n"):
        m = _ROW.match(ln)
        if not m:
            continue
        name = m.group(1).split()[0].split("[")[0].split("\\")[0].strip()
        if name:
            out[name] = ln
    return out


@pytest.fixture(scope="module")
def cli():
    return _rows(CLAUDE_MD, "CLI Subcommands"), _rows(CLI_AND_ENV, "CLI Subcommands")


@pytest.fixture(scope="module")
def env():
    return _rows(CLAUDE_MD, "Env Vars"), _rows(CLI_AND_ENV, "Env Vars")


def test_both_halves_exist_and_are_populated(cli, env):
    """The control. Every assertion below is satisfied by two empty files."""
    assert len(cli[0]) >= 5, "CLAUDE.md's CLI Subcommands lost its rows"
    assert len(cli[1]) >= 25, "CLI-AND-ENV.md lost its CLI rows"
    assert len(env[0]) >= 15, "CLAUDE.md's Env Vars lost its rows"
    assert len(env[1]) >= 25, "CLI-AND-ENV.md lost its Env rows"


@pytest.mark.parametrize("heading", ["CLI Subcommands", "Env Vars"])
def test_no_row_lives_in_both_files(heading):
    """⚠⚠ A duplicated row is two artifacts that will disagree, and the one
    nobody loads is the one that goes stale unnoticed."""
    both = set(_rows(CLAUDE_MD, heading)) & set(_rows(CLI_AND_ENV, heading))
    assert not both, f"{heading}: duplicated across CLAUDE.md and CLI-AND-ENV.md: {sorted(both)}"


@pytest.mark.parametrize(
    "heading,rationale",
    [("CLI Subcommands", CLI_RATIONALE), ("Env Vars", ENV_RATIONALE)],
)
def test_claude_md_keeps_only_rows_that_earn_their_context(heading, rationale):
    """⚠⚠ The budget rule, made mechanical. A row stays in the always-loaded
    file only if it carries a warning marker or is a named rationale row.

    ⚠ If this fails on something you just documented, the fix is one of three,
    and NOT raising the budget: state the invariant with a warning marker, put
    the description in CLI-AND-ENV.md, or add the name to the rationale set
    with a comment saying what it is load-bearing for.
    """
    freeloaders = sorted(
        name for name, line in _rows(CLAUDE_MD, heading).items()
        if "⚠" not in line and name not in rationale
    )
    assert not freeloaders, (
        f"{heading}: warning-free rows in the always-loaded file: " + ", ".join(freeloaders)
    )


@pytest.mark.parametrize(
    "heading,rationale",
    [("CLI Subcommands", CLI_RATIONALE), ("Env Vars", ENV_RATIONALE)],
)
def test_every_rationale_row_is_actually_present(heading, rationale):
    """⚠ The allowlist must describe the file. A row that leaves and keeps its
    exemption makes the list stop being a description of what is there -- the
    same rule as asserting the sdist allowlist in both directions."""
    missing = sorted(rationale - set(_rows(CLAUDE_MD, heading)))
    assert not missing, f"{heading}: the rationale set names rows that are gone: {missing}"


def test_claude_md_points_at_the_other_half():
    """⚠ A split with no pointer is a deletion. A reader who cannot find the
    table concludes the subcommand does not exist and adds it again."""
    text = CLAUDE_MD.read_text(encoding="utf-8")
    for heading in ("CLI Subcommands", "Env Vars"):
        assert "CLI-AND-ENV.md" in _section(text, heading), (
            f"the pointer must be IN the {heading} section"
        )


def test_the_moved_half_says_it_is_not_loaded():
    """The counterpart: someone reading CLI-AND-ENV.md must know why a row is
    missing from it, or they will 'restore' an invariant that never left."""
    text = CLI_AND_ENV.read_text(encoding="utf-8")
    assert "NOT loaded" in text
    assert "CLAUDE.md" in text


def test_every_documented_env_var_still_exists_in_the_source():
    """⚠ The 'in neither' direction, as far as it goes honestly.

    A hard roster check is not available -- 37 `JCODEMUNCH_*` names are read in
    `src/` and deliberately absent from both tables. But a DOCUMENTED variable
    must still name something the source reads, so a rename that orphans a row
    fails here instead of rotting in a file no session loads.
    """
    literals: set[str] = set()
    for path in SRC.rglob("*.py"):
        body = path.read_text(encoding="utf-8", errors="replace")
        literals |= set(re.findall(r"[\"'](JCODEMUNCH_[A-Z0-9_]+)[\"']", body))
    documented = set()
    for path in (CLAUDE_MD, CLI_AND_ENV):
        for heading in ("Env Vars",):
            documented |= {
                n for n in _rows(path, heading) if n.startswith("JCODEMUNCH_")
            }
    orphans = sorted(documented - literals)
    assert not orphans, (
        "documented env vars that no longer appear in src/: " + ", ".join(orphans)
    )


def test_every_documented_subcommand_still_has_a_parser():
    """The same direction for the CLI table. `add_parser` is the roster."""
    server = (SRC / "server.py").read_text(encoding="utf-8", errors="replace")
    parsers = set(re.findall(r'add_parser\(\s*"([a-z0-9\-]+)"', server))
    documented: set[str] = set()
    for path in (CLAUDE_MD, CLI_AND_ENV):
        documented |= set(_rows(path, "CLI Subcommands"))
    orphans = sorted(n for n in documented if n not in parsers)
    assert not orphans, (
        "documented subcommands with no add_parser call: " + ", ".join(orphans)
    )
