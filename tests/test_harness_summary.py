"""`python -m harness --summary/--annotate` reproduce the verdict, they do not compute one.

The tee records every `<id> crit <c> floor <cmp> <v> observed <o> PASS|FAIL`
line; a FAIL becomes a `::error title=<id>::...` annotation and a bold row.
Both arms are exercised on synthetic lines so the test needs no Floor to fail.
"""

from __future__ import annotations

import importlib
import io
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

hm = importlib.import_module("harness.__main__")


def _tee_with(lines):
    real = io.StringIO()
    tee = hm._Tee(real)
    for ln in lines:
        tee.write(ln + "\n")
    return tee


def test_fail_line_becomes_an_annotation_and_a_bold_row():
    tee = _tee_with([
        "latency.search_symbols_warm_p95_ms       crit 5   floor <= 23           observed 54.6         FAIL",
        "claude_md.max_chars                      crit N6  floor <= 140000       observed 136359       PASS",
    ])
    ann = tee.annotations()
    assert ann == ["::error title=latency.search_symbols_warm_p95_ms::floor <= 23, observed 54.6 (criterion 5, docs/standard/STANDARD.md)"]
    md = tee.summary_markdown("harness fast", ok=False)
    assert "## harness fast: FAIL" in md
    assert "| `latency.search_symbols_warm_p95_ms` | 5 | <= 23 | 54.6 | **FAIL** |" in md
    assert "| `claude_md.max_chars` | N6 | <= 140000 | 136359 | PASS |" in md


def test_pass_only_run_has_no_annotations():
    tee = _tee_with(["route.control_at1                        crit 4   floor >= 40.0         observed 40.0         PASS"])
    assert tee.annotations() == []
    assert "PASS" in tee.summary_markdown("harness check route.control_at1", ok=True)


def test_non_verdict_lines_are_ignored():
    tee = _tee_with(["== fast tier: 85 files", "   1160 passed, 7 skipped in 45.0s", "HARNESS PASS"])
    assert tee.verdicts() == []
    assert "_no threshold verdicts in this run_" in tee.summary_markdown("x", ok=True)
