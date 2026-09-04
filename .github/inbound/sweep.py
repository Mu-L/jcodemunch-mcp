"""Daily sweep over the ledger branch (docs/inbound/DESIGN.md section 6).

purpose:  roll the day's audit and draft artifacts into `inbound-ledger`;
          post the drafts a HUMAN approved, verbatim; count the
          graduation streaks; list what needs re-notification
invokes:  ledger.roll; `gh issue comment` for an approved draft (the one
          write); git on the ledger checkout
produces: ledger/<YYYY-MM>.jsonl appended; drafts/posted/*; a JSON
          summary for the digest; `streaks.json`
refuses:  to post a draft whose `approved:` is not literally `true` or whose
          approving commit was authored by the App; to count a post toward
          graduation when the body no longer matches its `original` block
          (it posts the edited text and resets the streak); to post twice;
          to overwrite a draft already in `drafts/` or `drafts/posted/`
          when re-ingesting artifacts (a human's approval survives the
          next sweep); to let one malformed draft abort the others
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import subprocess
import sys
from pathlib import Path

GRADUATING = ("bug-unreproducible", "question", "feature")


def parse_draft(text: str) -> dict:
    m = re.match(r"---\n(.*?)\n---\n(.*)\Z", text.replace("\r\n", "\n"), re.S)
    if not m:
        raise ValueError("draft has no front matter")
    fm = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    body = m.group(2)
    om = re.search(r"<!-- original -->\n(.*?)\n<!-- /original -->", body, re.S)
    original = om.group(1) if om else None
    shown = body.split("<!-- original -->", 1)[0].rstrip("\n")
    return {"front": fm, "body": shown, "original": original}


def approver_is_human(path: Path, ledger_dir: Path, app_login: str) -> tuple[bool, str]:
    """The author of the last commit touching the draft. The App never
    approves; a human commit is the approval (POLICY section 9)."""
    try:
        out = subprocess.run(
            [
                "git",
                "log",
                "-1",
                "--format=%an <%ae>",
                "--",
                str(path.relative_to(ledger_dir)),
            ],
            cwd=str(ledger_dir),
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return False, "git log failed"
    if not out:
        return False, "no commit"
    if app_login.lower() in out.lower() or "[bot]" in out:
        return False, out
    return True, out


def decide(draft: dict, human: bool) -> dict:
    """Pure. What the sweep does with one draft file."""
    fm = draft["front"]
    if fm.get("approved") != "true":
        return {"action": "hold", "reason": "not approved"}
    if not human:
        return {"action": "hold", "reason": "approver is not a human commit"}
    edited = (
        draft["original"] is not None
        and draft["body"].strip() != draft["original"].strip()
    )
    return {
        "action": "post",
        "edited": edited,
        "category": fm.get("category"),
        "issue": int(fm["issue"]),
    }


def update_streaks(streaks: dict, category: str, edited: bool) -> dict:
    s = dict(streaks)
    if category not in GRADUATING:
        return s
    row = dict(s.get(category, {"count": 0, "first": None, "last": None}))
    today = _dt.date.today().isoformat()
    if edited:
        row = {
            "count": 0,
            "first": None,
            "last": today,
            "reset_reason": "edited before post",
        }
    else:
        row["count"] = row.get("count", 0) + 1
        row["first"] = row.get("first") or today
        row["last"] = today
        row.pop("reset_reason", None)
    s[category] = row
    return s


def _gh(args: list[str], repo: str) -> None:
    subprocess.run(["gh", *args, "-R", repo], check=True, timeout=60)


def post_approved(
    ledger_dir: Path, repo: str, app_login: str, apply: bool
) -> list[dict]:
    drafts = ledger_dir / "drafts"
    posted_dir = drafts / "posted"
    posted_dir.mkdir(parents=True, exist_ok=True)
    streaks_path = ledger_dir / "streaks.json"
    streaks = (
        json.loads(streaks_path.read_text(encoding="utf-8"))
        if streaks_path.exists()
        else {}
    )
    results = []
    for p in sorted(drafts.glob("*.md")):
        try:
            d = parse_draft(p.read_text(encoding="utf-8"))
            human, who = approver_is_human(p, ledger_dir, app_login)
            verdict = decide(d, human)
        except (ValueError, KeyError, OSError) as e:
            # One malformed draft holds itself, never the others (item-3
            # review, finding 4).
            results.append(
                {"file": p.name, "action": "hold", "reason": f"{type(e).__name__}: {e}"}
            )
            continue
        verdict["file"] = p.name
        verdict["approver"] = who
        if verdict["action"] == "post":
            if apply:
                _gh(
                    ["issue", "comment", str(verdict["issue"]), "--body", d["body"]],
                    repo,
                )
                p.rename(posted_dir / p.name)
            streaks = update_streaks(streaks, verdict["category"], verdict["edited"])
        results.append(verdict)
    if apply:
        streaks_path.write_text(
            json.dumps(streaks, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return results


def ingest_drafts(artifacts_dir: Path, ledger_dir: Path) -> dict:
    """Copy `draft-*` artifact files into `drafts/` ONLY when no file of that
    name exists in `drafts/` or `drafts/posted/`. The artifact window is two
    days, so the same artifact is seen by two sweeps; re-copying it would
    revert a human's `approved: true` or re-create a posted draft (item-3
    review, finding 1)."""
    drafts = Path(ledger_dir) / "drafts"
    posted = drafts / "posted"
    drafts.mkdir(parents=True, exist_ok=True)
    posted.mkdir(parents=True, exist_ok=True)
    added, skipped = [], []
    for src in sorted(Path(artifacts_dir).rglob("*.md")):
        if "draft-" not in "/".join(src.relative_to(artifacts_dir).parts[:1]):
            continue
        if (drafts / src.name).exists() or (posted / src.name).exists():
            skipped.append(src.name)
            continue
        (drafts / src.name).write_bytes(src.read_bytes())
        added.append(src.name)
    return {"added": added, "skipped_existing": skipped}


def stale_needs_human(repo: str, days: int = 7) -> list[int]:
    cutoff = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)).isoformat()
    try:
        out = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "-R",
                repo,
                "--label",
                "needs-human",
                "--state",
                "open",
                "--json",
                "number,updatedAt",
                "--limit",
                "200",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
        ).stdout
        rows = json.loads(out or "[]")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []
    return sorted(r["number"] for r in rows if r.get("updatedAt", "") < cutoff)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledger-dir", type=Path, required=True)
    ap.add_argument("--artifacts-dir", type=Path, required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--app-login", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--summary", type=Path, default=None)
    args = ap.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ledger import roll

    ingested = ingest_drafts(args.artifacts_dir, args.ledger_dir)
    added = roll(args.artifacts_dir, args.ledger_dir / "ledger")
    posted = post_approved(args.ledger_dir, args.repo, args.app_login, args.apply)
    stale = stale_needs_human(args.repo)
    summary = {
        "ledger_rows_added": added,
        "drafts_ingested": ingested,
        "drafts": posted,
        "stale_needs_human": stale,
        "ran_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    }
    if args.summary:
        args.summary.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
