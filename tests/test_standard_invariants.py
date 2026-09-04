"""The standard's own citations cannot rot.

`docs/standard/STANDARD.md` names the tests that enforce each criterion,
`harness/thresholds.json` names the files in `enforced_by`, and
`harness/tiers.json` names the fast-tier files and the UNCLEAR items. Nothing
failed when one of those files was deleted or renamed. This file does.

It also carries the three offline Floors that had no assertion before
(COVERAGE-MAP s1): counter.saving_min, the two language counts, and the CI
job timeout, each read through `harness.thresholds` (the only copy).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from harness import thresholds as T

REPO = T.REPO_ROOT
TIERS = json.loads((REPO / "harness" / "tiers.json").read_text(encoding="utf-8"))
STANDARD = (REPO / "docs" / "standard" / "STANDARD.md").read_text(encoding="utf-8")

# Honesty invariants (criterion 9) and the four PROPOSED sub-criteria
# (COVERAGE-MAP s3): enumerated so a deletion is noticed. Names, not
# behaviour; the behaviour lives in the files.
HONESTY_PINS = [
    "tests/test_v1_108_186.py",  # ledger_trust: UNKNOWN is a third bucket, never False
    "tests/test_result_cache_isolation.py",  # a cache returns a copy, not its stored object (#572)
    "tests/test_stop_rule.py",  # terminal means final, not safe
    "tests/test_analyze_perf_totals.py",  # hit_rate_basis; a tokens-only baseline refuses a latency delta
    "tests/test_security_disclosure.py",  # every remote-write route is disclosed
    "tests/test_optional_dep_skips_are_visible.py",  # a skip must collect and show
]
PROPOSED = {
    "6a client-specific surface selection": [
        "tests/test_agent_selector.py",
        "tests/test_tier_switch_cost.py",
    ],
    "3a multi-process coordination": [
        "tests/test_v1_108_105.py",
        "tests/test_v1_108_108.py",
    ],
    "9a evidence receipts": [
        "tests/test_receipt.py",
        "tests/test_negative_evidence.py",
    ],
    "8a runtime-trace ingestion safety": [
        "tests/test_runtime_phase0.py",
        "tests/test_runtime_phase5.py",
    ],
}


def _collects(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    return bool(re.search(r"^\s*(async\s+)?def test_", text, re.M))


@pytest.mark.parametrize("path", HONESTY_PINS)
def test_honesty_pin_exists_and_collects(path):
    p = REPO / path
    assert p.exists(), (
        f"{path} named in the honesty enumeration is gone; retire it through harness/retired.json or restore it"
    )
    assert _collects(p), f"{path} defines no test functions"


@pytest.mark.parametrize("name,paths", sorted(PROPOSED.items()))
def test_proposed_subcriterion_pins_exist(name, paths):
    for path in paths:
        p = REPO / path
        if not p.exists():
            # A proposed sub-criterion may name a representative file that has
            # a different spelling; find the family by prefix before failing.
            stem = Path(path).stem.split("_")[1:3]
            family = list((REPO / "tests").glob(f"test_{'_'.join(stem)}*.py"))
            assert family, f"{name}: {path} and its family are gone"


def test_every_enforced_by_file_exists_and_collects():
    missing = []
    for e in T.load(announce=False).values():
        for ref in e["enforced_by"]:
            f = REPO / ref.split("::")[0].split(" ")[0]
            if not f.exists():
                missing.append(f"{e['id']}: {ref}")
            elif f.suffix == ".py" and f.parts[-2] == "tests" and not _collects(f):
                missing.append(f"{e['id']}: {ref} collects nothing")
    assert not missing, "\n".join(missing)


def test_every_test_named_in_the_standard_exists():
    named = set(re.findall(r"tests/test_[A-Za-z0-9_]+\.py", STANDARD))
    globbed = set(re.findall(r"tests/test_[A-Za-z0-9_]+\*\.py", STANDARD))
    missing = [n for n in sorted(named) if not (REPO / n).exists()]
    for g in globbed:
        if not list(REPO.glob(g)):
            missing.append(g)
    assert not missing, f"STANDARD.md names tests that do not exist: {missing}"


def test_fast_tier_files_exist():
    missing = [f for f in TIERS["fast"] if not (REPO / f).exists()]
    assert not missing, missing


def test_unclear_items_are_still_present_and_untouched_by_the_harness():
    """UNCLEAR entries may not be modified, moved or retired by an agent
    (docs/harness/DESIGN.md s6). Existence is what this can check; the
    review question travels with the entry."""
    for u in TIERS["unclear"]:
        p = REPO / u["path"]
        assert p.exists(), (
            f"UNCLEAR item {u['path']} is gone; it was to stay byte-identical until reviewed"
        )
        assert u["question"], f"UNCLEAR item {u['path']} carries no review question"


def test_counter_saving_floor():
    b = json.loads(
        (REPO / "benchmarks" / "schema_baseline.json").read_text(encoding="utf-8")
    )
    saving = 1 - b["counter_full"] / b["full_full"]
    T.assert_passes(
        "counter.saving_min",
        round(saving, 4),
        context="benchmarks/schema_baseline.json",
    )


def test_language_counts_do_not_shrink():
    from jcodemunch_mcp.parser.languages import LANGUAGE_EXTENSIONS, LANGUAGE_REGISTRY

    T.assert_passes(
        "languages.registry_min",
        len(LANGUAGE_REGISTRY),
        context="a removed language needs a CHANGELOG entry AND a tightened-history threshold entry",
    )
    T.assert_passes("languages.extensions_min", len(LANGUAGE_EXTENSIONS))


def test_ci_timeout_matches_threshold():
    text = (REPO / ".github" / "workflows" / "pr-gate.yml").read_text(encoding="utf-8")
    # The FULL job's ceiling, not the first job's: the block after `  full:`.
    m = re.search(r"^  full:\n(?:.*\n)*?\s+timeout-minutes:\s*(\d+)", text, re.M)
    assert m, "pr-gate.yml has no timeout-minutes on the full job (STANDARD N1)"
    T.assert_passes(
        "ci.test_job_timeout_minutes",
        int(m.group(1)),
        context=".github/workflows/pr-gate.yml",
    )
