"""Kill switch for every headless inbound job (docs/inbound/POLICY.md section 8).

purpose:  answer "may a headless job act right now?" from ONE repository
          variable, read through the API at run time, failing closed
invokes:  `gh variable get INBOUND_ENABLED` (read only)
produces: a JSON line on stdout; exit 0 when enabled, exit 78 (skip) when
          not; optionally an audit record with outcome "skipped"
refuses:  to treat anything but the exact string "true" as on; to read the
          `vars` context (captured at queue time, not run time)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

VARIABLE = "INBOUND_ENABLED"
EXIT_SKIP = 78  # BSD EX_CONFIG-adjacent; distinct from failure so a caller can tell "off" from "broken"


def enabled(value: str | None) -> bool:
    """Only the exact string ``true`` turns the layer on. ``None``, ``""``,
    ``"True"``, ``"1"``, ``"yes"`` are all OFF (POLICY section 8: a mis-set
    switch fails closed)."""
    return value == "true"


def read_variable(name: str = VARIABLE, repo: str | None = None) -> str | None:
    """Read a repository variable through the API. ``None`` when it does not
    exist or the call fails, which the caller must treat as OFF."""
    cmd = ["gh", "variable", "get", name]
    if repo:
        cmd += ["-R", repo]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, encoding="utf-8"
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    # Only the one newline `gh` appends; a padded value stays padded and reads OFF.
    return proc.stdout.rstrip("\n").rstrip("\r")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--variable", default=VARIABLE)
    ap.add_argument("--repo", default=None)
    ap.add_argument(
        "--record",
        type=Path,
        default=None,
        help="write a skipped audit record here when the switch is off",
    )
    ap.add_argument("--job", default="unknown")
    ap.add_argument("--item", default="")
    args = ap.parse_args(argv)

    value = read_variable(args.variable, args.repo)
    on = enabled(value)
    print(json.dumps({"variable": args.variable, "value": value, "enabled": on}))
    if on:
        return 0
    if args.record:
        from ledger import make_record, write_record  # sibling module

        write_record(
            args.record,
            make_record(
                job=args.job,
                item=args.item,
                outcome="skipped",
                decision=f"kill switch {args.variable}={value!r}",
                kill_switch_state=value,
            ),
        )
    return EXIT_SKIP


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.exit(main())
