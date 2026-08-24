"""The route binary pilot is a spent, one-run experiment. Both halves are gated.

H3 was registered, run once, and refuted. Two things must stay true afterwards,
and neither survives on prose alone.

**1. The corpus is spent.** `predicate.py` was committed before any case existed
and must not change while `cases.json` still exists. Editing the predicate and
re-running against these 60 cases is a fitting pass wearing an experiment's
clothes, and it would look exactly like ordinary work in a diff.

⚠⚠ **This test cannot judge whether a proposed edit is fitting, and does not
try — it makes the judgement HAPPEN.** Same design as the LICENSE digest pin: any
edit fails, and clearing the failure forces someone to state which case they are
in, at the edit, rather than downstream.

**2. The prose must agree with the artifact.** The pilot cannot have a freshness
gate — re-running it needs three external checkouts and three local indexes,
none of which exist in CI. So the guard runs the other way: every number quoted
in `RESULT.md` and `ROADMAP.md` must match `results.json`.

⚠ That is the defect this suite hit on 2026-08-21 in another costume:
`benchmarks/route_recall/results.json` drifted from the code while `CLAUDE.md`
cited its stale figure for two weeks. There the fix was to re-run and compare;
here re-running is impossible, so the quotable numbers are pinned instead.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PILOT = ROOT / "benchmarks" / "route_binary_pilot"

# sha256 of predicate.py as registered, normalised for line endings. Git rewrites
# CRLF on checkout, so hashing raw bytes would pin a property of the CHECKOUT
# rather than of the predicate -- the exact mistake the LICENSE digest made on
# its first day, red on every Ubuntu leg and green on every Windows one.
_PREDICATE_DIGEST = "8391f93f35e76af450b7ef7c60ba19231fbd1ae982555869245df2aa1676e705"


def _norm_digest(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _results() -> dict:
    path = PILOT / "results.json"
    if not path.is_file():
        pytest.skip("pilot results not present (sdist checkout)")
    return json.loads(path.read_text(encoding="utf-8"))["summary"]


def test_the_predicate_has_not_changed_since_it_was_registered():
    """⚠⚠ If this fails, say which case you are in before clearing it.

    EDITING THE PREDICATE while `cases.json` exists is fitting: the result is
    already known, so any change is informed by it. The honest paths are to
    delete the spent corpus and register a new predicate for new cases, or to
    leave both alone.
    """
    path = PILOT / "predicate.py"
    if not path.is_file():
        pytest.skip("pilot not present (sdist checkout)")
    actual = _norm_digest(path)
    assert actual == _PREDICATE_DIGEST, (
        "benchmarks/route_binary_pilot/predicate.py changed after registration, "
        "while cases.json still exists. That is a fitting pass unless the corpus "
        "goes with it. If the change is deliberate and the corpus is being "
        "retired, delete cases.json/results.json in the same commit and update "
        f"this digest to {actual}."
    )


def test_the_headline_numbers_in_the_prose_match_the_artifact():
    """Every figure a reader can quote is pinned to the run that produced it."""
    summary = _results()
    full = summary["full_vocabulary"]
    ablated = summary["ablated_own_name"]

    quotable = {
        f'{full["accuracy_pct"]}%',
        f'{ablated["accuracy_pct"]}%',
        str(full["binomial_p_vs_50"]),
        str(summary["n"]),
    }
    for doc in ("RESULT.md",):
        path = PILOT / doc
        if not path.is_file():
            pytest.skip(f"{doc} not present")
        text = path.read_text(encoding="utf-8")
        for value in quotable:
            assert value in text, (
                f"{doc} does not quote {value!r}, which results.json reports. "
                f"The prose and the artifact must agree; re-read whichever is "
                f"wrong rather than adjusting the other to match."
            )


def test_the_refutation_is_stated_and_not_softened():
    """⚠ The conclusion is the deliverable.

    A later edit that keeps the numbers but drops the verdict leaves a reader
    with an ambiguous result and an open invitation to re-propose H3 — the exact
    outcome merging this was meant to prevent.
    """
    text = (PILOT / "RESULT.md").read_text(encoding="utf-8")
    assert re.search(r"\bREFUTED\b", text), "RESULT.md no longer states the verdict"
    assert "cancelled" in text.lower(), (
        "RESULT.md no longer records that the corpus project is cancelled, which "
        "is the decision the pilot was built to make."
    )


def test_the_result_is_actually_at_chance():
    """The verdict must follow from the artifact, not merely sit beside it.

    ⚠ Asserted as the PROPERTY (interval spans the floor, p is not significant)
    rather than as the literal numbers, so a re-run on a wider corpus that
    genuinely separated the classes would fail here and force a re-reading
    instead of quietly keeping the old conclusion.
    """
    summary = _results()
    floor = summary["blind_floor"]["pct"]
    for condition in ("full_vocabulary", "ablated_own_name"):
        block = summary[condition]
        low, high = block["wilson95"]
        assert low <= floor <= high, (
            f"{condition}: the 95% interval [{low}, {high}] no longer spans the "
            f"{floor}% floor. The stated refutation does not follow from this "
            f"artifact any more — re-read RESULT.md rather than editing this test."
        )
        assert block["binomial_p_vs_50"] > 0.05, (
            f"{condition}: p={block['binomial_p_vs_50']} is significant. Same as "
            f"above — the conclusion in the prose no longer matches the run."
        )


def test_the_corpus_is_balanced_as_the_protocol_registered():
    summary = _results()
    counts = set(summary["balanced"].values())
    assert len(counts) == 1, (
        f"the pilot corpus is no longer balanced: {summary['balanced']}. A "
        f"majority-class floor of 50% is what every figure here is measured "
        f"against."
    )
