"""The fix job's two no-model gates (DESIGN section 3): the pre-flight
that declines a run before it starts, and the publish gate that decides
from the hand-over alone whether the App may push and open the draft.

Red arms: a bot-applied label with INBOUND_AUTOFIX unset proceeding; an
`agent:reverted` issue proceeding; a merged revert newer than the last
human label proceeding; an UNKNOWN account age proceeding; a bundle whose
first commit touches src/ publishing; a bundle touching `.claude/`
publishing; a body without `Closes #<n>` publishing; a branch off the
`inbound/fix-<n>-` shape publishing.
"""

from __future__ import annotations

import importlib.util
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


fp = _load("fix_preflight")
pub = _load("fix_publish")
sc = _load("selfcheck")

PATTERNS = sc.never_touch_patterns((ROOT / "docs" / "inbound" / "POLICY.md").read_text(encoding="utf-8"))
HEADINGS = sc.template_headings((ROOT / "docs" / "inbound" / "DESIGN.md").read_text(encoding="utf-8"))
GOOD_BODY = "\n".join(HEADINGS) + "\n\nCloses #12\n"
GOOD_COMMITS = [{"sha": "a" * 40, "files": ["tests/test_x.py"]}, {"sha": "b" * 40, "files": ["src/x.py", "CHANGELOG.md"]}]


# ---- pre-flight -----------------------------------------------------------

def test_human_label_on_a_clean_issue_proceeds():
    ok, reasons = fp.decide([], True, None, None, None, None, None)
    assert ok and reasons == []


def test_bot_label_needs_autofix_true_and_a_known_established_author():
    ok, reasons = fp.decide([], False, None, 400, True, None, None)
    assert not ok and any("INBOUND_AUTOFIX" in r for r in reasons)
    ok, reasons = fp.decide([], False, "true", 400, True, None, None)
    assert ok, reasons
    ok, reasons = fp.decide([], False, "true", 10, True, None, None)
    assert not ok and any("account age" in r for r in reasons)
    ok, reasons = fp.decide([], False, "true", None, None, None, None)
    assert not ok and len(reasons) == 2, "UNKNOWN age and UNKNOWN activity both block"


@pytest.mark.parametrize("label", fp.BLOCKING)
def test_blocking_labels_block_even_for_a_human(label):
    ok, reasons = fp.decide([label], True, None, None, None, None, None)
    assert not ok and reasons == [f"issue carries {label}"]


def test_a_merged_revert_blocks_unless_a_human_relabelled_after_it():
    ok, _ = fp.decide([], True, None, None, None, "2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z")
    assert not ok
    ok, _ = fp.decide([], True, None, None, None, "2026-09-03T00:00:00Z", "2026-09-02T00:00:00Z")
    assert ok
    ok, _ = fp.decide([], True, None, None, None, None, "2026-09-02T00:00:00Z")
    assert not ok, "no human label at all after a revert"


# ---- publish gate -----------------------------------------------------------

def test_a_clean_handover_publishes():
    assert pub.decide("inbound/fix-12-cache", 12, GOOD_COMMITS, "", GOOD_BODY, PATTERNS, HEADINGS) == []


@pytest.mark.parametrize("branch", ["fix/12-cache", "inbound/fix-13-cache", "inbound/fix-12", "main", ""])
def test_the_branch_shape_is_enforced(branch):
    r = pub.decide(branch, 12, GOOD_COMMITS, "", GOOD_BODY, PATTERNS, HEADINGS)
    assert any("inbound/fix-12-<slug>" in x for x in r), r


def test_src_before_the_test_commit_refuses():
    r = pub.decide("inbound/fix-12-c", 12, list(reversed(GOOD_COMMITS)), "", GOOD_BODY, PATTERNS, HEADINGS)
    assert any("before the first test commit" in x for x in r), r


@pytest.mark.parametrize("path", [".claude/settings.json", ".github/workflows/pr-gate.yml", "harness/thresholds.json", "docs/harness/ARCHAEOLOGY.md", "SECURITY.md"])
def test_a_never_touch_path_in_any_commit_refuses(path):
    commits = [GOOD_COMMITS[0], {"sha": "b" * 40, "files": ["src/x.py", path]}]
    r = pub.decide("inbound/fix-12-c", 12, commits, "", GOOD_BODY, PATTERNS, HEADINGS)
    assert any("never-touch" in x and path in x for x in r), r


def test_the_version_pin_refuses():
    r = pub.decide("inbound/fix-12-c", 12, GOOD_COMMITS, '-version = "1.0"\n+version = "1.1"\n', GOOD_BODY, PATTERNS, HEADINGS)
    assert any("[project].version" in x for x in r)


def test_the_body_needs_every_heading_and_the_closes_line():
    r = pub.decide("inbound/fix-12-c", 12, GOOD_COMMITS, "", "\n".join(HEADINGS[:-1]) + "\nCloses #12", PATTERNS, HEADINGS)
    assert any("## Audit" in x for x in r)
    r = pub.decide("inbound/fix-12-c", 12, GOOD_COMMITS, "", "\n".join(HEADINGS) + "\nCloses #13", PATTERNS, HEADINGS)
    assert any("Closes #12" in x for x in r)


def test_bundle_commits_reads_a_real_bundle_on_top_of_main(tmp_path, monkeypatch):
    """A repo with `main`, a branch of two commits, bundled; the gate lists
    them oldest first with their files, and refuses a bundle whose branch
    is not on top of main."""
    repo = tmp_path / "r"
    repo.mkdir()
    run = lambda *a, **k: subprocess.run(["git", *a], cwd=k.get("cwd", repo), check=True, capture_output=True, text=True)
    run("init", "-q", "-b", "main")
    run("-c", "user.name=t", "-c", "user.email=t@x", "commit", "-q", "--allow-empty", "-m", "base")
    run("checkout", "-q", "-b", "inbound/fix-12-c")
    (repo / "tests").mkdir(); (repo / "tests" / "test_x.py").write_text("def test_x(): assert 0\n", encoding="utf-8")
    run("add", "-A"); run("-c", "user.name=t", "-c", "user.email=t@x", "commit", "-q", "-m", "red")
    (repo / "src").mkdir(); (repo / "src" / "x.py").write_text("x = 1\n", encoding="utf-8")
    run("add", "-A"); run("-c", "user.name=t", "-c", "user.email=t@x", "commit", "-q", "-m", "fix")
    bundle = tmp_path / "fix.bundle"
    run("bundle", "create", str(bundle), "main..inbound/fix-12-c")
    monkeypatch.setattr(pub, "ROOT", repo)
    head, commits, err = pub.bundle_commits(bundle, "main")
    assert err is None and len(commits) == 2
    assert commits[0]["files"] == ["tests/test_x.py"] and commits[1]["files"] == ["src/x.py"]
    assert pub.decide("inbound/fix-12-c", 12, commits, "", GOOD_BODY, PATTERNS, HEADINGS) == []
    # main moves on; the same bundle is no longer on top of it
    run("checkout", "-q", "main")
    run("-c", "user.name=t", "-c", "user.email=t@x", "commit", "-q", "--allow-empty", "-m", "moved")
    _, commits2, err2 = pub.bundle_commits(bundle, "main")
    assert err2 and "not on top of main" in err2 and commits2 == []
