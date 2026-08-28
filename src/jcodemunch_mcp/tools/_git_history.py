"""Does this repository's history actually cover the window we are about to score?

⚠⚠ Nine tools run ``git log --since=<N> days`` and, before this module, not one
of them could tell a TRUNCATED history from a QUIET one. A shallow clone answers
every churn question with a small number and exit status 0, so the failure has
no symptom: the axis ranks nothing, the grade looks plausible, and it is wrong
in the flattering direction.

⚠⚠ **This is the third time this defect has been fixed here and the first time
the READER has been touched.** Practice 6 records ``git fetch --depth=1``
shortening an already-complete clone in the health-radar Action;
``tests/test_observatory_clone_depth.py`` records the same thing in the
observatory's cloner, measured at **81.3 (B) shallow versus 75.6 (C) full on one
identical commit**, with ``churn_surface`` the only axis that moved. Both fixes
made OUR clones deep. Neither taught a consumer that a shallow history is
UNMEASURABLE rather than calm -- so every user running the Action or
``jcodemunch-mcp health`` in their own CI kept the defect, and
``actions/checkout`` defaults to ``fetch-depth: 1``.

⚠⚠ **The question asked here is COVERAGE, not shallowness, and the difference
is not pedantic.** ``--is-shallow-repository`` is the mechanism; "the history
reaches past the window" is the property. A ``--depth=500`` clone is shallow and
may still cover 90 days completely -- flagging it would be a false alarm that
teaches people to ignore the flag. A repository whose first commit is three
weeks old is NOT truncated; it is young, and its churn is real.

⚠ Tri-state, and UNKNOWN IS NEVER False. Absent git, a timeout, an unparseable
date: all return ``complete=None``, which consumers must treat as "cannot
establish", never as "history is fine". Same rule as ``has_any()`` and
``FreshnessProbe.classify``.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

#: Bounded memo. Keyed by the shallow marker's own state, so an ``--unshallow``
#: invalidates it without a TTL: the file appears, disappears or changes size
#: and the key moves with it.
_CACHE: dict[tuple, dict] = {}
_CACHE_MAX = 64

REMEDY = (
    "deepen the clone past the window "
    "(actions/checkout with fetch-depth: 0, or git fetch --unshallow)"
)


def _git(args: list[str], cwd: str, timeout: int = 10) -> tuple[int, str]:
    """Run git, returning (returncode, stdout). Never raises."""
    try:
        r = subprocess.run(
            ["git"] + args, cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        return r.returncode, r.stdout.strip()
    except FileNotFoundError:
        return -1, ""
    except subprocess.TimeoutExpired:
        return -2, ""
    except Exception:
        logger.debug("git probe failed in %s", cwd, exc_info=True)
        return -3, ""


def _shallow_marker_key(cwd: str) -> tuple:
    """Identity of the shallow marker file, so the memo cannot outlive a fetch.

    ⚠ ``.git`` is a FILE in a worktree or submodule, so resolve it via git
    rather than assuming a directory. A failure here yields a key that simply
    never matches a cached entry, which costs a re-probe and never a stale
    answer.
    """
    rc, git_dir = _git(["rev-parse", "--git-dir"], cwd)
    if rc != 0 or not git_dir:
        return (cwd, None, None)
    marker = Path(git_dir)
    if not marker.is_absolute():
        marker = Path(cwd) / git_dir
    marker = marker / "shallow"
    try:
        st = marker.stat()
        return (cwd, st.st_size, st.st_mtime_ns)
    except OSError:
        return (cwd, None, None)


def history_coverage(cwd: str, window_days: int) -> dict:
    """Can a ``--since=<window_days> days`` log see the whole window here?

    Returns ``{complete, shallow, oldest_commit, window_days, reason}`` where
    ``complete`` is True / False / **None (could not establish)**, plus
    ``remedy`` only when it is False.

    ``reason`` always names the finding, never the consequence.
    """
    if window_days <= 0:
        return _result(True, False, None, window_days, "window_is_not_positive")

    key = (_shallow_marker_key(cwd), window_days)
    hit = _CACHE.get(key)
    if hit is not None:
        return dict(hit)

    rc, out = _git(["rev-parse", "--is-shallow-repository"], cwd)
    if rc != 0:
        # Not a repo, no git, or a git predating the flag (added in 2.15).
        return _memo(key, _result(None, None, None, window_days, "shallow_state_unknown"))

    shallow = out.strip().lower() == "true"
    if not shallow:
        return _memo(key, _result(True, False, None, window_days, "full_history"))

    # Shallow, so the graft boundary decides it. Parentless commits reachable
    # from HEAD are the boundary in a shallow clone (and the true root in a
    # complete one, which cannot reach this branch).
    rc2, dates = _git(["log", "--max-parents=0", "--format=%aI", "HEAD"], cwd, timeout=20)
    if rc2 != 0 or not dates:
        return _memo(key, _result(None, True, None, window_days, "shallow_boundary_unreadable"))

    oldest = None
    for line in dates.splitlines():
        parsed = _parse_iso(line.strip())
        if parsed is None:
            continue
        if oldest is None or parsed < oldest:
            oldest = parsed
    if oldest is None:
        return _memo(key, _result(None, True, None, window_days, "shallow_boundary_undated"))

    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    covers = oldest <= cutoff
    return _memo(key, _result(
        covers, True, oldest.isoformat(), window_days,
        "shallow_but_covers_window" if covers else "shallow_truncates_window",
    ))


def _parse_iso(s: str) -> Optional[datetime]:
    """Parse git's ``%aI`` on every supported Python.

    ⚠⚠ **git renders a UTC offset as ``Z``, and ``datetime.fromisoformat``
    could not parse ``Z`` until 3.11.** So the boundary date came back
    unparseable on 3.10 -- but ONLY on a machine whose git chose the ``Z``
    spelling, which means UTC. Every CI runner is UTC; a developer box on a
    non-zero offset gets ``-05:00`` and cannot reproduce it at all. The
    integration tests here were green locally and red on 3.10 in CI for exactly
    that reason: **the machine's timezone selected the input format.**

    ⚠ Which is why ``test_parse_iso_accepts_both_offset_spellings`` pins BOTH
    spellings as a unit, with no repository and no clock involved. An
    integration test cannot guard this -- it can only observe whichever
    spelling the host happens to produce.

    ⚠ The tri-state held under the defect: an unparseable boundary reported
    ``complete: None``, not a confident answer. It degraded rather than lied.
    """
    if not s:
        return None
    # 3.11+ handles "Z" natively; normalising first is correct on every version.
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _result(
    complete: Optional[bool], shallow: Optional[bool],
    oldest: Optional[str], window_days: int, reason: str,
) -> dict:
    out = {
        "complete": complete,
        "shallow": shallow,
        "oldest_commit": oldest,
        "window_days": window_days,
        "reason": reason,
    }
    # ⚠ The remedy rides ONLY where it applies. Attaching it to an unknown or a
    # healthy result would train readers to skip the block.
    if complete is False:
        out["remedy"] = REMEDY
    return out


def _memo(key: tuple, value: dict) -> dict:
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[key] = dict(value)
    return dict(value)


def attach_history_coverage(result: dict, cwd: str, window_days: int) -> dict:
    """Stamp ``result['_meta']['git_history']`` unless the window is fully covered.

    ⚠⚠ Silent on a complete history BY DESIGN. A block that appears on every
    response is one nobody reads, and this exists to be noticed exactly when a
    churn number cannot be trusted. An UNKNOWN is disclosed too -- it is not a
    clean bill of health.
    """
    if not isinstance(result, dict):
        return result
    cov = history_coverage(cwd, window_days)
    if cov.get("complete") is True:
        return result
    meta = result.setdefault("_meta", {})
    if isinstance(meta, dict):
        meta["git_history"] = cov
    return result


def churn_is_measurable(cwd: str, window_days: int) -> bool:
    """True only when the window is provably covered.

    ⚠ Deliberately collapses None to False at the point a caller must decide
    whether to PUBLISH A GRADE. The tri-state survives in the disclosure; this
    is the gate, and a gate that cannot establish its precondition must not
    open. Same rule as ``_stop_rule``'s "every uncertainty resolves to False".
    """
    return history_coverage(cwd, window_days).get("complete") is True
