"""One table from two fresh runs, per row; an absent side is `n/a`, never 0
(harness F-13; workflows W-28). Red arms: a missing side rendered as 0; a
row present in only one summary dropped; a committed artifact read as a
side (there is no such input; both are files the caller made).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INBOUND = ROOT / ".github" / "inbound"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, INBOUND / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


bt = _load("bench_table")

SUMMARY_A = "| threshold | crit | floor | observed | verdict |\n|---|---|---|---|---|\n| `latency.search_symbols_p50_ms` | N4 | <= 50 | 12.5 | PASS |\n"
SUMMARY_B = "latency.search_symbols_p50_ms         crit N4  floor <= 50           observed 14.0         PASS\nlatency.only_in_head_ms crit N4 floor <= 9 observed 3 PASS\n"


def test_verdicts_reads_both_summary_shapes():
    assert bt.verdicts(SUMMARY_A)["latency.search_symbols_p50_ms"] == ("12.5", "PASS")
    v = bt.verdicts(SUMMARY_B)
    assert v["latency.search_symbols_p50_ms"] == ("14.0", "PASS") and "latency.only_in_head_ms" in v


def test_render_one_row_per_id_with_delta_and_na():
    md = bt.render({"artifacts": {}}, {"artifacts": {}}, SUMMARY_A, SUMMARY_B)
    rows = [l for l in md.splitlines() if l.startswith("| `")]
    by = {r.split("|")[1].strip().strip("`"): r for r in rows}
    assert "12.5" in by["latency.search_symbols_p50_ms"] and "+1.5" in by["latency.search_symbols_p50_ms"]
    assert "| n/a | 3 | n/a |" in by["latency.only_in_head_ms"], by["latency.only_in_head_ms"]
    assert "never a zero" in md


def test_observed_flattens_the_artifacts_block():
    obs = bt.observed({"artifacts": {"self_latency": {"search_symbols_p50_ms": 12.5, "note": "x"}}})
    assert obs == {"self_latency.search_symbols_p50_ms": 12.5}


def test_thresholds_load_from_the_real_file():
    th = bt._thresholds()
    assert th and all("floor" in v or "criterion" in v or "crit" in v for v in th.values())
