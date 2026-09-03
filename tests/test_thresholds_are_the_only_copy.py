"""`harness/thresholds.json` is the only place a Floor lives.

Two halves, both required (Standing lesson 08-22: a ratchet must be run
against the reintroduced defect, never only the fixed tree):

1. Every entry loads, validates, and a loosened entry cannot hide.
2. Every `guard_patterns` regex (a) MATCHES its own historical spelling, so a
   pattern cannot be inert, and (b) matches NOTHING in tests/, benchmarks/ or
   .github/workflows/ outside the files the entry names in `enforced_by`.
   The loader reads `enforced_by` files too: they must call
   `harness.thresholds`, not restate the number.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from harness import thresholds as T

REPO = T.REPO_ROOT
SCAN_ROOTS = ("tests", "benchmarks", ".github/workflows", "harness/__main__.py")

# The spelling each guarded literal had BEFORE it moved into the threshold
# file. A pattern that fails to match its own history is not a guard.
_HISTORICAL = {
    "replay.max_relative_drop": "--gate 0.02",
    "schema.core_compact_ceiling": "assert core_compact <= 4000",
    "schema.drift_tolerance": "DRIFT_TOLERANCE = 0.05  # 5%",
    "route.control_at1": "EXIT_CONTROL_AT_1 = 55.0",
    "route.control_at1/baseline": "EXIT_BASELINE_CONTROL_AT_1 = 40.0",
    "coverage.min": "--cov-fail-under=74",
    "claude_md.max_chars": "BUDGET = 140_000",
}


def _files():
    for root in SCAN_ROOTS:
        p = REPO / root
        if p.is_file():
            yield p
            continue
        for f in p.rglob("*"):
            if f.is_file() and f.suffix in (".py", ".yml", ".yaml", ".toml", ".json", ".md"):
                yield f


def test_file_loads_and_every_entry_validates():
    entries = T.load(announce=False)
    assert len(entries) >= 20
    for e in entries.values():
        for k in T._REQUIRED:
            assert k in e, (e["id"], k)


def test_loosening_without_a_block_is_refused(tmp_path):
    bad = {"schema": "x", "thresholds": [{
        "id": "t", "criterion": "N6", "metric": "m", "comparator": "<=", "floor": 200,
        "set_at": {"commit": "0", "date": "d", "reason": "r"}, "enforced_by": [],
        "history": [{"floor": 100}],
    }]}
    p = tmp_path / "t.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(T.ThresholdError, match="loosened"):
        T.load(p, announce=False)
    bad["thresholds"][0]["loosened"] = {"by": "test", "reason": "test"}
    p.write_text(json.dumps(bad), encoding="utf-8")
    assert T.load(p, announce=False)["t"]["floor"] == 200


def test_loosened_entry_is_announced(capsys):
    T.load(announce=True)
    err = capsys.readouterr().err
    assert "LOOSENED threshold claude_md.max_chars" in err


@pytest.mark.parametrize("tid", sorted(_HISTORICAL))
def test_guard_pattern_matches_its_own_history(tid):
    e = T.get(tid.split("/")[0])
    pats = e.get("guard_patterns") or []
    assert pats, f"{tid} must carry guard_patterns"
    assert any(re.search(p, _HISTORICAL[tid]) for p in pats), (
        f"{tid}: none of {pats} matches the historical spelling {_HISTORICAL[tid]!r}; "
        "an inert pattern guards nothing"
    )


def test_no_guarded_literal_outside_the_threshold_file():
    entries = T.load(announce=False)
    offenders = []
    me = Path(__file__).resolve()
    for e in entries.values():
        pats = [re.compile(p) for p in (e.get("guard_patterns") or [])]
        if not pats:
            continue
        allowed = {REPO / f.split("::")[0] for f in e["enforced_by"]}
        for f in _files():
            if f == me or f in allowed or f == T.THRESHOLDS_PATH:
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            for p in pats:
                if p.search(text):
                    offenders.append(f"{e['id']}: {f.relative_to(REPO)} matches {p.pattern!r}")
    assert not offenders, "a Floor is restated outside harness/thresholds.json:\n" + "\n".join(offenders)


def test_enforcing_files_read_the_threshold_not_the_number():
    """The files named in enforced_by must import the loader (or be a workflow
    that shells out to `python -m harness threshold`)."""
    entries = T.load(announce=False)
    missing = []
    for e in entries.values():
        if not e.get("guard_patterns"):
            continue
        for ref in e["enforced_by"]:
            f = REPO / ref.split("::")[0].split(" ")[0]
            if not f.exists():
                missing.append(f"{e['id']}: {ref} does not exist")
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            if "harness.thresholds" not in text and "harness threshold" not in text and "from harness import" not in text:
                missing.append(f"{e['id']}: {ref} does not read harness.thresholds")
    assert not missing, "\n".join(missing)
