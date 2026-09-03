"""CLI entry for the smoke fixture."""

import sys

from .inventory import Inventory


def main(argv: list[str] | None = None) -> int:
    inv = Inventory()
    inv.stock["widget"] = 3
    ok = inv.reserve("widget", int((argv or sys.argv[1:] or ["1"])[0]))
    return 0 if ok else 1
