"""Does identifier-shape predict search_symbols vs search_text? Measured: no.

v1.108.253 fixed `route`'s @3 collapse on emitted task strings and named the
remaining gap without guessing at it: a rank-1 discriminator, "most likely
'does the task name an identifier-shaped token'". This script tests that
hypothesis before anyone builds a rule on it.

⚠⚠ THE PREDICATE IS DECLARED BEFORE ANY LABEL IS READ. That ordering is the
only thing separating a test from a search for a pattern that fits.

Result (2026-08-20, see shape_separation_results.json): the rule scores BELOW
a constant answer on the larger sample, and its coverage is ~15% either way,
so the residue it cannot reach IS the problem. Do not build it.

Usage:
    python measure_shape_separation.py [--corpus path/to/route_candidates_v0.1.csv]

Without --corpus the file is fetched from the published dataset and its sha256
is verified against the digest this measurement was taken over.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

CORPUS_URL = (
    "https://raw.githubusercontent.com/rknighton/jcm-route-benchmark-corpus"
    "/main/data/route_candidates_v0.1.csv"
)
# The digest emitted_task_cases.json recorded, so both measurements are over
# one corpus rather than two spellings of a moving one.
CORPUS_SHA256 = "25d09f6ae9e8e668d1a3b9a30755cf8dbd7d063ce08868529cc152fdfe84b86e"

HERE = Path(__file__).parent
SEARCH_FAMILY = {"search_text", "search_symbols"}

# ── The predicate. Declared before labels. ────────────────────────────────
PATTERNS = {
    "snake_case": re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b"),
    "camelCase": re.compile(r"\b[a-z]+[A-Z][A-Za-z0-9]*\b"),
    "PascalCase": re.compile(r"\b[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*\b"),
    "CONSTANT_CASE": re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b"),
    "call_form": re.compile(r"\b\w+\(\s*\)"),
    "dotted_path": re.compile(r"\b[A-Za-z_]\w*\.[A-Za-z_]\w*\b"),
    "backticked": re.compile(r"`[^`\n]+`"),
}


def shape_hits(text: str) -> list[str]:
    return sorted(name for name, pat in PATTERNS.items() if pat.search(text or ""))


def is_identifier_shaped(text: str) -> bool:
    return bool(shape_hits(text))


# ── Measurement ───────────────────────────────────────────────────────────

def _binom_ge(k: int, n: int, p: float) -> float:
    """P(at least k of n) under the null. Small buckets need this stated."""
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1))


def _score(pairs: list[tuple[bool, str]]) -> dict:
    """pairs of (shaped, gold). The rule under test: shaped -> symbols."""
    tab = Counter(pairs)
    n = len(pairs)
    correct = tab[(True, "search_symbols")] + tab[(False, "search_text")]
    symbols = sum(tab[(s, "search_symbols")] for s in (True, False))
    majority = max(symbols, n - symbols)
    fires = sum(tab[(True, g)] for g in SEARCH_FAMILY)
    return {
        "n": n,
        "table": {
            "shaped": {g: tab[(True, g)] for g in sorted(SEARCH_FAMILY)},
            "unshaped": {g: tab[(False, g)] for g in sorted(SEARCH_FAMILY)},
        },
        "rule_accuracy_pct": round(correct / n * 100, 1),
        "majority_floor_pct": round(majority / n * 100, 1),
        "lift_over_floor_pts": round((correct - majority) / n * 100, 1),
        "coverage_pct": round(fires / n * 100, 1),
        "residue_purity_pct": round(
            max(tab[(False, g)] for g in SEARCH_FAMILY) / max(n - fires, 1) * 100, 1
        ),
    }


def _load_corpus(path: str | None) -> list[dict]:
    if path:
        raw = Path(path).read_bytes()
    else:
        import urllib.request

        with urllib.request.urlopen(CORPUS_URL) as resp:  # noqa: S310 (pinned host)
            raw = resp.read()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != CORPUS_SHA256:
        raise SystemExit(
            f"corpus digest {digest} != {CORPUS_SHA256}. The dataset moved; this "
            "measurement's numbers are not comparable to it until re-run."
        )
    return list(csv.DictReader(raw.decode("utf-8").splitlines()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--write", action="store_true", help="update the results artifact")
    args = ap.parse_args()

    cases = json.loads(
        (HERE / "emitted_task_cases.json").read_text(encoding="utf-8")
    )["cases"]
    emitted = [c for c in cases if c["gold_primary"] in SEARCH_FAMILY]
    emitted_result = _score(
        [(is_identifier_shaped(c["emitted_task"]), c["gold_primary"]) for c in emitted]
    )
    base = sum(1 for c in emitted if c["gold_primary"] == "search_symbols") / len(emitted)
    shaped_right = emitted_result["table"]["shaped"]["search_symbols"]
    shaped_n = sum(emitted_result["table"]["shaped"].values())
    emitted_result["null_p_of_shaped_bucket"] = round(
        _binom_ge(shaped_right, shaped_n, base), 3
    )

    rows = _load_corpus(args.corpus)
    prompts = [r for r in rows if r["gold_primary_action"] in SEARCH_FAMILY]
    prompt_result = _score(
        [(is_identifier_shaped(r["prompt_text"]), r["gold_primary_action"]) for r in prompts]
    )

    per_pattern = {}
    for name in PATTERNS:
        hit = [r for r in prompts if name in shape_hits(r["prompt_text"])]
        if hit:
            sy = sum(1 for r in hit if r["gold_primary_action"] == "search_symbols")
            per_pattern[name] = {"fires": len(hit), "search_symbols": sy}
        else:
            per_pattern[name] = {"fires": 0}

    out = {
        "hypothesis": "identifier-shape predicts search_symbols over search_text",
        "verdict": "REFUTED",
        "corpus": {"source": CORPUS_URL, "sha256": CORPUS_SHA256},
        "emitted_tasks": emitted_result,
        "raw_prompts": prompt_result,
        "per_pattern_exploratory": per_pattern,
        "per_pattern_note": (
            "Seven patterns tested on one sample. Expect one to look good by chance; "
            "none is a finding on its own."
        ),
    }
    print(json.dumps(out, indent=1))
    if args.write:
        (HERE / "shape_separation_results.json").write_text(
            json.dumps(out, indent=1) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
