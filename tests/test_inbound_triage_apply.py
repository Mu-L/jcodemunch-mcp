"""The triage plan can never exceed POLICY section 2 for its category and
confidence, whatever the model returned (DESIGN section 2).

Red arms: a `medium` question producing a draft; a `low` anything
producing more than unknown + needs-human; a security result with any
comment or human label; a duplicate without `duplicate_of`; the owner's own
issue getting a draft; a malformed result being acted on as if classified.
"""

from __future__ import annotations

import importlib.util
import json
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


at = _load("apply_triage")


def _r(**kw):
    base = {
        "issue": 42,
        "category": "question",
        "confidence": "high",
        "evidence": ["how do I x?"],
    }
    base.update(kw)
    return base


def test_high_question_from_a_stranger_drafts_and_labels_only():
    p = at.plan(
        _r(draft="See docs/CONFIGURATION.md section 3."), "someone", "jgravelle"
    )
    assert p["add"] == ["inbound:question", "question"]
    assert p["remove"] == ["inbound:queued"]
    assert p["comment"] is None
    assert p["draft"]["body"].startswith("See docs/")


@pytest.mark.parametrize("conf", ["medium", "low"])
def test_below_high_never_drafts_or_comments(conf):
    p = at.plan(_r(confidence=conf, draft="an answer"), "someone", "jgravelle")
    assert p["comment"] is None and p["draft"] is None
    assert "needs-human" in p["add"]
    if conf == "low":
        assert p["add"] == ["inbound:unknown", "needs-human"]
    else:
        assert p["add"] == ["inbound:question", "needs-human"]


@pytest.mark.parametrize("conf", ["high", "medium", "low"])
def test_security_is_label_and_needs_human_only_at_every_confidence(conf):
    p = at.plan(
        _r(category="security", confidence=conf, draft="do not post me"),
        "someone",
        "jgravelle",
    )
    assert p["add"] == ["inbound:security", "needs-human"]
    assert p["comment"] is None and p["draft"] is None


def test_duplicate_high_is_the_one_unattended_comment():
    p = at.plan(
        _r(
            category="duplicate",
            duplicate_of=7,
            evidence=["first sentence", "second sentence", "third"],
        ),
        "someone",
        "jgravelle",
    )
    assert p["comment"]["issue_to"] == 42
    assert "#7" in p["comment"]["body"] and "third" not in p["comment"]["body"]
    assert "close" in p["comment"]["body"].lower() and p["draft"] is None
    assert "duplicate" not in p["add"], (
        "the human `duplicate` label implies a verdict and is never applied"
    )


def test_duplicate_without_a_target_is_a_schema_error():
    with pytest.raises(at.SchemaError):
        at.plan(_r(category="duplicate"), "someone", "jgravelle")


def test_owner_issues_get_labels_only():
    p = at.plan(_r(draft="an answer"), "JGravelle", "jgravelle")
    assert p["draft"] is None and p["comment"] is None
    assert p["add"] == ["inbound:question", "question"]


def test_unknown_high_adds_needs_human():
    p = at.plan(_r(category="unknown"), "someone", "jgravelle")
    assert p["add"] == ["inbound:unknown", "needs-human"]


@pytest.mark.parametrize(
    "bad",
    [
        {"issue": 1, "category": "bug", "confidence": "high", "evidence": []},
        {"issue": 1, "category": "feature", "confidence": "certain", "evidence": []},
        {
            "issue": 1,
            "category": "feature",
            "confidence": "high",
            "evidence": ["a", "b", "c", "d"],
        },
        {"category": "feature", "confidence": "high", "evidence": []},
    ],
)
def test_schema_violations_are_refused(bad):
    with pytest.raises(at.SchemaError):
        at.plan(bad, "someone", "jgravelle")


def test_malformed_result_file_escalates_and_applies_nothing(
    tmp_path, capsys, monkeypatch
):
    called = []
    monkeypatch.setattr(at, "apply", lambda *a, **k: called.append(a))
    f = tmp_path / "r.json"
    f.write_text("{not json", encoding="utf-8")
    rc = at.main(
        [
            str(f),
            "--author",
            "x",
            "--owner",
            "o",
            "--repo",
            "o/r",
            "--drafts-dir",
            str(tmp_path / "d"),
            "--run-id",
            "1",
            "--apply",
        ]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["add"] == ["inbound:unknown", "needs-human"] and "error" in out
    assert called == [], "a malformed result must not reach gh"


def test_draft_file_carries_approval_fields_and_the_original(tmp_path):
    p = at.write_draft(
        {"issue": 5, "category": "feature", "body": "Assessment.\n"}, tmp_path, "99"
    )
    text = p.read_text(encoding="utf-8")
    assert text.startswith("---\nissue: 5\n")
    assert "approved: false" in text and "edited: false" in text
    assert text.count("Assessment.") == 2 and "<!-- original -->" in text
    assert p.name == "5-99.md"
