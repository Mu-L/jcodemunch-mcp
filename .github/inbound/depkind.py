"""Classify a Dependabot PR with no model (docs/inbound/POLICY.md section 1
rule 2; DESIGN section 4).

purpose:  decide `grammar-or-parser`, `major`, `patch-or-minor`, or
          `unknown` from the PR's file list and the before/after lock file
invokes:  nothing outside the standard library; the caller hands it the
          diff's file list and the two `uv.lock` texts
produces: JSON {kind, bumps: [{name, before, after}], reasons}
refuses:  to classify a PR whose diff touches any file outside `uv.lock`,
          the dependency tables of `pyproject.toml`, or `uses:` lines of
          workflow files (that is `unknown`, POLICY rule 2)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ALLOWED_FILES = re.compile(r"^(uv\.lock|pyproject\.toml|\.github/workflows/[^/]+\.ya?ml)$")
GRAMMAR = re.compile(r"^tree[-_]sitter", re.I)

_PKG = re.compile(r'^\[\[package\]\]\nname = "([^"]+)"\nversion = "([^"]+)"', re.M)


def lock_versions(lock_text: str) -> dict[str, str]:
    return {m.group(1).lower(): m.group(2) for m in _PKG.finditer(lock_text.replace("\r\n", "\n"))}


def _major(v: str) -> int | None:
    m = re.match(r"(\d+)", v)
    return int(m.group(1)) if m else None


def bumps(before: dict[str, str], after: dict[str, str]) -> list[dict]:
    out = []
    for name in sorted(set(before) | set(after)):
        b, a = before.get(name), after.get(name)
        if b != a:
            out.append({"name": name, "before": b, "after": a})
    return out


def classify(files: list[str], before_lock: str, after_lock: str, pyproject_diff: str = "") -> dict:
    reasons = []
    bad = [f for f in files if not ALLOWED_FILES.match(f)]
    if bad:
        return {"kind": "unknown", "bumps": [], "reasons": [f"touches non-dependency files: {bad}"]}
    if pyproject_diff and re.search(r"^[+-]\s*version\s*=", pyproject_diff, re.M):
        return {"kind": "unknown", "bumps": [], "reasons": ["pyproject.toml [project].version changed"]}
    changes = bumps(lock_versions(before_lock), lock_versions(after_lock))
    if not changes and any(f == "uv.lock" for f in files):
        reasons.append("uv.lock changed with no package version movement (markers or hashes only)")
    if any(GRAMMAR.match(c["name"]) for c in changes):
        return {"kind": "grammar-or-parser", "bumps": changes,
                "reasons": [f"moves {c['name']}" for c in changes if GRAMMAR.match(c["name"])]}
    majors = [c for c in changes if c["before"] and c["after"] and _major(c["before"]) != _major(c["after"])]
    added = [c for c in changes if c["before"] is None]
    if majors or added:
        return {"kind": "major", "bumps": changes,
                "reasons": [f"{c['name']}: {c['before']} -> {c['after']}" for c in majors] + [f"new package {c['name']}" for c in added]}
    return {"kind": "patch-or-minor", "bumps": changes, "reasons": reasons or ["every bump stays within its major"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--files", type=Path, required=True, help="newline-separated changed paths")
    ap.add_argument("--before", type=Path, required=True, help="uv.lock at the base")
    ap.add_argument("--after", type=Path, required=True, help="uv.lock at the head")
    ap.add_argument("--pyproject-diff", type=Path, default=None)
    args = ap.parse_args(argv)
    files = [x.strip() for x in args.files.read_text(encoding="utf-8").splitlines() if x.strip()]
    pd = args.pyproject_diff.read_text(encoding="utf-8") if args.pyproject_diff and args.pyproject_diff.exists() else ""
    res = classify(files, args.before.read_text(encoding="utf-8"), args.after.read_text(encoding="utf-8"), pd)
    print(json.dumps(res, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
