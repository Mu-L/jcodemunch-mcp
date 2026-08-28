"""A truncated git history is UNMEASURABLE, never quiet.

⚠⚠ Nine tools run ``git log --since=<N> days``; before this, none could tell a
shallow clone from a calm repository. git answers exit 0 with a short log, so
``churn_surface`` ranked nothing but complexity and the grade came out
flattering. Fixed twice before in the CLONERS (Practice 6; the observatory,
81.3 B vs 75.6 C at one identical commit) and never once in a READER --
``actions/checkout`` defaults to ``fetch-depth: 1``, so every user kept it.

⚠⚠ **The first attempt at this fix MADE THE NUMBER WORSE and that is what
`test_dropping_an_unmeasurable_axis_is_not_a_fix` pins.** Omitting
``churn_surface`` the way ``runtime_coverage`` is omitted took the shallow tree
from **84.0 B to 88.8 B** while full-clone truth was **77.3 C**: dropping a
low-scoring axis RAISES a mean. NOT APPLICABLE and COULD NOT MEASURE are
different states and only the first may be dropped silently.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from jcodemunch_mcp.tools import _git_history as gh
from jcodemunch_mcp.tools.health_radar import compute_radar, diff_radar


def _git(args, cwd):
    return subprocess.run(
        ["git"] + args, cwd=str(cwd), capture_output=True, text=True,
        stdin=subprocess.DEVNULL,
    )


def _repo(path, commits, span_days):
    """A repo whose commits are spread back `span_days` from today."""
    path.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q", "-b", "main"], path)
    _git(["config", "user.email", "t@example.invalid"], path)
    _git(["config", "user.name", "t"], path)
    for i in range(commits):
        (path / "f.txt").write_text(f"v{i}\n", encoding="utf-8")
        when = datetime.now(timezone.utc) - timedelta(
            days=span_days - (span_days * i / max(commits - 1, 1))
        )
        stamp = when.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        _git(["add", "f.txt"], path)
        env_args = ["-c", f"user.name=t", "commit", "-q", "-m", f"c{i}",
                    "--date", stamp]
        subprocess.run(
            ["git"] + env_args, cwd=str(path), capture_output=True, text=True,
            stdin=subprocess.DEVNULL,
            env={**_env(), "GIT_COMMITTER_DATE": stamp, "GIT_AUTHOR_DATE": stamp},
        )
    return path


def _env():
    import os
    return dict(os.environ)


@pytest.fixture(autouse=True)
def _clear_memo():
    gh._CACHE.clear()
    yield
    gh._CACHE.clear()


def test_a_full_clone_covers_its_window(tmp_path):
    r = _repo(tmp_path / "full", commits=4, span_days=200)
    cov = gh.history_coverage(str(r), 90)
    assert cov["complete"] is True
    assert cov["shallow"] is False
    assert cov["reason"] == "full_history"
    assert "remedy" not in cov, "a healthy result must not carry a remedy"


def test_a_shallow_clone_that_truncates_the_window_is_incomplete(tmp_path):
    src = _repo(tmp_path / "src", commits=6, span_days=300)
    dst = tmp_path / "shallow"
    _git(["clone", "-q", "--depth=1", f"file://{src.as_posix()}", str(dst)], tmp_path)
    if _git(["rev-parse", "--is-shallow-repository"], dst).stdout.strip() != "true":
        pytest.skip("git did not produce a shallow clone here")
    cov = gh.history_coverage(str(dst), 90)
    assert cov["complete"] is False
    assert cov["shallow"] is True
    assert cov["reason"] == "shallow_truncates_window"
    assert cov["remedy"], "an actionable failure must say how to fix it"
    assert gh.churn_is_measurable(str(dst), 90) is False


def test_shallow_but_covering_is_not_flagged(tmp_path):
    """⚠⚠ The question is COVERAGE, not shallowness.

    `--is-shallow-repository` is the mechanism; "the history reaches past the
    window" is the property. A deep-but-bounded clone that covers the window is
    fine, and flagging it would teach people to ignore the flag.
    """
    src = _repo(tmp_path / "src", commits=8, span_days=400)
    dst = tmp_path / "deep"
    _git(["clone", "-q", "--depth=6", f"file://{src.as_posix()}", str(dst)], tmp_path)
    if _git(["rev-parse", "--is-shallow-repository"], dst).stdout.strip() != "true":
        pytest.skip("git did not produce a shallow clone here")
    cov = gh.history_coverage(str(dst), 30)
    assert cov["shallow"] is True
    assert cov["complete"] is True, cov
    assert cov["reason"] == "shallow_but_covers_window"


def test_a_young_repository_is_complete_not_truncated(tmp_path):
    """A three-week-old repo is YOUNG, not truncated. Its churn is real."""
    r = _repo(tmp_path / "young", commits=3, span_days=5)
    cov = gh.history_coverage(str(r), 90)
    assert cov["complete"] is True
    assert cov["shallow"] is False


def test_unknown_is_never_false(tmp_path):
    """⚠ No repo, no git, unreadable boundary: all UNKNOWN, never 'fine'."""
    empty = tmp_path / "not_a_repo"
    empty.mkdir()
    cov = gh.history_coverage(str(empty), 90)
    assert cov["complete"] is None, "a repo we cannot read is not a healthy repo"
    assert cov["reason"] == "shallow_state_unknown"
    # The publish gate collapses unknown to "do not publish".
    assert gh.churn_is_measurable(str(empty), 90) is False


def test_disclosure_is_silent_only_when_the_window_is_covered(tmp_path):
    r = _repo(tmp_path / "full", commits=4, span_days=200)
    ok: dict = {}
    gh.attach_history_coverage(ok, str(r), 90)
    assert "_meta" not in ok, "a block on every response is one nobody reads"

    unknown: dict = {}
    empty = tmp_path / "nope"
    empty.mkdir()
    gh.attach_history_coverage(unknown, str(empty), 90)
    assert unknown["_meta"]["git_history"]["complete"] is None, (
        "an UNKNOWN must be disclosed too; it is not a clean bill of health"
    )


# --------------------------------------------------------------------------- #
# The radar half — where the flattering grade actually reached a user.
# --------------------------------------------------------------------------- #

_BASE = dict(
    avg_complexity=4.02, dead_code_pct=0.0, cycle_count=2,
    unstable_modules=66, total_files=329, untested_pct=0.0,
)


def test_dropping_an_unmeasurable_axis_is_not_a_fix():
    """⚠⚠ The regression test for my own first attempt.

    Omitting `churn_surface` the way `runtime_coverage` is omitted RAISES the
    composite, because a low-scoring axis is being removed from a mean. The
    shallow tree went 84.0 -> 88.8 while the truth was 77.3. This asserts the
    direction, so nobody re-applies the omission as a fix.
    """
    scored = compute_radar(**_BASE, top_hotspot_score=348.0)
    dropped = compute_radar(**_BASE, top_hotspot_score=None)
    assert dropped["composite"] > scored["composite"], (
        "if this ever reverses, the premise of the withhold changed and the "
        "reasoning below must be re-derived, not the assertion relaxed"
    )
    # ...and therefore the honest answer is to publish neither.
    withheld = compute_radar(
        **_BASE, top_hotspot_score=None, unmeasurable_axes=["churn_surface"]
    )
    assert withheld["composite"] is None
    assert withheld["grade"] is None
    assert withheld["unmeasurable_axes"] == ["churn_surface"]


def test_a_withheld_grade_keeps_the_axes_it_did_measure():
    """Refusing a composite is not refusing to report. The measured axes stand."""
    w = compute_radar(
        **_BASE, top_hotspot_score=None, unmeasurable_axes=["churn_surface"]
    )
    assert set(w["axes"]) >= {"complexity", "dead_code", "cycles", "coupling"}
    assert all(a["score"] is not None for a in w["axes"].values())
    assert w["partial_composite"] is not None
    assert w["grade_withheld"]


def test_the_default_path_is_byte_for_byte_unchanged():
    """⚠ No caller passing `unmeasurable_axes` may see any difference."""
    r = compute_radar(**_BASE, top_hotspot_score=348.0)
    assert r["composite"] == 84.0
    assert r["grade"] == "B"
    assert "unmeasurable_axes" not in r
    assert "partial_composite" not in r
    assert compute_radar(**_BASE, top_hotspot_score=348.0, unmeasurable_axes=None) == r
    assert compute_radar(**_BASE, top_hotspot_score=348.0, unmeasurable_axes=[]) == r


def test_diff_radar_survives_a_withheld_composite():
    """⚠⚠ `.get(k, 0.0)` does NOT protect against this.

    The key is PRESENT with value None, so the default never fires. Before the
    guard this raised; defaulting to 0.0 would have been worse, reporting a
    ~77-point regression against a side that was never measured.
    """
    graded = compute_radar(**_BASE, top_hotspot_score=348.0)
    withheld = compute_radar(
        **_BASE, top_hotspot_score=None, unmeasurable_axes=["churn_surface"]
    )
    d = diff_radar(graded, withheld)
    assert d["composite_delta"] is None
    assert "not comparable" in d["grade_change"]
    assert "current" in d["grade_change"], "name WHICH side could not be graded"
    d2 = diff_radar(withheld, graded)
    assert "baseline" in d2["grade_change"]


# --------------------------------------------------------------------------- #
# ⚠⚠ The 3.10 guard. THIS is the test the integration cases could not be.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("spelling", [
    "2026-04-01T00:00:00Z",        # git's rendering when the offset is UTC
    "2026-04-01T00:00:00z",        # lowercase, tolerated by the same rule
    "2026-04-01T00:00:00+00:00",   # git's rendering on a non-zero-offset host
    "2026-04-01T00:00:00-05:00",
])
def test_parse_iso_accepts_both_offset_spellings(spelling):
    """⚠⚠ `datetime.fromisoformat` could not parse a `Z` suffix until 3.11.

    git renders a UTC offset as `Z`, so on 3.10 the shallow boundary came back
    unparseable and coverage degraded to `complete: None` -- but ONLY on a host
    whose git chose that spelling, which means a host in UTC.

    ⚠⚠ **Every CI runner is UTC; this developer box is CDT.** The integration
    tests above were green locally and red on 3.10 in CI, because *the machine's
    timezone selected the input format*. An integration test can only observe
    whichever spelling its host happens to produce -- it is structurally
    incapable of guarding this. A unit test over both spellings is.
    """
    parsed = gh._parse_iso(spelling)
    assert parsed is not None, f"{spelling!r} must parse on every supported Python"
    assert parsed.tzinfo is not None, "a git timestamp is never naive"


def test_parse_iso_returns_none_rather_than_guessing():
    """⚠ Unparseable is UNKNOWN, which is what makes the tri-state hold.

    The 3.10 defect degraded to `complete: None` instead of asserting a
    coverage answer off an unread date. That is the design working under a real
    fault, and it is worth a test of its own.
    """
    for junk in ("", "not-a-date", "2026-13-45T99:99:99Z"):
        assert gh._parse_iso(junk) is None


def test_an_undated_boundary_degrades_it_does_not_lie(monkeypatch, tmp_path):
    """⚠ With every boundary date unreadable, coverage must be None, not False.

    False would send a user chasing a shallow clone they may not have; None says
    we could not establish it, which is the truth.
    """
    src = _repo(tmp_path / "src", commits=4, span_days=300)
    dst = tmp_path / "shallow"
    _git(["clone", "-q", "--depth=1", f"file://{src.as_posix()}", str(dst)], tmp_path)
    if _git(["rev-parse", "--is-shallow-repository"], dst).stdout.strip() != "true":
        pytest.skip("git did not produce a shallow clone here")
    monkeypatch.setattr(gh, "_parse_iso", lambda _s: None)
    gh._CACHE.clear()
    cov = gh.history_coverage(str(dst), 90)
    assert cov["complete"] is None
    assert cov["reason"] == "shallow_boundary_undated"
    assert "remedy" not in cov, "an unknown must not prescribe a fix for a guess"
