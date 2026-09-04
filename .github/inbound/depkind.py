"""Classify a Dependabot PR with no model (docs/inbound/POLICY.md section 1
rule 2; DESIGN section 4).

purpose:  decide `grammar-or-parser`, `major`, `patch-or-minor`, or
          `unknown` from the PR's file list, the before/after lock file
          and the diff itself
invokes:  nothing outside the standard library; the caller hands it the
          diff's file list, the two `uv.lock` texts and the unified diff
produces: JSON {kind, bumps: [{name, before, after}], reasons}
refuses:  to classify a PR whose diff touches any file outside `uv.lock`,
          the dependency tables of `pyproject.toml`, or `uses:` lines of
          workflow files (that is `unknown`, POLICY rule 2). The diff is
          inspected line by line: a `pyproject.toml` hunk outside a
          dependency table, or a workflow line that is not a `uses:` pin,
          is `unknown` even though the file name is admitted (item-4
          review, finding 3: the first draft admitted the whole file)
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

# The pyproject tables a dependency update may touch (PEP 621 / PEP 735).
DEPENDENCY_TABLES = ("project.optional-dependencies", "dependency-groups", "build-system")
# Inside [project], only the `dependencies = [...]` array.
_USES = re.compile(r"^\s*-?\s*uses:\s*\S+@[0-9a-f]{40}(\s+#.*)?$")


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


def split_diff(diff: str) -> dict[str, list[str]]:
    """{path: [changed lines with their +/- sign]} from a unified diff;
    hunk headers, file headers and context lines are dropped."""
    out: dict[str, list[str]] = {}
    path = None
    for line in diff.replace("\r\n", "\n").split("\n"):
        m = re.match(r"^diff --git a/(\S+) b/(\S+)", line)
        if m:
            path = m.group(2)
            out.setdefault(path, [])
            continue
        if path is None or line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith(("+", "-")):
            out[path].append(line)
    return out


def dependency_table_lines(text: str) -> set[str]:
    """The raw lines of a pyproject text that sit inside a dependency
    table: `[project]`'s `dependencies = [...]` array, every
    `[project.optional-dependencies*]` table, `[dependency-groups]`,
    `[build-system]`."""
    allowed: set[str] = set()
    table = None
    in_deps_array = False
    for raw in text.replace("\r\n", "\n").split("\n"):
        s = raw.strip()
        m = re.match(r"^\[([^\]]+)\]$", s)
        if m:
            table = m.group(1)
            in_deps_array = False
            continue
        if table == "project" and re.match(r"^dependencies\s*=\s*\[", s):
            in_deps_array = not s.endswith("]")
            allowed.add(raw)
            continue
        if table == "project" and in_deps_array:
            allowed.add(raw)
            if s.startswith("]"):
                in_deps_array = False
            continue
        if table in DEPENDENCY_TABLES or (table and table.startswith("project.optional-dependencies")):
            allowed.add(raw)
    return allowed


def pyproject_changes_outside_dependency_tables(before_text: str, after_text: str, changed: list[str]) -> list[str]:
    """An added line must exist inside a dependency table of the AFTER
    text; a removed line must have existed inside one of the BEFORE text.
    Anything else (a version pin, an sdist exclude, a script entry) is
    named."""
    before_ok = dependency_table_lines(before_text)
    after_ok = dependency_table_lines(after_text)
    bad = []
    for line in changed:
        body = line[1:]
        ok = after_ok if line.startswith("+") else before_ok
        if body not in ok:
            bad.append(line)
    return bad


def workflow_changes_outside_uses(changed: list[str]) -> list[str]:
    return [line for line in changed if not _USES.match(line[1:])]


def classify(files: list[str], before_lock: str, after_lock: str, diff: str = "", before_pyproject: str = "", after_pyproject: str = "") -> dict:
    reasons = []
    bad = [f for f in files if not ALLOWED_FILES.match(f)]
    if bad:
        return {"kind": "unknown", "bumps": [], "reasons": [f"touches non-dependency files: {bad}"]}
    per_file = split_diff(diff) if diff else {}
    if "pyproject.toml" in files:
        if not diff or not after_pyproject or not before_pyproject:
            return {"kind": "unknown", "bumps": [], "reasons": ["pyproject.toml changed and no diff or before/after text was given to inspect"]}
        outside = pyproject_changes_outside_dependency_tables(before_pyproject, after_pyproject, per_file.get("pyproject.toml", []))
        if outside:
            return {"kind": "unknown", "bumps": [], "reasons": [f"pyproject.toml changed outside its dependency tables: {outside[:5]}"]}
    for f in files:
        if f.startswith(".github/workflows/"):
            if not diff:
                return {"kind": "unknown", "bumps": [], "reasons": [f"{f} changed and no diff was given to inspect"]}
            outside = workflow_changes_outside_uses(per_file.get(f, []))
            if outside:
                return {"kind": "unknown", "bumps": [], "reasons": [f"{f} changed outside `uses:` pins: {outside[:5]}"]}
    changes = bumps(lock_versions(before_lock), lock_versions(after_lock))
    if not changes and any(f == "uv.lock" for f in files):
        reasons.append("uv.lock changed with no package version movement (markers or hashes only)")
    if any(GRAMMAR.match(c["name"]) for c in changes):
        return {"kind": "grammar-or-parser", "bumps": changes,
                "reasons": [f"moves {c['name']}" for c in changes if GRAMMAR.match(c["name"])]}
    majors = [c for c in changes if c["before"] and c["after"] and _major(c["before"]) != _major(c["after"])]
    added = [c for c in changes if c["before"] is None]
    removed = [c for c in changes if c["after"] is None]
    if majors or added or removed:
        # A removed package is a shape POLICY rule 2 does not name; it is
        # treated as major so a human reads it (item-4 review, note 8).
        return {"kind": "major", "bumps": changes,
                "reasons": [f"{c['name']}: {c['before']} -> {c['after']}" for c in majors]
                + [f"new package {c['name']}" for c in added]
                + [f"removed package {c['name']}" for c in removed]}
    return {"kind": "patch-or-minor", "bumps": changes, "reasons": reasons or ["every bump stays within its major"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--files", type=Path, required=True, help="newline-separated changed paths")
    ap.add_argument("--before", type=Path, required=True, help="uv.lock at the base")
    ap.add_argument("--after", type=Path, required=True, help="uv.lock at the head")
    ap.add_argument("--diff", type=Path, default=None, help="the full unified diff")
    ap.add_argument("--before-pyproject", type=Path, default=None, help="pyproject.toml at the base")
    ap.add_argument("--after-pyproject", type=Path, default=None, help="pyproject.toml at the head")
    args = ap.parse_args(argv)
    files = [x.strip() for x in args.files.read_text(encoding="utf-8").splitlines() if x.strip()]

    def _t(p):
        return p.read_text(encoding="utf-8", errors="replace") if p and p.exists() else ""

    res = classify(files, _t(args.before), _t(args.after), _t(args.diff), _t(args.before_pyproject), _t(args.after_pyproject))
    print(json.dumps(res, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
