"""A Dependabot PR is classified from its lock delta with no model
(POLICY rule 2). Red arms: a tree-sitter bump read as patch-or-minor; a
major bump read as patch-or-minor; a PR that touches src/ read as anything
but unknown; a version-pin change read as a dependency update.
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


def test_grammar_wins_over_everything():
    r = dk.classify(
        ["uv.lock", "pyproject.toml"],
        _lock(cryptography="46.0.5", **{"tree-sitter-language-pack": "0.7.0"}),
        _lock(cryptography="48.0.1", **{"tree-sitter-language-pack": "0.9.0"}),
    )
    assert r["kind"] == "grammar-or-parser"
    assert any("tree-sitter-language-pack" in x for x in r["reasons"])


def test_a_file_outside_the_dependency_set_is_unknown():
    r = dk.classify(["uv.lock", "src/jcodemunch_mcp/server.py"], _lock(a="1"), _lock(a="2"))
    assert r["kind"] == "unknown" and "src/jcodemunch_mcp/server.py" in r["reasons"][0]


def test_a_version_pin_change_is_unknown():
    r = dk.classify(["pyproject.toml"], _lock(a="1"), _lock(a="1"), pyproject_diff='-version = "1.108.317"\n+version = "1.108.318"\n')
    assert r["kind"] == "unknown"


def test_workflow_uses_bump_is_allowed_and_patch_or_minor_with_no_lock_movement():
    r = dk.classify([".github/workflows/pr-gate.yml"], _lock(a="1"), _lock(a="1"))
    assert r["kind"] == "patch-or-minor"
