"""Publish gate for the fix job, with no model (docs/inbound/DESIGN.md
section 3, as built): the model job commits locally and hands over a git
bundle, a PR body and its evidence; this decides, from those files alone,
whether the App may push the branch and open the DRAFT.

purpose:  refuse the push when the branch is not `inbound/fix-<n>-*`; when
          any commit touches a never-touch path or the version pin; when
          the first test commit does not precede every src/ change; when
          the body lacks a template heading or `Closes #<n>` for the issue;
          when the bundle carries anything but commits on top of main
invokes:  git (bundle verify, rev-list, diff-tree) on the main checkout;
          selfcheck.py's pure checks; nothing that writes
produces: JSON {ok, reasons, branch, head}; exit 0 / 1
refuses:  to lift a rule from the command line; to push or open anything
          itself (the workflow does that, on exit 0 only)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from selfcheck import (  # noqa: E402
    DESIGN,
    POLICY,
    body_follows_template,
    commit_order,
    never_touch_patterns,
    template_headings,
    touches_never_touch,
    version_pin_changed,
)


def _git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    # `cwd` resolves at CALL time; a default bound at import pins the
    # repository this module was loaded from (the item-5 lesson).
    return subprocess.run(["git", *args], cwd=str(cwd or ROOT), capture_output=True, text=True, encoding="utf-8", timeout=300)


def bundle_commits(bundle: Path, base_ref: str) -> tuple[str | None, list[dict], str | None]:
    """Fetch the bundle into refs/inbound/fix-head and list its commits
    oldest first as {sha, files}. Returns (head_sha, commits, error)."""
    v = _git(["bundle", "verify", str(bundle)])
    if v.returncode != 0:
        return None, [], f"bundle verify failed: {v.stderr.strip()[:300]}"
    heads = _git(["bundle", "list-heads", str(bundle)]).stdout.split()
    if len(heads) < 2:
        return None, [], "bundle lists no head"
    f = _git(["fetch", "-q", str(bundle), f"{heads[1]}:refs/inbound/fix-head"])
    if f.returncode != 0:
        return None, [], f"fetch from bundle failed: {f.stderr.strip()[:300]}"
    head = _git(["rev-parse", "refs/inbound/fix-head"]).stdout.strip()
    mb = _git(["merge-base", base_ref, head]).stdout.strip()
    base = _git(["rev-parse", base_ref]).stdout.strip()
    if mb != base:
        return head, [], f"the branch is not on top of {base_ref} (merge-base {mb[:7]}, base {base[:7]})"
    # `--parents`: a merge commit (two parents) or a root commit (none)
    # lists NO files under `diff-tree` without `-m`/`--root`, so a
    # never-touch path could ride in on one (review round 1, finding 2;
    # reproduced with an orphan commit merged onto the branch). Refused by
    # shape; `range_files` below is the second guard.
    lines = _git(["rev-list", "--reverse", "--parents", f"{base_ref}..{head}"]).stdout.splitlines()
    commits = []
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        s, parents = parts[0], parts[1:]
        if len(parents) != 1:
            return head, [], f"commit {s[:7]} has {len(parents)} parents; every commit must have exactly one"
        files = _git(["diff-tree", "--no-commit-id", "--name-only", "-r", s]).stdout.split()
        commits.append({"sha": s, "files": files})
    return head, commits, None


def range_files(base_ref: str, head: str) -> list[str]:
    """Every path that differs between the base and the head, whatever the
    commits say: the per-commit list can be fooled by commit shape, the
    range cannot."""
    return _git(["diff", "--name-only", f"{base_ref}..{head}"]).stdout.split()


def decide(branch: str, issue: int, commits: list[dict], diff: str, body: str, patterns: list[str], headings: list[str],
           range_files: list[str] | None = None) -> list[str]:
    """Pure. Every reason is a refusal; an empty list publishes.
    `range_files` is `git diff --name-only base..head`; it is unioned with
    the per-commit lists for the never-touch check (finding 2)."""
    reasons = []
    if not re.match(rf"^inbound/fix-{issue}-[a-z0-9][a-z0-9-]*$", branch or ""):
        reasons.append(f"branch {branch!r} is not inbound/fix-{issue}-<slug>")
    if not commits:
        reasons.append("no commits on top of main")
    files = sorted({f for c in commits for f in c["files"]} | set(range_files or []))
    hits = touches_never_touch(files, patterns)
    if hits:
        reasons.append(f"never-touch: {hits}")
    if version_pin_changed(diff):
        reasons.append("never-touch: pyproject.toml [project].version")
    _, problems = commit_order(commits)
    reasons += problems
    missing = body_follows_template(body, headings)
    if missing:
        reasons.append(f"template headings missing or out of order: {missing}")
    if not re.search(rf"Closes #{issue}\b", body):
        reasons.append(f"body does not carry `Closes #{issue}`")
    return reasons


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bundle", type=Path, required=True)
    ap.add_argument("--branch-file", type=Path, required=True)
    ap.add_argument("--body", type=Path, required=True)
    ap.add_argument("--issue", type=int, required=True)
    ap.add_argument("--base-ref", default="origin/main")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    branch = args.branch_file.read_text(encoding="utf-8").strip() if args.branch_file.exists() else ""
    body = args.body.read_text(encoding="utf-8") if args.body.exists() else ""
    head, commits, err = (None, [], "no bundle file") if not args.bundle.exists() else bundle_commits(args.bundle, args.base_ref)
    reasons = [err] if err else []
    diff = _git(["diff", f"{args.base_ref}..{head}", "--", "pyproject.toml"]).stdout if head and not err else ""
    rng = range_files(args.base_ref, head) if head and not err else []
    reasons += decide(branch, args.issue, commits, diff,  body,
                      never_touch_patterns(POLICY.read_text(encoding="utf-8")),
                      template_headings(DESIGN.read_text(encoding="utf-8")), range_files=rng)
    res = {"ok": not reasons, "reasons": reasons, "branch": branch, "head": head, "commits": [c["sha"] for c in commits]}
    text = json.dumps(res, sort_keys=True)
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8", newline="\n")
    return 0 if not reasons else 1


if __name__ == "__main__":
    sys.exit(main())
