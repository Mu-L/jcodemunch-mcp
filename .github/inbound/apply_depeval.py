"""Turn a dependency evaluation into exactly the label, the one comment and
the draft POLICY section 2 permits (docs/inbound/DESIGN.md section 4).

purpose:  `agent:ready-to-merge` needs ALL of: kind patch-or-minor, gate
          success, every Floor row PASS, review verdict APPROVE; anything
          else is `agent:evaluation-failed` (gate or Floor red),
          `agent:bench-pending` (grammar) or `agent:needs-human-review`
          (major, unknown, non-APPROVE, missing result, no Floor table)
invokes:  `gh pr edit --add-label/--remove-label`, `gh pr comment` (one
          sticky comment, edited on re-run), `gh api` reads, when run
          with --apply; `apply_triage.write_draft` for the assessment
produces: a plan {label, reasons, draft}; the actions
refuses:  to merge, approve, re-run, edit the PR body or push; to label
          ready when any input is missing or UNKNOWN; to post the model's
          assessment (it is a DRAFT file for the sweep, POLICY section 2:
          the comment carries our numbers and no external text)

Floor verdicts are read from the gate's JOB LOG (`gh run view --log`),
where every tier prints one `<id> crit <c> floor <cmp v> observed <o>
PASS|FAIL` line, and from any Markdown table under the gate directory.
The PR gate writes its summaries to `$GITHUB_STEP_SUMMARY`, never to an
artifact (item-4 review, finding 1; FINDINGS IN-14), so the log is the
only place the table exists for a job that is not the gate.
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
_TABLE_ROW = re.compile(r"^\|\s*`?([\w.]+)`?\s*\|\s*\w+\s*\|[^|]*\|[^|]*\|\s*(PASS|FAIL)\s*\|")
# The harness's verdict line, anywhere in a log line (gh prefixes job, step
# and timestamp with tabs).
_VERDICT = re.compile(r"([\w.]+)\s+crit\s+\w+\s+floor\s+\S+\s+\S+\s+observed\s+\S+\s+(PASS|FAIL)\b")


def verdict_rows(text: str) -> list[tuple[str, str]]:
    rows = []
    for line in text.splitlines():
        m = _TABLE_ROW.match(line)
        if m:
            rows.append((m.group(1), m.group(2)))
            continue
        m = _VERDICT.search(line)
        if m:
            rows.append((m.group(1), m.group(2)))
    return rows


def floors_hold(gate_dir: Path | None) -> tuple[bool | None, list[str]]:
    """Every verdict row from every `*.md`, `*.log` and `*.txt` under the
    gate directory. None when no row was found (UNKNOWN, never True)."""
    if not gate_dir or not Path(gate_dir).exists():
        return None, []
    rows = []
    for p in sorted(Path(gate_dir).rglob("*")):
        if p.suffix in (".md", ".log", ".txt") and p.is_file():
            rows += verdict_rows(p.read_text(encoding="utf-8", errors="replace"))
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
        reasons.append("no Floor table found in the gate log or artifacts")
    if result is None:
        reasons.append("no evaluation result")
    if kind != "patch-or-minor":
        reasons.append(f"kind {kind}")
    if verdict != "APPROVE":
        reasons.append(f"review verdict {verdict!r}")
    if reasons:
        return {"label": "agent:bench-pending" if kind == "grammar-or-parser" else "agent:needs-human-review", "reasons": reasons}
    return {"label": "agent:ready-to-merge", "reasons": ["patch-or-minor; gate green; every Floor holds; reviewer APPROVE"]}


def render_comment(p: dict, result: dict | None, kind: str, gate_run: str, repo: str, draft_written: bool = False) -> str:
    """Our numbers and the reviewer's reasons; never the model's prose."""
    lines = [MARKER, f"**Inbound dependency evaluation**: kind `{kind}`, label `{p['label']}`", ""]
    lines += [f"- {r}" for r in p["reasons"]]
    if result:
        for r in result.get("review_reasons") or []:
            lines.append(f"- reviewer: {r}")
        if result.get("corpora_moved"):
            lines += ["", "Corpora whose symbol counts moved: " + ", ".join(str(c) for c in result["corpora_moved"])]
    if draft_written:
        lines += ["", "An assessment was drafted for the maintainer and awaits approval on the `inbound-ledger` branch; nothing from it is posted here."]
    lines += ["", f"Gate run: https://github.com/{repo}/actions/runs/{gate_run}. Nothing here merges; a human does."]
    return "\n".join(lines)


def _gh(args: list[str], repo: str, capture: bool = False) -> str:
    # `gh api` takes the repository in its path and rejects `-R` (checked
    # against gh 2.x: "unknown shorthand flag: 'R'").
    cmd = ["gh", *args] if args[0] == "api" else ["gh", *args, "-R", repo]
    proc = subprocess.run(cmd, check=True, timeout=60, capture_output=capture, text=True, encoding="utf-8")
    return proc.stdout if capture else ""


def _sticky(pr: int, repo: str) -> tuple[str | None, str]:
    """(comment id, body) of the sticky comment, or (None, ""). The id is
    found with jq; the body is fetched by a second call so newlines are
    never parsed out of a tab-joined line (item-4 review, finding 2)."""
    out = _gh(["api", f"repos/{repo}/issues/{pr}/comments", "--paginate", "--jq",
               f'.[] | select(.body | startswith("{MARKER}")) | .id'], repo, capture=True)
    ids = [x for x in out.strip().splitlines() if x.strip()]
    if not ids:
        return None, ""
    cid = ids[0].strip()
    body = _gh(["api", f"repos/{repo}/issues/comments/{cid}", "--jq", ".body"], repo, capture=True)
    return cid, body.rstrip("\n")


def apply(p: dict, body: str, pr: int, repo: str) -> None:
    remove = [x for x in OUTCOME_LABELS if x != p["label"]]
    _gh(["pr", "edit", str(pr), "--add-label", p["label"], *sum((["--remove-label", x] for x in remove), [])], repo)
    cid, _ = _sticky(pr, repo)
    if cid:
        _gh(["api", f"repos/{repo}/issues/comments/{cid}", "--method", "PATCH", "-f", f"body={body}"], repo)
    else:
        _gh(["pr", "comment", str(pr), "--body", body], repo)


def append_table(table_md: str, pr: int, repo: str) -> None:
    """The full-corpus bench appends its per-row table under the sticky
    comment, keeping everything already there; a missing comment gets one
    with the marker."""
    section = "\n\n**Full-corpus benchmark (grammar or parser bump; POLICY section 2)**\n\n" + table_md.strip() + "\n"
    cid, body = _sticky(pr, repo)
    if cid:
        _gh(["api", f"repos/{repo}/issues/comments/{cid}", "--method", "PATCH", "-f", f"body={body}{section}"], repo)
    else:
        _gh(["pr", "comment", str(pr), "--body", MARKER + section], repo)


def write_assessment_draft(result: dict | None, kind: str, pr: int, drafts_dir: Path | None, run_id: str) -> str | None:
    """A `major` or `grammar-or-parser` assessment is a draft file in the
    triage draft format, for the sweep to post once a human approves it."""
    text = (result or {}).get("assessment")
    if not text or kind not in ("major", "grammar-or-parser") or drafts_dir is None:
        return None
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from apply_triage import write_draft

    p = write_draft({"issue": pr, "category": "dependency", "body": str(text)}, drafts_dir, run_id)
    return str(p)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("result", type=Path, nargs="?")
    ap.add_argument("--append-table", type=Path, default=None, help="bench job: append this Markdown under the sticky comment and exit")
    ap.add_argument("--kind", default="unknown")
    ap.add_argument("--gate-conclusion", default="unknown")
    ap.add_argument("--gate-dir", type=Path, default=None)
    ap.add_argument("--gate-run", default="")
    ap.add_argument("--drafts-dir", type=Path, default=None)
    ap.add_argument("--run-id", default="local")
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
        if not isinstance(result, dict) or result.get("missing"):
            result = None
    except (OSError, json.JSONDecodeError):
        result = None
    floors, failing = floors_hold(args.gate_dir)
    p = plan(result, args.kind, args.gate_conclusion, floors, failing)
    draft = write_assessment_draft(result, args.kind, args.pr, args.drafts_dir, args.run_id)
    body = render_comment(p, result, args.kind, args.gate_run, args.repo, draft_written=bool(draft))
    print(json.dumps({**p, "draft": draft, "comment_chars": len(body)}, sort_keys=True))
    if args.apply:
        apply(p, body, args.pr, args.repo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
