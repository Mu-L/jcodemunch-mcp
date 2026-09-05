"""The sweep posts only what a human approved, verbatim, and counts the
streak only for an unedited post (POLICY section 9, DESIGN section 6).

Red arms: `approved: True` (capitalised) posting; an App-authored approval
posting; an edited body incrementing the streak; a second sweep re-posting
a draft already moved to posted/.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
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


sweep = _load("sweep")
at = _load("apply_triage")


def _draft(
    tmp: Path,
    issue: int,
    body: str,
    approved: str | None = None,
    edit: str | None = None,
) -> Path:
    p = at.write_draft(
        {"issue": issue, "category": "question", "body": body}, tmp / "drafts", "r1"
    )
    text = p.read_text(encoding="utf-8")
    if approved is not None:
        text = text.replace("approved: false", f"approved: {approved}", 1)
    if edit is not None:
        # edit the shown body only; the original block stays
        text = text.replace(
            body + "\n\n<!-- original -->", edit + "\n\n<!-- original -->", 1
        )
    p.write_text(text, encoding="utf-8", newline="\n")
    return p


@pytest.mark.parametrize("value", [None, "True", "yes", "1", "approved"])
def test_only_literal_true_posts(tmp_path, value):
    p = _draft(tmp_path, 3, "An answer.", approved=value)
    d = sweep.parse_draft(p.read_text(encoding="utf-8"))
    assert sweep.decide(d, human=True)["action"] == "hold"


def test_human_approval_posts_unedited():
    d = {
        "front": {"approved": "true", "category": "question", "issue": "3"},
        "body": "An answer.",
        "original": "An answer.",
    }
    v = sweep.decide(d, human=True)
    assert v == {"action": "post", "edited": False, "category": "question", "issue": 3}


def test_app_approval_never_posts():
    d = {
        "front": {"approved": "true", "category": "question", "issue": "3"},
        "body": "x",
        "original": "x",
    }
    assert sweep.decide(d, human=False)["action"] == "hold"


def test_edited_body_posts_but_is_marked_edited():
    d = {
        "front": {"approved": "true", "category": "question", "issue": "3"},
        "body": "An answer, fixed.",
        "original": "An answer.",
    }
    v = sweep.decide(d, human=True)
    assert v["action"] == "post" and v["edited"] is True


def test_streak_counts_unedited_and_resets_on_edit():
    s = {}
    s = sweep.update_streaks(s, "question", edited=False)
    s = sweep.update_streaks(s, "question", edited=False)
    assert s["question"]["count"] == 2
    s = sweep.update_streaks(s, "question", edited=True)
    assert (
        s["question"]["count"] == 0
        and s["question"]["reset_reason"] == "edited before post"
    )
    assert sweep.update_streaks({}, "security", edited=False) == {}, (
        "security never graduates"
    )


def test_parse_draft_reads_front_matter_and_original(tmp_path):
    p = _draft(tmp_path, 9, "Body text.")
    d = sweep.parse_draft(p.read_text(encoding="utf-8"))
    assert d["front"]["issue"] == "9" and d["front"]["approved"] == "false"
    assert d["body"] == "Body text." and d["original"] == "Body text."


def test_approver_is_human_reads_the_last_commit(tmp_path):
    led = tmp_path / "led"
    led.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=led, check=True)
    p = _draft(led, 4, "x", approved="true")
    subprocess.run(["git", "add", "-A"], cwd=led, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=jcodemunch-inbound[bot]",
            "-c",
            "user.email=b@x",
            "commit",
            "-q",
            "-m",
            "app",
        ],
        cwd=led,
        check=True,
    )
    ok, who = sweep.approver_is_human(p, led, "jcodemunch-inbound[bot]")
    assert ok is False and "bot" in who
    p.write_text(p.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=jgravelle",
            "-c",
            "user.email=j@x",
            "commit",
            "-qam",
            "approve",
        ],
        cwd=led,
        check=True,
    )
    ok, who = sweep.approver_is_human(p, led, "jcodemunch-inbound[bot]")
    assert ok is True and "jgravelle" in who


def test_post_approved_moves_the_file_and_never_posts_twice(tmp_path, monkeypatch):
    led = tmp_path / "led"
    (led / "drafts").mkdir(parents=True)
    _draft(led, 5, "Answer five.", approved="true")
    _draft(led, 6, "Answer six.")  # not approved
    monkeypatch.setattr(sweep, "approver_is_human", lambda *a, **k: (True, "jgravelle"))
    posted = []
    monkeypatch.setattr(sweep, "_gh", lambda args, repo: posted.append(args))
    r1 = sweep.post_approved(led, "o/r", "app[bot]", apply=True)
    assert [x["action"] for x in r1] == ["post", "hold"]
    assert len(posted) == 1 and posted[0][:3] == ["issue", "comment", "5"]
    assert (led / "drafts" / "posted" / "5-r1.md").exists() and not (
        led / "drafts" / "5-r1.md"
    ).exists()
    assert (
        json.loads((led / "streaks.json").read_text(encoding="utf-8"))["question"][
            "count"
        ]
        == 1
    )
    r2 = sweep.post_approved(led, "o/r", "app[bot]", apply=True)
    assert [x["action"] for x in r2] == ["hold"] and len(posted) == 1


def test_ingest_never_overwrites_a_draft_a_human_touched(tmp_path):
    """Item-3 review, finding 1: the artifact window is two days, so the
    same artifact reaches two sweeps; re-copying it would revert
    `approved: true` or re-create a posted draft."""
    art = tmp_path / "artifacts" / "draft-1-7"
    art.mkdir(parents=True)
    (art / "7-r1.md").write_text(
        "---\nissue: 7\ncategory: question\napproved: false\n---\nA.\n",
        encoding="utf-8",
    )
    led = tmp_path / "led"
    first = sweep.ingest_drafts(tmp_path / "artifacts", led)
    assert first == {"added": ["7-r1.md"], "skipped_existing": []}
    target = led / "drafts" / "7-r1.md"
    target.write_text(
        target.read_text(encoding="utf-8").replace("approved: false", "approved: true"),
        encoding="utf-8",
    )
    second = sweep.ingest_drafts(tmp_path / "artifacts", led)
    assert second == {"added": [], "skipped_existing": ["7-r1.md"]}
    assert "approved: true" in target.read_text(encoding="utf-8")
    target.rename(led / "drafts" / "posted" / "7-r1.md")
    third = sweep.ingest_drafts(tmp_path / "artifacts", led)
    assert third["added"] == [] and not (led / "drafts" / "7-r1.md").exists()


def test_ingest_reads_only_draft_artifacts(tmp_path):
    other = tmp_path / "artifacts" / "inbound-audit-9"
    other.mkdir(parents=True)
    (other / "note.md").write_text("not a draft", encoding="utf-8")
    assert sweep.ingest_drafts(tmp_path / "artifacts", tmp_path / "led")["added"] == []


def test_one_malformed_draft_holds_itself_only(tmp_path, monkeypatch):
    led = tmp_path / "led"
    (led / "drafts").mkdir(parents=True)
    (led / "drafts" / "bad.md").write_text(
        "---\napproved: true\n---\nno issue key\n", encoding="utf-8"
    )
    _draft(led, 8, "Answer eight.", approved="true")
    monkeypatch.setattr(sweep, "approver_is_human", lambda *a, **k: (True, "jgravelle"))
    posted = []
    monkeypatch.setattr(sweep, "_gh", lambda args, repo: posted.append(args))
    r = sweep.post_approved(led, "o/r", "app[bot]", apply=True)
    by = {x["file"]: x for x in r}
    assert by["bad.md"]["action"] == "hold" and "KeyError" in by["bad.md"]["reason"]
    assert by["8-r1.md"]["action"] == "post" and len(posted) == 1


def test_the_summary_is_written_into_a_directory_that_does_not_exist_yet(tmp_path, monkeypatch):
    """Third live sweep (2026-09-05, run 33941021629): every step of the
    work succeeded and the run failed writing `--summary` into
    `$RUNNER_TEMP/audit/`, a directory only a DECLINE creates. The first
    sweep to pass its gate was the first with nowhere to write."""
    import subprocess as sp
    monkeypatch.setattr(sweep.subprocess, "run", lambda *a, **k: sp.CompletedProcess(a, 1, stdout="", stderr="no gh here"))
    ledger = tmp_path / "ledger"
    (ledger / "ledger").mkdir(parents=True)
    (tmp_path / "artifacts").mkdir()
    out = tmp_path / "audit" / "deeper" / "sweep-summary.json"
    rc = sweep.main(["--ledger-dir", str(ledger), "--artifacts-dir", str(tmp_path / "artifacts"), "--repo", "o/r", "--app-login", "x", "--summary", str(out)])
    assert rc == 0 and out.exists(), out
    assert json.loads(out.read_text(encoding="utf-8"))["ledger_rows_added"] == 0
