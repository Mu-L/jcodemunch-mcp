"""The ONE reader of `harness/thresholds.json`.

Every Floor and Target the standard states lives in that file and nowhere
else (docs/harness/DESIGN.md section 3). A test or a workflow that needs a
threshold calls `get(id)` / `floor(id)`; `tests/test_thresholds_are_the_only_copy.py`
fails if a guarded literal reappears anywhere else.

Loosening is refused unless the entry carries a `loosened` block, and a
loosened entry is printed on every load so it can never be quiet.
"""

from __future__ import annotations

import json
import operator
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
THRESHOLDS_PATH = HERE / "thresholds.json"

_COMPARATORS = {
    "<=": operator.le,
    ">=": operator.ge,
    "==": operator.eq,
    "<": operator.lt,
    ">": operator.gt,
}

_REQUIRED = (
    "id",
    "criterion",
    "metric",
    "comparator",
    "floor",
    "set_at",
    "enforced_by",
)


class ThresholdError(ValueError):
    pass


def _validate(entry: dict[str, Any]) -> None:
    missing = [k for k in _REQUIRED if k not in entry]
    if missing:
        raise ThresholdError(f"threshold {entry.get('id')!r} lacks {missing}")
    if entry["comparator"] not in _COMPARATORS:
        raise ThresholdError(
            f"threshold {entry['id']!r}: unknown comparator {entry['comparator']!r}"
        )
    for k in ("commit", "date", "reason"):
        if k not in entry["set_at"]:
            raise ThresholdError(f"threshold {entry['id']!r}: set_at lacks {k!r}")
    # A floor that moved in the LOOSER direction relative to its history must say so.
    hist = entry.get("history") or []
    if hist:
        prev = hist[-1].get("floor")
        if prev is not None and _is_looser(entry["comparator"], entry["floor"], prev):
            if not entry.get("loosened"):
                raise ThresholdError(
                    f"threshold {entry['id']!r} was loosened from {prev} to {entry['floor']} "
                    "without a `loosened` block naming who and why"
                )


def _is_looser(comparator: str, new: Any, old: Any) -> bool:
    if comparator in ("<=", "<"):
        return new > old
    if comparator in (">=", ">"):
        return new < old
    return False


def load(
    path: Path | None = None, *, announce: bool = True
) -> dict[str, dict[str, Any]]:
    """Return {id: entry}. Prints every loosened entry to stderr when `announce`."""
    p = path or THRESHOLDS_PATH
    data = json.loads(p.read_text(encoding="utf-8"))
    entries = data["thresholds"]
    out: dict[str, dict[str, Any]] = {}
    for e in entries:
        _validate(e)
        if e["id"] in out:
            raise ThresholdError(f"duplicate threshold id {e['id']!r}")
        out[e["id"]] = e
        if e.get("loosened") and announce:
            print(
                f"[harness] LOOSENED threshold {e['id']}: floor {e['floor']} "
                f"({e['loosened'].get('by')}: {e['loosened'].get('reason')})",
                file=sys.stderr,
            )
    return out


def get(id: str) -> dict[str, Any]:
    entries = load(announce=False)
    try:
        return entries[id]
    except KeyError:
        raise ThresholdError(
            f"no threshold named {id!r} in {THRESHOLDS_PATH}"
        ) from None


def floor(id: str) -> Any:
    return get(id)["floor"]


def target(id: str) -> Any:
    return get(id).get("target")


def passes(id: str, observed: Any) -> bool:
    e = get(id)
    return bool(_COMPARATORS[e["comparator"]](observed, e["floor"]))


def verdict_line(id: str, observed: Any) -> str:
    e = get(id)
    ok = passes(id, observed)
    return (
        f"{id:<40} crit {e['criterion']:<3} floor {e['comparator']} {e['floor']!s:<12} "
        f"observed {observed!s:<12} {'PASS' if ok else 'FAIL'}"
    )


def assert_passes(id: str, observed: Any, *, context: str = "") -> None:
    """Raise AssertionError naming criterion, floor and observed value."""
    e = get(id)
    if not passes(id, observed):
        raise AssertionError(
            f"STANDARD criterion {e['criterion']} ({e['metric']}): observed {observed!r} "
            f"violates floor {e['comparator']} {e['floor']!r} [{id}]"
            + (f" -- {context}" if context else "")
        )
