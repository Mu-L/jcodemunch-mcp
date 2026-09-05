"""`agent:ready-to-merge` needs every input green; every other combination
is a weaker label (POLICY section 2, dependency rows).

Red arms: a major bump with APPROVE labelled ready; a Floor FAIL with
APPROVE labelled ready; a missing result labelled ready; a grammar bump
labelled anything but bench-pending / needs-human; a second run posting a
second comment instead of editing the sticky one; the bench's appended
table replacing the sticky comment's text (item-4 review, finding 2); the
model's assessment appearing in the comment (finding 6); a Floor table
read from summary files the gate never uploads instead of its job log
(finding 1).
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

# Two real lines from a PR-gate job log (`gh run view --log`): job, step,
# timestamp, then the harness's verdict line.
LOG = (
    "fast: harness fast tier\tFast tier\t2026-09-04T19:28:31.2479398Z suite.fast_skips_max                     crit N7  floor <= 15           observed 9            PASS\n"
    "fast: harness fast tier\tFast tier\t2026-09-04T19:28:31.2498278Z coverage.min                             crit N2  floor >= 74           delegated to pytest --cov-fail-under (full tier)\n"
    "full: test (ubuntu-latest, 3.12)\tFull tier\t2026-09-04T19:40:00.0000000Z suite.full_seconds                       crit N1  floor <= 360          observed 400          FAIL\n"
)


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


def test_floors_hold_reads_the_gate_job_log(tmp_path):
    """The PR gate writes its summaries to the step summary, never to an
    artifact; the verdict lines live in the job log."""
    (tmp_path / "run.log").write_text(LOG, encoding="utf-8")
    ok, failing = ad.floors_hold(tmp_path)
    assert ok is False and failing == ["suite.full_seconds"]
    assert ad.verdict_rows(LOG) == [("suite.fast_skips_max", "PASS"), ("suite.full_seconds", "FAIL")], "the delegated line is not a verdict"
    (tmp_path / "run.log").write_text(LOG.replace("observed 400          FAIL", "observed 300          PASS"), encoding="utf-8")
    assert ad.floors_hold(tmp_path) == (True, [])


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
    result = {"review_verdict": "APPROVE", "review_reasons": ["fine"], "assessment": "MODEL PROSE HERE."}
    body = ad.render_comment(p, result, "major", "123", "o/r", draft_written=True)
    assert body.startswith(ad.MARKER)
    assert "kind major" in body.replace("`", "") and "reviewer: fine" in body
    assert "MODEL PROSE HERE" not in body, "the assessment is a draft for a human, never posted"
    assert "awaits approval" in body and "Nothing here merges" in body


def test_assessment_becomes_a_draft_file_in_the_triage_format(tmp_path):
    result = {"review_verdict": "APPROVE", "assessment": "Major bump; the changelog names a removed API."}
    p = ad.write_assessment_draft(result, "major", 77, tmp_path / "drafts", "r9")
    assert p and Path(p).name == "77-r9.md"
    text = Path(p).read_text(encoding="utf-8")
    assert "approved: false" in text and "category: dependency" in text and "<!-- original -->" in text
    assert ad.write_assessment_draft(result, "patch-or-minor", 77, tmp_path / "drafts", "r9") is None
    assert ad.write_assessment_draft({"review_verdict": "APPROVE"}, "major", 77, tmp_path / "drafts", "r9") is None


def _fake_gh(calls, sticky_id="555", sticky_body=None):
    def fake(args, repo, capture=False):
        calls.append(args)
        if args[0] == "api" and args[1].endswith("/comments") and "--paginate" in args:
            return f"{sticky_id}\n" if sticky_id else ""
        if args[0] == "api" and f"/comments/{sticky_id}" in args[1] and "--jq" in args:
            return (sticky_body or "") + "\n"
        return ""
    return fake


def test_apply_edits_the_sticky_comment_and_swaps_outcome_labels(monkeypatch):
    calls = []
    monkeypatch.setattr(ad, "_gh", _fake_gh(calls))
    ad.apply({"label": "agent:ready-to-merge", "reasons": []}, "body", 9, "o/r")
    edit = calls[0]
    assert edit[:3] == ["pr", "edit", "9"] and "agent:ready-to-merge" in edit
    assert edit.count("--remove-label") == 3
    assert any(a[0] == "api" and "comments/555" in a[1] and "PATCH" in a for a in calls)
    assert not any(a[:2] == ["pr", "comment"] for a in calls)


def test_append_table_keeps_the_sticky_comment_it_appends_to(monkeypatch):
    """Item-4 review, finding 2: the first draft split a tab-joined jq line
    on its first newline and PATCHed marker + table over the reasons."""
    calls = []
    existing = ad.MARKER + "\n**Inbound dependency evaluation**: kind `grammar-or-parser`\n\n- reviewer: fine\n- kind grammar-or-parser"
    monkeypatch.setattr(ad, "_gh", _fake_gh(calls, sticky_body=existing))
    ad.append_table("| a | b |\n|---|---|\n| 1 | 2 |", 9, "o/r")
    patch = next(a for a in calls if a[0] == "api" and "PATCH" in a)
    body = patch[patch.index("-f") + 1]
    assert body.startswith("body=" + existing), body[:120]
    assert "- reviewer: fine" in body and "| 1 | 2 |" in body and "Full-corpus benchmark" in body
    assert not any(a[:2] == ["pr", "comment"] for a in calls)


def test_append_table_with_no_sticky_comment_creates_one(monkeypatch):
    calls = []
    monkeypatch.setattr(ad, "_gh", _fake_gh(calls, sticky_id=None))
    ad.append_table("| a |", 9, "o/r")
    post = next(a for a in calls if a[:2] == ["pr", "comment"])
    assert post[post.index("--body") + 1].startswith(ad.MARKER)


def test_gh_api_calls_carry_no_repo_flag(monkeypatch):
    seen = []
    monkeypatch.setattr(ad.subprocess, "run", lambda cmd, **k: seen.append(cmd) or type("P", (), {"stdout": ""})())
    ad._gh(["api", "repos/o/r/issues/1/comments"], "o/r", capture=True)
    ad._gh(["pr", "edit", "1"], "o/r")
    assert "-R" not in seen[0] and seen[1][-2:] == ["-R", "o/r"]
