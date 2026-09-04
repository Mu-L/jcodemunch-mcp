"""Self-check for a PR labelled agent-authored (docs/inbound/DESIGN.md
section 5). Runs with the kill switch off, because it can only fail a PR.

purpose:  prove, from the PR's own history and files, what the fix job
          promised: nothing on the never-touch list; the failing test
          committed BEFORE any src/ change and red on main; the description
          template complete and in order; the head branch, author and
          closing issue are the fix job's
invokes:  git on a checkout of main plus the PR's commits fetched into
          refs/inbound/ (never checked out at the workspace root);
          `uv run pytest` on the test commit cherry-picked onto a worktree
          of main
produces: JSON {ok, failed: [clause...]} and exit 0/1
refuses:  nothing; every clause is checked and every failure named
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "docs" / "inbound" / "POLICY.md"
DESIGN = ROOT / "docs" / "inbound" / "DESIGN.md"


def never_touch_patterns(policy_text: str) -> list[str]:
    """The POLICY 4.4 block, one glob per whitespace-separated token; the
    `pyproject.toml [project].version` entry is checked by diff, not path."""
    i = policy_text.index("### 4.4 The never-touch list")
    m = re.search(r"```\n(.*?)\n```", policy_text[i:], re.S)
    tokens = []
    for line in m.group(1).splitlines():
        line = line.replace("pyproject.toml [project].version", "")
        tokens += [t for t in line.split() if t]
    return tokens


def touches_never_touch(files: list[str], patterns: list[str]) -> list[str]:
    hits = []
    for f in files:
        for pat in patterns:
            p = pat.rstrip("/")
            if f == p or fnmatch.fnmatch(f, p) or (p.endswith("**") and f.startswith(p[:-2])) or f.startswith(p + "/"):
                hits.append(f)
                break
    return sorted(set(hits))


def version_pin_changed(diff_text: str) -> bool:
    return bool(re.search(r"^[+-]version\s*=\s*\"", diff_text, re.M))


def template_headings(design_text: str) -> list[str]:
    i = design_text.index("## 7. The agent-authored PR description")
    m = re.search(r"```\n(.*?)\n```", design_text[i:], re.S)
    return [ln.strip() for ln in m.group(1).splitlines() if ln.startswith("## ")]


def body_follows_template(body: str, headings: list[str]) -> list[str]:
    """Every heading present, in the template's order. Each heading is
    looked up from the start of the body (a sequential search from the
    previous hit would report a swapped pair as MISSING, not out of
    order, and the reader would fix the wrong thing)."""
    problems, last = [], -1
    for h in headings:
        idx = body.find(h)
        if idx < 0:
            problems.append(h)
            continue
        if idx < last:
            problems.append(h + " (out of order)")
        last = max(last, idx)
    return problems


def commit_order(commits: list[dict]) -> tuple[str | None, list[str]]:
    """commits: oldest first, each {sha, files}. Returns (test_commit_sha,
    problems). The first commit touching tests/ must precede every commit
    touching src/, and must itself touch no src/."""
    problems = []
    first_test = next((c for c in commits if any(f.startswith("tests/") for f in c["files"])), None)
    first_src = next((c for c in commits if any(f.startswith("src/") for f in c["files"])), None)
    if first_test is None:
        problems.append("no commit touches tests/")
        return None, problems
    if any(f.startswith("src/") for f in first_test["files"]):
        problems.append(f"the first test commit {first_test['sha'][:7]} also touches src/")
    if first_src is not None and commits.index(first_src) < commits.index(first_test):
        problems.append(f"src/ changed in {first_src['sha'][:7]} before the first test commit {first_test['sha'][:7]}")
    return first_test["sha"], problems


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True, encoding="utf-8", timeout=900)


def test_commit_is_red_on_main(test_sha: str, base_ref: str, worktree: Path) -> tuple[bool, str]:
    """Cherry-pick the test commit onto a worktree of the base and run its
    test files; exit 1 there is the reproduction the fix job promised."""
    run(["git", "worktree", "add", "-q", "--detach", str(worktree), base_ref], ROOT)
    try:
        cp = run(["git", "cherry-pick", "--no-commit", test_sha], worktree)
        if cp.returncode != 0:
            return False, f"cherry-pick failed: {cp.stderr.strip()[:300]}"
        files = [f for f in run(["git", "diff", "--cached", "--name-only"], worktree).stdout.split() if f.startswith("tests/") and f.endswith(".py")]
        if not files:
            return False, "the test commit adds no tests/*.py"
        # The main checkout's environment runs the worktree's test files: the
        # package under test is `main` either way (the worktree is `main`
        # plus a commit that touches only tests/), and a fresh `uv sync` per
        # worktree would be a second environment to keep honest.
        res = run(
            ["uv", "run", "--no-sync", "pytest", "-q", "-p", "no:xdist",
             "--rootdir", str(worktree), *[str(worktree / f) for f in files]],
            ROOT,
        )
        last = (res.stdout.strip().splitlines() or [""])[-1]
        # Exit 1 is "tests failed", the reproduction. 2 (interrupted), 4
        # (usage) and 5 (nothing collected) are not a red test.
        return res.returncode == 1, f"pytest exit {res.returncode}: {last}"
    finally:
        run(["git", "worktree", "remove", "--force", str(worktree)], ROOT)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pr-json", type=Path, required=True, help="gh pr view --json number,author,headRefName,body,files,labels,commits,baseRefName")
    ap.add_argument("--diff", type=Path, required=True, help="gh pr diff output")
    ap.add_argument("--commits", type=Path, required=True, help="JSON list oldest-first of {sha, files}")
    ap.add_argument("--issue-labels", default="", help="labels on the Closes issue, comma-separated")
    ap.add_argument("--app-login", default="jcodemunch-inbound[bot]")
    ap.add_argument("--base-ref", default="origin/main")
    ap.add_argument("--worktree", type=Path, default=None)
    ap.add_argument("--skip-red-run", action="store_true")
    args = ap.parse_args(argv)

    pr = json.loads(args.pr_json.read_text(encoding="utf-8"))
    diff = args.diff.read_text(encoding="utf-8")
    commits = json.loads(args.commits.read_text(encoding="utf-8"))
    files = [f["path"] if isinstance(f, dict) else f for f in pr.get("files", [])]
    failed = []

    hits = touches_never_touch(files, never_touch_patterns(POLICY.read_text(encoding="utf-8")))
    if hits:
        failed.append(f"(a) never-touch: {hits}")
    if version_pin_changed(diff):
        failed.append("(a) never-touch: pyproject.toml [project].version")

    test_sha, problems = commit_order(commits)
    failed += [f"(b) {p}" for p in problems]
    if test_sha and not args.skip_red_run:
        red, why = test_commit_is_red_on_main(test_sha, args.base_ref, args.worktree or (ROOT.parent / "selfcheck-wt"))
        if not red:
            failed.append(f"(b) the test commit is not red on {args.base_ref}: {why}")

    missing = body_follows_template(pr.get("body") or "", template_headings(DESIGN.read_text(encoding="utf-8")))
    if missing:
        failed.append(f"(c) template headings missing or out of order: {missing}")

    m = re.search(r"Closes #(\d+)", pr.get("body") or "")
    issue_labels = [x for x in args.issue_labels.split(",") if x]
    if not m:
        failed.append("(d) body carries no `Closes #<n>`")
    elif not ({"agent-fix", "inbound:bug-candidate"} & set(issue_labels)):
        failed.append(f"(d) issue #{m.group(1)} carries neither agent-fix nor inbound:bug-candidate: {issue_labels}")

    if not re.match(r"^inbound/fix-\d+-", pr.get("headRefName") or ""):
        failed.append(f"(e) head branch {pr.get('headRefName')!r} is not inbound/fix-<n>-*")
    author = (pr.get("author") or {}).get("login", "")
    if author.replace("app/", "") not in (args.app_login, args.app_login.replace("[bot]", "")):
        failed.append(f"(f) author {author!r} is not the App {args.app_login!r}")

    print(json.dumps({"ok": not failed, "failed": failed, "test_commit": test_sha}, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
