"""One table from two fresh bench runs, per row, never per total
(docs/workflows/DESIGN.md `/benchmark-compare`; harness F-13).

purpose:  render base vs head for every threshold id that appears in
          either run's `artifacts` block or either summary's verdict rows;
          `n/a` where a side is absent, never 0 (a refusal is not a zero)
invokes:  `harness.thresholds.load()` for id, criterion, comparator, floor
produces: Markdown on stdout
refuses:  to read a committed artifact as a side (W-28): both inputs are
          files the caller produced in this run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _thresholds() -> dict[str, dict]:
    sys.path.insert(0, str(ROOT))
    try:
        from harness.thresholds import load  # type: ignore

        # `load()` returns {id: entry} and announces loosened Floors on
        # stderr, the same reader every tier uses; never a second parse.
        return dict(load(announce=False))
    except Exception:
        data = json.loads((ROOT / "harness" / "thresholds.json").read_text(encoding="utf-8"))
        return {r["id"]: r for r in data.get("thresholds", [])}


def _flatten(obj, prefix="") -> dict[str, float]:
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        out[prefix] = float(obj)
    return out


def observed(latest: dict) -> dict[str, float]:
    return _flatten(latest.get("artifacts", {}))


def verdicts(summary_text: str) -> dict[str, tuple[str, str]]:
    out = {}
    for line in summary_text.splitlines():
        m = re.match(r"^\|\s*`?([\w.]+)`?\s*\|\s*(\w+)\s*\|[^|]*\|\s*([^|]+?)\s*\|\s*(PASS|FAIL|informational)\s*\|", line)
        if m:
            out[m.group(1)] = (m.group(3), m.group(4))
        m2 = re.match(r"^([\w.]+)\s+crit\s+(\w+)\s+floor\s+(\S+\s+\S+)\s+observed\s+(\S+)\s+(PASS|FAIL)", line)
        if m2:
            out[m2.group(1)] = (m2.group(4), m2.group(5))
    return out


def _find(obs: dict[str, float], tid: str) -> float | None:
    for k, v in obs.items():
        if k == tid or k.endswith("." + tid) or k.endswith("." + tid.split(".")[-1]):
            return v
    return None


def render(base_latest: dict, head_latest: dict, base_summary: str, head_summary: str) -> str:
    th = _thresholds()
    bo, ho = observed(base_latest), observed(head_latest)
    bv, hv = verdicts(base_summary), verdicts(head_summary)
    ids = sorted(set(bv) | set(hv) | {t for t in th if _find(bo, t) is not None or _find(ho, t) is not None})
    lines = ["| threshold | crit | floor | base | head | delta | verdict (head) |", "|---|---|---|---|---|---|---|"]
    for tid in ids:
        t = th.get(tid, {})
        crit = t.get("criterion") or t.get("crit") or ""
        floor = f"{t.get('comparator', '')} {t.get('floor', '')}".strip() if t else ""
        b = _find(bo, tid)
        h = _find(ho, tid)
        if b is None and tid in bv:
            try:
                b = float(bv[tid][0])
            except ValueError:
                b = None
        if h is None and tid in hv:
            try:
                h = float(hv[tid][0])
            except ValueError:
                h = None
        bs = "n/a" if b is None else f"{b:g}"
        hs = "n/a" if h is None else f"{h:g}"
        ds = "n/a" if b is None or h is None else f"{h - b:+g}"
        verdict = hv.get(tid, ("", "n/a"))[1]
        lines.append(f"| `{tid}` | {crit} | {floor} | {bs} | {hs} | {ds} | {verdict} |")
    lines.append("")
    lines.append("Both columns are fresh runs from this job (main and the PR merge ref); no committed artifact was read. `n/a` is an absent measurement, never a zero.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--head", type=Path, required=True)
    ap.add_argument("--base-summary", type=Path, required=True)
    ap.add_argument("--head-summary", type=Path, required=True)
    args = ap.parse_args(argv)

    def _j(p: Path) -> dict:
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _t(p: Path) -> str:
        try:
            return p.read_text(encoding="utf-8")
        except OSError:
            return ""

    print(render(_j(args.base), _j(args.head), _t(args.base_summary), _t(args.head_summary)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
