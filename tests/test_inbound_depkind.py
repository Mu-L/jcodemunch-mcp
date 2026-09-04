"""A Dependabot PR is classified from its lock delta AND its diff with no
model (POLICY rule 2). Red arms: a tree-sitter bump read as
patch-or-minor; a major bump read as patch-or-minor; a PR that touches
src/ read as anything but unknown; a version-pin change read as a
dependency update; a workflow diff that edits `permissions:` read as a
`uses:` bump; a pyproject diff that edits the sdist exclude read as a
dependency-table change (item-4 review, finding 3: the first draft
admitted whole files by name); a removed package read as patch-or-minor.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INBOUND = ROOT / ".github" / "inbound"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, INBOUND / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


dk = _load("depkind")


def _lock(**pkgs) -> str:
    return "\n".join(f'[[package]]\nname = "{k}"\nversion = "{v}"\n' for k, v in pkgs.items())


PYPROJECT_BEFORE = (
    '[project]\nname = "x"\nversion = "1.0.0"\ndependencies = [\n    "mcp>=1.10.0,<2.0.0",\n    "httpx>=0.27.0",\n]\n\n'
    '[project.optional-dependencies]\nwatch = ["watchfiles>=1.0.0"]\n\n'
    '[tool.hatch.build.targets.sdist]\nexclude = [".claude/"]\n'
)


def _diff(path: str, removed: list[str], added: list[str]) -> str:
    body = "".join(f"-{l}\n" for l in removed) + "".join(f"+{l}\n" for l in added)
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n{body}"


def test_lock_versions_reads_the_real_lock_shape():
    real = (ROOT / "uv.lock").read_text(encoding="utf-8")
    vs = dk.lock_versions(real)
    assert "tree-sitter" in vs and "mcp" in vs, sorted(vs)[:5]


def test_patch_or_minor():
    r = dk.classify(["uv.lock"], _lock(idna="3.11", mcp="1.26.0"), _lock(idna="3.15", mcp="1.28.1"))
    assert r["kind"] == "patch-or-minor" and len(r["bumps"]) == 2


def test_major_crossing():
    r = dk.classify(["uv.lock"], _lock(cryptography="46.0.5"), _lock(cryptography="48.0.1"))
    assert r["kind"] == "major" and "46.0.5 -> 48.0.1" in r["reasons"][0]


def test_new_package_is_major():
    r = dk.classify(["uv.lock"], _lock(a="1.0"), _lock(a="1.0", b="0.1"))
    assert r["kind"] == "major" and "new package b" in r["reasons"][0]


def test_removed_package_is_major():
    r = dk.classify(["uv.lock"], _lock(a="1.0", b="0.1"), _lock(a="1.0"))
    assert r["kind"] == "major" and "removed package b" in r["reasons"][0], "a removal is a shape POLICY rule 2 does not name; a human reads it"


def test_grammar_wins_over_everything():
    r = dk.classify(
        ["uv.lock"],
        _lock(cryptography="46.0.5", **{"tree-sitter-language-pack": "0.7.0"}),
        _lock(cryptography="48.0.1", **{"tree-sitter-language-pack": "0.9.0"}),
    )
    assert r["kind"] == "grammar-or-parser"
    assert any("tree-sitter-language-pack" in x for x in r["reasons"])


def test_a_file_outside_the_dependency_set_is_unknown():
    r = dk.classify(["uv.lock", "src/jcodemunch_mcp/server.py"], _lock(a="1"), _lock(a="2"))
    assert r["kind"] == "unknown" and "src/jcodemunch_mcp/server.py" in r["reasons"][0]


def test_pyproject_dependency_table_edit_is_admitted():
    after = PYPROJECT_BEFORE.replace('"httpx>=0.27.0",', '"httpx>=0.28.0",')
    diff = _diff("pyproject.toml", ['    "httpx>=0.27.0",'], ['    "httpx>=0.28.0",'])
    r = dk.classify(["pyproject.toml", "uv.lock"], _lock(httpx="0.27.0"), _lock(httpx="0.28.1"), diff, PYPROJECT_BEFORE, after)
    assert r["kind"] == "patch-or-minor", r


def test_pyproject_optional_dependency_edit_is_admitted():
    after = PYPROJECT_BEFORE.replace('watch = ["watchfiles>=1.0.0"]', 'watch = ["watchfiles>=1.1.0"]')
    diff = _diff("pyproject.toml", ['watch = ["watchfiles>=1.0.0"]'], ['watch = ["watchfiles>=1.1.0"]'])
    r = dk.classify(["pyproject.toml"], _lock(a="1"), _lock(a="1"), diff, PYPROJECT_BEFORE, after)
    assert r["kind"] == "patch-or-minor", r


def test_a_version_pin_change_is_unknown():
    after = PYPROJECT_BEFORE.replace('version = "1.0.0"', 'version = "1.0.1"')
    diff = _diff("pyproject.toml", ['version = "1.0.0"'], ['version = "1.0.1"'])
    r = dk.classify(["pyproject.toml"], _lock(a="1"), _lock(a="1"), diff, PYPROJECT_BEFORE, after)
    assert r["kind"] == "unknown" and "outside its dependency tables" in r["reasons"][0]


def test_the_sdist_exclude_is_not_a_dependency_table():
    """The v0.2.6 vector: a diff that edits `[tool.hatch.build.targets.sdist]`
    is not a dependency update whatever the file name says."""
    after = PYPROJECT_BEFORE.replace('exclude = [".claude/"]', "exclude = []")
    diff = _diff("pyproject.toml", ['exclude = [".claude/"]'], ["exclude = []"])
    r = dk.classify(["pyproject.toml"], _lock(a="1"), _lock(a="1"), diff, PYPROJECT_BEFORE, after)
    assert r["kind"] == "unknown", r


def test_pyproject_with_no_diff_to_inspect_is_unknown():
    r = dk.classify(["pyproject.toml"], _lock(a="1"), _lock(a="1"))
    assert r["kind"] == "unknown"


def test_workflow_uses_bump_is_allowed_and_patch_or_minor_with_no_lock_movement():
    diff = _diff(".github/workflows/pr-gate.yml",
                 ["      - uses: actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd  # v5"],
                 ["      - uses: actions/checkout@1111111111111111111111111111111111111111  # v6"])
    r = dk.classify([".github/workflows/pr-gate.yml"], _lock(a="1"), _lock(a="1"), diff)
    assert r["kind"] == "patch-or-minor"


def test_workflow_edit_outside_uses_is_unknown():
    diff = _diff(".github/workflows/pr-gate.yml", ["  contents: read"], ["  contents: write"])
    r = dk.classify([".github/workflows/pr-gate.yml"], _lock(a="1"), _lock(a="1"), diff)
    assert r["kind"] == "unknown" and "outside `uses:` pins" in r["reasons"][0]
    unpinned = _diff(".github/workflows/pr-gate.yml", ["      - uses: actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd"], ["      - uses: actions/checkout@v6"])
    assert dk.classify([".github/workflows/pr-gate.yml"], _lock(a="1"), _lock(a="1"), unpinned)["kind"] == "unknown", "a tag is not a 40-hex pin"
    assert dk.classify([".github/workflows/pr-gate.yml"], _lock(a="1"), _lock(a="1"))["kind"] == "unknown", "no diff to inspect"


def test_split_diff_keeps_only_changed_lines_per_file():
    d = _diff("a.txt", ["x"], ["y"]) + _diff("b.txt", [], ["z"])
    assert dk.split_diff(d) == {"a.txt": ["-x", "+y"], "b.txt": ["+z"]}
