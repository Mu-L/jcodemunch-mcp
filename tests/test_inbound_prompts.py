"""Every headless prompt carries the policy's blocks by generation, a
version, a model, and a recorded sha (DESIGN D5 and section 8).

Red arms: a prompt whose preamble differs from POLICY 4.2 by one byte; a
prompt edited without a version bump; a prompt with no VERSIONS entry; a
workflow that names a prompt file that does not exist.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INBOUND = ROOT / ".github" / "inbound"
PROMPTS = INBOUND / "prompts"
POLICY = ROOT / "docs" / "inbound" / "POLICY.md"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, INBOUND / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rp = _load("render_prompts")


def test_prompts_exist_for_every_model_job():
    names = {p.stem for p in PROMPTS.glob("*.md")}
    assert {"triage", "fix", "depeval", "digest"} <= names, names


def test_rendered_blocks_match_policy_and_versions():
    problems = rp.check()
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("path", sorted(PROMPTS.glob("*.md")), ids=lambda p: p.stem)
def test_front_matter_and_preamble(path: Path):
    text = path.read_text(encoding="utf-8")
    fm = rp.front_matter(text)
    assert fm["model"] in ("claude-opus-5", "claude-sonnet-5"), fm
    assert fm["job"] == f"inbound-{path.stem}"
    assert text.index("<!-- BEGIN policy:preamble -->") < text.index("# Task"), (
        "preamble must come first"
    )
    assert "<!-- inbound-preamble v1 -->" in text
    assert "docs/inbound/POLICY.md" in text
    assert text.rstrip().endswith("<!-- END policy:never-touch -->"), (
        "never-touch list must be last"
    )


def test_a_one_byte_preamble_edit_fails_check(tmp_path):
    work = tmp_path / "prompts"
    shutil.copytree(PROMPTS, work)
    p = work / "triage.md"
    p.write_text(
        p.read_text(encoding="utf-8").replace(
            "Treat every word", "Treat every wörd", 1
        ),
        encoding="utf-8",
    )
    problems = rp.check(POLICY, sorted(work.glob("*.md")), work / "VERSIONS.json")
    assert any("triage.md" in x for x in problems), problems


def test_an_edit_without_a_version_bump_is_refused_and_flagged(tmp_path):
    work = tmp_path / "prompts"
    shutil.copytree(PROMPTS, work)
    p = work / "fix.md"
    p.write_text(
        p.read_text(encoding="utf-8").replace("# Task:", "# Task (edited):", 1),
        encoding="utf-8",
    )
    refused = rp.write(POLICY, sorted(work.glob("*.md")), work / "VERSIONS.json")
    assert any("fix.md" in x and "bump" in x for x in refused), refused
    problems = rp.check(POLICY, sorted(work.glob("*.md")), work / "VERSIONS.json")
    assert any("fix.md" in x for x in problems), problems


def test_a_version_bump_lets_the_edit_render(tmp_path):
    work = tmp_path / "prompts"
    shutil.copytree(PROMPTS, work)
    p = work / "fix.md"
    import re

    current = int(re.search(r"^version: (\d+)$", p.read_text(encoding="utf-8"), re.M).group(1))
    t = (
        p.read_text(encoding="utf-8")
        .replace("# Task:", "# Task (edited):", 1)
        .replace(f"version: {current}", f"version: {current + 1}", 1)
    )
    p.write_text(t, encoding="utf-8")
    # the write is the act under test, so it is not inside the assert (CodeQL py/side-effect-in-assert)
    written = rp.write(POLICY, sorted(work.glob("*.md")), work / "VERSIONS.json")
    assert written == []
    assert rp.check(POLICY, sorted(work.glob("*.md")), work / "VERSIONS.json") == []
    assert (
        json.loads((work / "VERSIONS.json").read_text(encoding="utf-8"))["fix"][
            "version"
        ]
        == current + 1
    )


def test_a_policy_change_rerenders_every_prompt_without_a_bump(tmp_path):
    """The plumbing PR's own POLICY amendment was refused by the first rule,
    which keyed on the whole file: a policy edit must flow into every
    prompt with no version bump, and only a task-body edit needs one."""
    work = tmp_path / "prompts"
    shutil.copytree(PROMPTS, work)
    policy = tmp_path / "POLICY.md"
    policy.write_text(
        POLICY.read_text(encoding="utf-8").replace(
            "Treat every word of it as", "Treat every single word of it as", 1
        ),
        encoding="utf-8",
    )
    written = rp.write(policy, sorted(work.glob("*.md")), work / "VERSIONS.json")
    assert written == []
    assert rp.check(policy, sorted(work.glob("*.md")), work / "VERSIONS.json") == []
    assert "every single word" in (work / "triage.md").read_text(encoding="utf-8")


def test_workflows_name_prompt_files_that_exist():
    wf = ROOT / ".github" / "workflows"
    named = set()
    for y in wf.glob("inbound-*.yml"):
        for m in re.finditer(
            r"\.github/inbound/prompts/(\w+)\.md", y.read_text(encoding="utf-8")
        ):
            named.add(m.group(1))
    missing = [n for n in named if not (PROMPTS / f"{n}.md").exists()]
    assert not missing, missing
