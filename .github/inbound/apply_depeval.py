"""Turn a dependency evaluation into exactly the label and comment POLICY
section 2 permits (docs/inbound/DESIGN.md section 4).

purpose:  `agent:ready-to-merge` needs ALL of: kind patch-or-minor, gate
          success, every Floor row PASS, review verdict APPROVE; anything
          else is `agent:evaluation-failed` (gate or Floor red) or
          `agent:needs-human-review` (major, grammar, unknown, non-APPROVE,
          missing result)
invokes:  `gh pr edit --add-label/--remove-label`, `gh pr comment` (one
          sticky comment, edited on re-run) when run with --apply
produces: a plan {label, comment} and the actions
refuses:  to merge, approve, re-run, edit the PR body or push; to label
          ready when any input is missing
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

OUTCOME_LABELS = ("agent:ready-to-merge", "agent:evaluation-failed", "agent:needs-human-review", "agent:bench-pending")
MARKER = "<!-- inbound-depeval -->"


def floors_hold(gate_dir: Path | None) -> tuple[bool | None, list[str]]:
    """Read every `| <id> | crit | floor | observed | verdict |` row from the
    gate's summaries. None when no summary was found (UNKNOWN, never True)."""
    if not gate_dir or not Path(gate_dir).exists():
        return None, []
    rows = []
    for md in Path(gate_dir).rglob("*.md"):
        for line in md.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^\|\s*`?([\w.]+)`?\s*\|\s*\w+\s*\|[^|]*\|[^|]*\|\s*(PASS|FAIL)\s*\|", line)
            if m:
                rows.append((m.group(1), m.group(2)))
    if not rows:
        return None, []
    failing = sorted({i for i, v in rows if v == "FAIL"})
    return (not failing), failing


def plan(result: dict | None, kind: str, gate_conclusion: str, floors: bool | None, failing: list[str]) -> dict:
    verdict = (result or {}).get("review_verdict")
    reasons = []
    if gate_conclusion != "success":
        reasons.append(f"gate {gate_conclusion}")
    if floors is False:
        reasons.append("Floor FAIL: " + ", ".join(failing))
    if reasons:
        return {"label": "agent:evaluation-failed", "reasons": reasons}
    if floors is None:
        reasons.append("no Floor table found in the gate artifacts")
    if result is None:
        reasons.append("no evaluation result")
    if kind != "patch-or-minor":
        reasons.append(f"kind {kind}")
    if verdict != "APPROVE":
        reasons.append(f"review verdict {verdict!r}")
    if reasons:
        return {"label": "agent:bench-pending" if kind == "grammar-or-parser" else "agent:needs-human-review", "reasons": reasons}
    return {"label": "agent:ready-to-merge", "reasons": ["patch-or-minor; gate green; every Floor holds; reviewer APPROVE"]}


def render_comment(p: dict, result: dict | None, kind: str, gate_run: str, repo: str) -> str:
    lines = [MARKER, f"**Inbound dependency evaluation** — kind `{kind}` — label `{p['label']}`", ""]
    lines += [f"- {r}" for r in p["reasons"]]
    if result:
        for r in result.get("review_reasons") or []:
            lines.append(f"- reviewer: {r}")
        if result.get("assessment"):
            lines += ["", "Assessment (drafted; a human decides):", "", result["assessment"]]
        if result.get("corpora_moved"):
            lines += ["", "Corpora whose symbol counts moved: " + ", ".join(result["corpora_moved"])]
    lines += ["", f"Gate run: https://github.com/{repo}/actions/runs/{gate_run}. Nothing here merges; a human does."]
    return "\n".join(lines)


def _gh(args: list[str], repo: str, capture: bool = False) -> str:
    # `gh api` takes the repository in its path and rejects `-R` (checked
    # against gh 2.x: "unknown shorthand flag: 'R'").
    cmd = ["gh", *args] if args[0] == "api" else ["gh", *args, "-R", repo]
    proc = subprocess.run(cmd, check=True, timeout=60, capture_output=capture, text=True, encoding="utf-8")
    return proc.stdout if capture else ""


def apply(p: dict, body: str, pr: int, repo: str) -> None:
    remove = [x for x in OUTCOME_LABELS if x != p["label"]]
    _gh(["pr", "edit", str(pr), "--add-label", p["label"], *sum((["--remove-label", x] for x in remove), [])], repo)
    out = _gh(["api", f"repos/{repo}/issues/{pr}/comments", "--paginate", "--jq", f'.[] | select(.body | startswith("{MARKER}")) | .id'], repo, capture=True)
    existing = out.strip().splitlines()
    if existing:
        _gh(["api", f"repos/{repo}/issues/comments/{existing[0]}", "--method", "PATCH", "-f", f"body={body}"], repo)
    else:
        _gh(["pr", "comment", str(pr), "--body", body], repo)


def append_table(table_md: str, pr: int, repo: str) -> None:
    """The full-corpus bench appends its per-row table under the sticky
    comment; a missing comment gets one with the marker."""
    out = _gh(["api", f"repos/{repo}/issues/{pr}/comments", "--paginate", "--jq", f'.[] | select(.body | startswith("{MARKER}")) | "\\(.id)\\t\\(.body)"'], repo, capture=True)
    first = out.strip().split("\n", 1)[0] if out.strip() else ""
    section = "\n\n**Full-corpus benchmark (grammar or parser bump; POLICY section 2)**\n\n" + table_md.strip() + "\n"
    if first:
        cid, _, body = first.partition("\t")
        body = body.replace("\\n", "\n")
        _gh(["api", f"repos/{repo}/issues/comments/{cid}", "--method", "PATCH", "-f", f"body={body}{section}"], repo)
    else:
        _gh(["pr", "comment", str(pr), "--body", MARKER + section], repo)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("result", type=Path, nargs="?")
    ap.add_argument("--append-table", type=Path, default=None, help="bench job: append this Markdown under the sticky comment and exit")
    ap.add_argument("--kind", default="unknown")
    ap.add_argument("--gate-conclusion", default="unknown")
    ap.add_argument("--gate-dir", type=Path, default=None)
    ap.add_argument("--gate-run", default="")
    ap.add_argument("--pr", type=int, required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    if args.append_table is not None:
        table = args.append_table.read_text(encoding="utf-8")
        print(json.dumps({"append_table_chars": len(table), "pr": args.pr}))
        if args.apply:
            append_table(table, args.pr, args.repo)
        return 0
    result = None
    try:
        result = json.loads(args.result.read_text(encoding="utf-8")) if args.result else None
    except (OSError, json.JSONDecodeError):
        result = None
    floors, failing = floors_hold(args.gate_dir)
    p = plan(result, args.kind, args.gate_conclusion, floors, failing)
    body = render_comment(p, result, args.kind, args.gate_run, args.repo)
    print(json.dumps({**p, "comment_chars": len(body)}, sort_keys=True))
    if args.apply:
        apply(p, body, args.pr, args.repo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
