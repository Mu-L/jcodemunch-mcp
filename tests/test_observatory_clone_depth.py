"""The observatory must clone enough history to SCORE, not just to index.

⚠⚠ `clone_or_update` used `--depth=1` with the comment "shallow clone is
sufficient for indexing -- we don't need history". True of indexing, false of
scoring. `churn_surface` is ``complexity x log(1 + commits_in_window)`` with the
window counted by ``git log --since=90.days``, so a one-commit clone reports
churn 1 for EVERY file in EVERY repository. The axis then ranks nothing but
complexity, identically for all eleven scored repos -- which is why it looked
plausible for months.

⚠⚠ Measured on jcodemunch-mcp at one commit: depth=1 scored **81.3 (B)**, full
history **75.6 (C)**. The observatory was FLATTERING every repository it scores,
ours included. Same defect Practice 6 records from the health-radar Action,
reappearing somewhere else that publishes a public verdict.

⚠ Measured on gin, the grade did NOT move (91.8 A both ways) but the top hotspot
CHANGED -- raw 55.45 -> 39.42 -- because an untouched complex file scores zero
once churn is real. That is the axis starting to mean what it says: complex code
you actually change, rather than complex code you merely own.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

from jcodemunch_mcp.tools import observatory


def _clone_source() -> str:
    return inspect.getsource(observatory.clone_or_update)


def test_the_churn_window_is_covered_with_a_buffer():
    """The clone window must exceed the window the scorer reads.

    ⚠ Derived from `get_hotspots`' own default rather than a literal, so
    widening the scorer's look-back cannot silently outrun the clone.
    """
    from jcodemunch_mcp.tools.get_hotspots import get_hotspots

    scorer_days = inspect.signature(get_hotspots).parameters["days"].default
    assert observatory._CHURN_WINDOW_DAYS >= scorer_days, (
        f"clone window {observatory._CHURN_WINDOW_DAYS}d is narrower than the "
        f"scorer's {scorer_days}d look-back"
    )
    assert observatory._HISTORY_BUFFER_DAYS > 0, (
        "a window with no buffer clips the boundary commit and is sensitive to "
        "clock skew between the runner and the remote"
    )


def _clone_arg_literals() -> list[str]:
    """String literals reachable in the function BODY, docstring excluded.

    ⚠ The first version of this test compared source-text POSITIONS and failed
    on correct code, because the docstring names `--depth=1` while explaining
    why it is not used -- earlier in the file than the code's first
    `--shallow-since=`. A guard that reads prose is measuring the explanation,
    not the behaviour.
    """
    tree = ast.parse(inspect.getsource(observatory.clone_or_update).lstrip())
    fn = tree.body[0]
    body = fn.body[1:] if (
        fn.body and isinstance(fn.body[0], ast.Expr)
        and isinstance(fn.body[0].value, ast.Constant)
        and isinstance(fn.body[0].value.value, str)
    ) else fn.body
    out = []
    for node in body:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                out.append(sub.value)
            elif isinstance(sub, ast.JoinedStr):
                out.append("".join(
                    v.value for v in sub.values
                    if isinstance(v, ast.Constant) and isinstance(v.value, str)
                ) + "<expr>")
    return out


def test_shallow_since_is_the_primary_clone_strategy():
    """The FIRST clone attempted must be the windowed one."""
    lits = _clone_arg_literals()
    since = [i for i, v in enumerate(lits) if v.startswith("--shallow-since=")]
    depth = [i for i, v in enumerate(lits) if v == "--depth=1"]
    assert since, "no --shallow-since argument in the function body"
    if depth:
        assert min(since) < min(depth), (
            "--depth=1 must be the fallback, never the primary clone"
        )


def test_depth_one_fallback_carries_its_reason():
    """⚠ A bare fallback to depth=1 reintroduces the defect silently.

    It is legitimate only for a repository whose newest commit predates the
    window -- there the churn genuinely IS zero. That distinction has to be
    written down, or the next reader deletes the shallow-since branch as
    redundant.
    """
    src = _clone_source()
    if "--depth=1" not in src:
        return
    assert "fallback" in src.lower() or "falling back" in src.lower()
    assert "quiet" in src.lower() or "predates" in src.lower(), (
        "the depth=1 branch must say WHY zero churn is correct there"
    )


def test_fetch_path_keeps_the_same_window():
    """⚠ The update path is the half that rots.

    A correct first clone followed by `fetch --depth=1` walks the cached
    worktree straight back to one commit on the second run, and the observatory
    caches its workdir between builds -- so the defect would return on every run
    after the first.
    """
    src = _clone_source()
    fetch_calls = [
        line for line in src.split("\n") if '"fetch"' in line or "'fetch'" in line
    ]
    assert fetch_calls, "no fetch call found; did the update path move?"
    joined = "\n".join(fetch_calls)
    assert "--depth=1" not in joined, "fetch must not re-truncate the cached clone"


def test_clone_is_still_bounded():
    """⚠ Not a full clone. The scoring needs 120 days, not Django's entire past.

    An unbounded clone would be correct and wasteful; this asserts the fix did
    not overshoot into re-downloading history nobody scores.
    """
    src = _clone_source()
    tree = ast.parse(pathlib.Path(observatory.__file__).read_text(encoding="utf-8"))
    assert tree is not None
    assert "--shallow-since=" in src
    assert "--unshallow" not in src, "unshallowing defeats the point of bounding"
