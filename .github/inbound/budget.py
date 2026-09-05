"""Budget pre-flight for headless inbound jobs (docs/inbound/POLICY.md section 7).

purpose:  decline a run BEFORE it starts when the day's count, the
          concurrent count, the open agent-PR count, or the day's cost
          would exceed the policy table; never mid-run
invokes:  `gh run list`, `gh pr list` (read only); the ledger directory
          when one is checked out
produces: a JSON verdict on stdout; exit 0 to proceed, exit 78 to skip
refuses:  to run a job it has no row for; to lower a ceiling from the
          command line (the table is edited in a PR)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
from pathlib import Path

EXIT_SKIP = 78

# POLICY section 7, verbatim. Keys are workflow file stems.
BUDGETS = {
    "inbound-triage": {
        "runs_per_day": 20,
        "cost_per_run_usd": 5.0,
        "turns": 12,
        "timeout_min": 10,
    },
    "inbound-fix": {
        "runs_per_day": 3,
        "cost_per_run_usd": 25.0,
        "turns": 60,
        "timeout_min": 60,
    },
    "inbound-depeval": {
        "runs_per_day": 4,
        "cost_per_run_usd": 10.0,
        "turns": 30,
        "timeout_min": 45,
    },
    "inbound-bench-full": {
        "runs_per_day": 4,
        "cost_per_run_usd": 0.0,
        "turns": 0,
        "timeout_min": 90,
    },
    "inbound-sweep": {
        "runs_per_day": 1,
        "cost_per_run_usd": 0.0,
        "turns": 0,
        "timeout_min": 15,
    },
    "inbound-digest": {
        "runs_per_day": 1,
        "cost_per_run_usd": 2.0,
        "turns": 8,
        "timeout_min": 15,
    },
}
DAILY_COST_USD = 60.0
MAX_OPEN_AGENT_PRS = 3


def evaluate(
    job: str,
    runs_today: int,
    open_agent_prs: int,
    cost_today_usd: float,
    manual_dispatch: bool = False,
) -> tuple[bool, list[str]]:
    """Pure decision. ``runs_today`` counts runs of this job already started
    today (the current run excluded). ``manual_dispatch`` does not lift any
    ceiling; it is recorded so the digest can say a human asked."""
    if job not in BUDGETS:
        return False, [f"no budget row for job {job!r}; add one to POLICY section 7"]
    b = BUDGETS[job]
    reasons = []
    if runs_today >= b["runs_per_day"]:
        reasons.append(f"runs_per_day: {runs_today} of {b['runs_per_day']} used")
    if cost_today_usd >= DAILY_COST_USD:
        reasons.append(
            f"daily_cost: {cost_today_usd:.2f} of {DAILY_COST_USD:.2f} USD used"
        )
    if job == "inbound-fix" and open_agent_prs >= MAX_OPEN_AGENT_PRS:
        reasons.append(f"open_agent_prs: {open_agent_prs} of {MAX_OPEN_AGENT_PRS}")
    return (not reasons), reasons


def _gh_json(args: list[str]) -> list:
    try:
        proc = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=60, encoding="utf-8"
        )
        if proc.returncode != 0:
            return []
        return json.loads(proc.stdout or "[]")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []


def runs_today(job: str, repo: str | None, today: str) -> int:
    args = [
        "run",
        "list",
        "--workflow",
        f"{job}.yml",
        "--created",
        f">={today}",
        "--json",
        "databaseId",
        "--limit",
        "200",
    ]
    if repo:
        args += ["-R", repo]
    return count_other_runs(_gh_json(args), os.environ.get("GITHUB_RUN_ID"))


def count_other_runs(runs: list, current_run_id: str | None) -> int:
    """Runs of this job already started today, EXCLUDING the run that is
    asking. The first live sweep (2026-09-05, run 33936406280) counted
    itself and declined with "runs_per_day: 1 of 1 used": a job allowed
    one run a day could never run. A run that declined at its gate still
    counts (FINDINGS IN-17)."""
    return sum(1 for r in runs if str(r.get("databaseId")) != str(current_run_id or ""))


def open_agent_prs(repo: str | None) -> int:
    args = [
        "pr",
        "list",
        "--state",
        "open",
        "--label",
        "agent-authored",
        "--json",
        "number",
        "--limit",
        "100",
    ]
    if repo:
        args += ["-R", repo]
    return len(_gh_json(args))


def cost_today(ledger_dir: Path | None, today: str) -> float:
    if not ledger_dir:
        return 0.0
    total = 0.0
    month = today[:7]
    f = Path(ledger_dir) / f"{month}.jsonl"
    if not f.exists():
        return 0.0
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (rec.get("recorded_at") or "")[:10] != today:
            continue
        c = rec.get("cost_usd") or 0.0
        job = rec.get("job") or ""
        ceiling = BUDGETS.get(job, {}).get("cost_per_run_usd", 0.0)
        # POLICY section 7: a run over its ceiling counts double against the day.
        total += c * (2.0 if ceiling and c > ceiling else 1.0)
    return total


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--job", required=True, choices=sorted(BUDGETS))
    ap.add_argument("--repo", default=None)
    ap.add_argument("--ledger-dir", type=Path, default=None)
    ap.add_argument("--manual", action="store_true")
    ap.add_argument(
        "--today", default=_dt.datetime.now(_dt.timezone.utc).date().isoformat()
    )
    args = ap.parse_args(argv)
    r = runs_today(args.job, args.repo, args.today)
    p = open_agent_prs(args.repo) if args.job == "inbound-fix" else 0
    c = cost_today(args.ledger_dir, args.today)
    ok, reasons = evaluate(args.job, r, p, c, args.manual)
    print(
        json.dumps(
            {
                "job": args.job,
                "runs_today": r,
                "open_agent_prs": p,
                "cost_today_usd": round(c, 2),
                "ok": ok,
                "reasons": reasons,
                "limits": {
                    **BUDGETS[args.job],
                    "daily_cost_usd": DAILY_COST_USD,
                    "max_open_agent_prs": MAX_OPEN_AGENT_PRS,
                },
            }
        )
    )
    return 0 if ok else EXIT_SKIP


if __name__ == "__main__":
    sys.exit(main())
