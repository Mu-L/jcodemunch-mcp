"""What intake does with one issue event, decided with no model
(docs/inbound/DESIGN.md section 1).

purpose:  from the scan result, the event, and the labels already on the
          item, decide which labels to add and remove; never re-queue an
          item a human or the security rule already holds
invokes:  nothing outside the standard library
produces: JSON {add, remove, outcome, reason}
refuses:  to touch an item carrying `inbound:security` or `needs-human`;
          to re-queue on an edit or comment by anyone but the author; to
          do anything but label
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HELD = ("inbound:security", "needs-human")


def plan(
    scan: dict, event: str, action: str, actor: str, author: str, labels: list[str]
) -> dict:
    labels = list(labels or [])
    if any(h in labels for h in HELD):
        return {
            "add": [],
            "remove": [],
            "outcome": "skipped",
            "reason": "item is held (security or needs-human)",
        }
    if scan.get("security_hit"):
        return {
            "add": ["inbound:security", "needs-human"],
            "remove": ["inbound:queued"],
            "outcome": "escalated",
            "reason": "security keyword (POLICY rule 1)",
        }
    if scan.get("injection_hit"):
        return {
            "add": ["inbound:unknown", "needs-human", "inbound:injection-suspected"],
            "remove": ["inbound:queued"],
            "outcome": "escalated",
            "reason": "instruction pattern (POLICY 4.3)",
        }
    is_new = event == "issues" and action in ("opened", "reopened")
    by_author = actor.lower() == author.lower()
    if not is_new and not by_author:
        return {
            "add": [],
            "remove": [],
            "outcome": "skipped",
            "reason": "edit or comment by someone other than the author",
        }
    already = [x for x in labels if x.startswith("inbound:") and x != "inbound:queued"]
    if not is_new and already:
        return {
            "add": [],
            "remove": [],
            "outcome": "skipped",
            "reason": f"already classified {already}; an author edit does not re-queue a classified item",
        }
    return {
        "add": ["inbound:queued"],
        "remove": [],
        "outcome": "acted",
        "reason": "queued for the triage runner",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("scan", type=Path)
    ap.add_argument("--event", required=True)
    ap.add_argument("--action", required=True)
    ap.add_argument("--actor", required=True)
    ap.add_argument("--author", required=True)
    ap.add_argument(
        "--labels", default="", help="comma-separated labels already on the item"
    )
    args = ap.parse_args(argv)
    scan = json.loads(args.scan.read_text(encoding="utf-8"))
    labels = [x for x in args.labels.split(",") if x]
    print(
        json.dumps(
            plan(scan, args.event, args.action, args.actor, args.author, labels),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
