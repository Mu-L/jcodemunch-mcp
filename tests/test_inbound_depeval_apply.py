"""`agent:ready-to-merge` needs every input green; every other combination
is a weaker label (POLICY section 2, dependency rows).

Red arms: a major bump with APPROVE labelled ready; a Floor FAIL with
APPROVE labelled ready; a missing result labelled ready; a grammar bump
labelled anything but bench-pending / needs-human; a second run posting a
second comment instead of editing the sticky one.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INBOUND = ROOT / ".github" / "inbound"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, INBOUND / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ad = _load("apply_depeval")
APPROVE = {"review_verdict": "APPROVE", "review_reasons": []}


def test_ready_needs_everything():
    p = ad.plan(APPROVE, "patch-or-minor", "success", True, [])
    assert p["label"] == "agent:ready-to-merge"


@pytest.mark.parametrize(
    "result,kind,gate,floors,failing,label",
    [
        (APPROVE, "major", "success", True, [], "agent:needs-human-review"),
        (APPROVE, "patch-or-minor", "success", False, ["coverage.min"], "agent:evaluation-failed"),
        (APPROVE, "patch-or-minor", "failure", True, [], "agent:evaluation-failed"),
        (None, "patch-or-minor", "success", True, [], "agent:needs-human-review"),
        (APPROVE, "patch-or-minor", "success", None, [], "agent:needs-human-review"),
        ({"review_verdict": "REQUEST CHANGES"}, "patch-or-minor", "success", True, [], "agent:needs-human-review"),
        (APPROVE, "grammar-or-parser", "success", True, [], "agent:bench-pending"),
        (APPROVE, "unknown", "success", True, [], "agent:needs-human-review"),
    ],
)
def test_every_weaker_combination(result, kind, gate, floors, failing, label):
    p = ad.plan(result, kind, gate, floors, failing)
    assert p["label"] == label, p


def test_floors_hold_reads_the_summary_rows(tmp_path):
    (tmp_path / "full.md").write_text(
        "| threshold | crit | floor | observed | verdict |\n|---|---|---|---|---|\n"
        "| `coverage.min` | N2 | >= 74 | 81 | PASS |\n| `suite.full_seconds` | N1 | <= 360 | 400 | FAIL |\n",
        encoding="utf-8",
    )
    ok, failing = ad.floors_hold(tmp_path)
    assert ok is False and failing == ["suite.full_seconds"]
    assert ad.floors_hold(tmp_path / "missing") == (None, [])
    (tmp_path / "full.md").write_text("no table here\n", encoding="utf-8")
    assert ad.floors_hold(tmp_path) == (None, [])


def test_comment_carries_marker_reasons_and_the_no_merge_line():
    p = ad.plan(APPROVE, "major", "success", True, [])
    body = ad.render_comment(p, {"review_verdict": "APPROVE", "review_reasons": ["fine"], "assessment": "Major bump."}, "major", "123", "o/r")
    assert body.startswith(ad.MARKER)
    assert "kind major" in body.replace("`", "") and "reviewer: fine" in body and "Major bump." in body
    assert "Nothing here merges" in body


def test_apply_edits_the_sticky_comment_and_swaps_outcome_labels(monkeypatch):
    calls = []

    def fake(args, repo, capture=False):
        calls.append(args)
        if args[0] == "api" and "comments" in args[1] and "--paginate" in args:
            return "555\n"
        return ""

    monkeypatch.setattr(ad, "_gh", fake)
    ad.apply({"label": "agent:ready-to-merge", "reasons": []}, "body", 9, "o/r")
    edit = calls[0]
    assert edit[:3] == ["pr", "edit", "9"] and "agent:ready-to-merge" in edit
    assert edit.count("--remove-label") == 3
    assert any(a[0] == "api" and "comments/555" in a[1] and "PATCH" in a for a in calls)
    assert not any(a[:2] == ["pr", "comment"] for a in calls)
