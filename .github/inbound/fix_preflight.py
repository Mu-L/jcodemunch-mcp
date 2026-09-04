"""Pre-flight for the fix job, with no model (docs/inbound/DESIGN.md
section 3; POLICY section 2, bug row; section 9 rollback).

purpose:  decline BEFORE anything runs when: the labeler is not a human
          and INBOUND_AUTOFIX is not "true"; the issue carries
          agent:reverted, agent:in-progress or inbound:security; the author's
          account is younger than 90 days or has no prior activity here and
          the labeler is not a human; a merged revert PR names the issue and
          no human agent-fix label event is newer than that merge
invokes:  `gh api` reads (issue, timeline, user, merged PRs); nothing else
produces: JSON {ok, reasons}; exit 0 / 78; a skipped audit record on 78
refuses:  to lift any rule from the command line
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import subprocess
import sys
from pathlib import Path

EXIT_SKIP = 78
BLOCKING = ("agent:reverted", "agent:in-progress", "inbound:security")
MIN_ACCOUNT_DAYS = 90


def _gh(args: list[str]) -> str | None:
    try:
        p = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60, encoding="utf-8")
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout if p.returncode == 0 else None


def _iso(s: str) -> _dt.datetime:
    return _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def decide(
    labels: list[str],
    labeler_is_human: bool,
    autofix: str | None,
    author_age_days: int | None,
    author_prior_activity: bool | None,
    last_human_agent_fix: str | None,
    revert_merged_at: str | None,
) -> tuple[bool, list[str]]:
    """Pure. Every input None is UNKNOWN and blocks (never a False)."""
    reasons = []
    if not labeler_is_human and autofix != "true":
        reasons.append("label applied by a non-human and INBOUND_AUTOFIX is not true")
    for b in BLOCKING:
        if b in labels:
            reasons.append(f"issue carries {b}")
    if not labeler_is_human:
        if author_age_days is None or author_age_days < MIN_ACCOUNT_DAYS:
            reasons.append(f"author account age {author_age_days} days < {MIN_ACCOUNT_DAYS} (or unknown) and no human label")
        if not author_prior_activity:
            reasons.append("author has no prior comment, issue or PR here (or unknown) and no human label")
    if revert_merged_at is not None:
        if last_human_agent_fix is None or _iso(last_human_agent_fix) <= _iso(revert_merged_at):
            reasons.append(f"a merged revert names this issue ({revert_merged_at}) and no human agent-fix is newer")
    return (not reasons), reasons


def issue_labels(repo: str, issue: int) -> list[str]:
    out = _gh(["issue", "view", str(issue), "-R", repo, "--json", "labels", "--jq", "[.labels[].name]"])
    return json.loads(out) if out else []


def author_facts(repo: str, issue: int) -> tuple[str, int | None, bool | None]:
    out = _gh(["issue", "view", str(issue), "-R", repo, "--json", "author,createdAt", "--jq", "{login: .author.login, created: .createdAt}"])
    if not out:
        return "", None, None
    d = json.loads(out)
    login = d["login"]
    u = _gh(["api", f"users/{login}", "--jq", ".created_at"])
    age = (_iso(d["created"]) - _iso(u.strip())).days if u else None
    prior = _gh(["api", f"search/issues?q=repo:{repo}+author:{login}&per_page=1", "--jq", ".total_count"])
    prior_ok = (int(prior.strip()) > 1) if prior else None  # this issue counts once
    return login, age, prior_ok


def last_human_agent_fix_event(repo: str, issue: int, app_login: str) -> str | None:
    out = _gh(["api", f"repos/{repo}/issues/{issue}/timeline?per_page=100", "--paginate",
               "--jq", '.[] | select(.event == "labeled" and .label.name == "agent-fix") | "\\(.created_at)\\t\\(.actor.login)\\t\\(.actor.type)"'])
    latest = None
    for line in (out or "").splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        when, actor, typ = parts
        if typ == "User" and actor != app_login and not actor.endswith("[bot]"):
            latest = when if latest is None or when > latest else latest
    return latest


def merged_revert_naming(repo: str, issue: int) -> str | None:
    out = _gh(["pr", "list", "-R", repo, "--state", "merged", "--search", f'"Revert" #{issue} in:title,body', "--json", "title,body,mergedAt", "--limit", "20"])
    if not out:
        return None
    latest = None
    for pr in json.loads(out):
        text = (pr.get("title") or "") + "\n" + (pr.get("body") or "")
        if re.search(r"^Revert\b", pr.get("title") or "") and re.search(rf"#{issue}\b", text):
            latest = pr["mergedAt"] if latest is None or pr["mergedAt"] > latest else latest
    return latest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--issue", type=int, required=True)
    ap.add_argument("--labeler", required=True)
    ap.add_argument("--labeler-type", default="User")
    ap.add_argument("--app-login", default="jcodemunch-inbound[bot]")
    ap.add_argument("--record", type=Path, default=None)
    args = ap.parse_args(argv)

    labeler_is_human = args.labeler_type == "User" and not args.labeler.endswith("[bot]") and args.labeler != args.app_login
    autofix = (_gh(["variable", "get", "INBOUND_AUTOFIX", "-R", args.repo]) or "").rstrip("\n").rstrip("\r") or None
    labels = issue_labels(args.repo, args.issue)
    _, age, prior = author_facts(args.repo, args.issue)
    last_fix = last_human_agent_fix_event(args.repo, args.issue, args.app_login)
    revert = merged_revert_naming(args.repo, args.issue)
    ok, reasons = decide(labels, labeler_is_human, autofix, age, prior, last_fix, revert)
    print(json.dumps({"ok": ok, "reasons": reasons, "labels": labels, "author_age_days": age,
                      "author_prior_activity": prior, "last_human_agent_fix": last_fix, "revert_merged_at": revert}, sort_keys=True))
    if ok:
        return 0
    if args.record:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from ledger import make_record, write_record

        write_record(args.record, make_record(job="inbound-fix", item=str(args.issue), outcome="skipped",
                                              decision="; ".join(reasons), kill_switch_state="true"))
    return EXIT_SKIP


if __name__ == "__main__":
    sys.exit(main())
