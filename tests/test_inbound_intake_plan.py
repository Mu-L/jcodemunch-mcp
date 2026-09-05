"""Intake never re-queues a held or classified item, and never acts on an
edit or comment by anyone but the author (DESIGN section 1).

Red arms: a benign comment on an `inbound:security` item re-queuing it; a
stranger's comment re-queuing a `needs-human` item; an author edit
re-queuing an item already classified `inbound:question`.
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


ip = _load("intake_plan")
CLEAN = {"security_hit": False, "injection_hit": False}


def test_new_issue_is_queued():
    p = ip.plan(CLEAN, "issues", "opened", "alice", "alice", [])
    assert p["add"] == ["inbound:queued"] and p["outcome"] == "acted"


def test_security_hit_escalates_and_never_queues():
    p = ip.plan(
        {"security_hit": True, "injection_hit": True},
        "issues",
        "opened",
        "alice",
        "alice",
        [],
    )
    assert (
        p["add"] == ["inbound:security", "needs-human"]
        and "inbound:queued" in p["remove"]
    )


def test_injection_hit_escalates():
    p = ip.plan(
        {"security_hit": False, "injection_hit": True},
        "issues",
        "opened",
        "alice",
        "alice",
        [],
    )
    assert p["add"] == ["inbound:unknown", "needs-human", "inbound:injection-suspected"]


@pytest.mark.parametrize(
    "held", [["inbound:security"], ["needs-human"], ["inbound:question", "needs-human"]]
)
def test_a_held_item_is_never_touched(held):
    for event, action, actor in (
        ("issue_comment", "created", "bob"),
        ("issues", "edited", "alice"),
        ("issues", "reopened", "alice"),
    ):
        p = ip.plan(CLEAN, event, action, actor, "alice", held)
        assert p["add"] == [] and p["remove"] == [] and p["outcome"] == "skipped", (
            held,
            event,
            actor,
        )


def test_a_strangers_comment_or_edit_requeues_nothing():
    p = ip.plan(CLEAN, "issue_comment", "created", "bob", "alice", ["inbound:queued"])
    assert p["add"] == [] and p["outcome"] == "skipped"
    p = ip.plan(CLEAN, "issues", "edited", "bob", "alice", [])
    assert p["add"] == []


def test_an_author_edit_does_not_requeue_a_classified_item():
    p = ip.plan(
        CLEAN, "issues", "edited", "alice", "alice", ["inbound:question", "question"]
    )
    assert p["add"] == [] and "already classified" in p["reason"]


def test_an_author_edit_on_an_unclassified_item_queues_it():
    p = ip.plan(CLEAN, "issues", "edited", "alice", "alice", [])
    assert p["add"] == ["inbound:queued"]


def test_security_on_a_held_item_still_does_nothing_new():
    """A second security keyword on an already-held item adds nothing; the
    human already has it."""
    p = ip.plan(
        {"security_hit": True, "injection_hit": False},
        "issue_comment",
        "created",
        "bob",
        "alice",
        ["inbound:security", "needs-human"],
    )
    assert p["add"] == [] and p["outcome"] == "skipped"
