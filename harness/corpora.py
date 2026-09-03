"""Pinned corpora and their checksums (docs/harness/DESIGN.md section 5).

`harness/corpora.json` names every corpus a gated harness reads and a sha256
over its contents (files sorted by relative path, contents concatenated).
`verify()` returns the list of mismatches; the fast tier refuses to run a
benchmark over a corpus that moved. `pin()` rewrites the manifest and is only
ever run deliberately (a corpus change is a CHANGELOG event: rules R1-R6).

The three external repos in benchmarks/tasks.json are pinned by upstream
commit SHA there; this manifest records those SHAs and does not re-hash the
clones (they are not in the tree).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
MANIFEST = HERE / "corpora.json"

# name -> (relative path, glob or None for a single file)
CORPORA = {
    "rust_fixtures": ("tests/fixtures/rust", "*.rs"),
    "rust_oracle": ("tests/fixtures/rust_oracle.json", None),
    "racket_fixtures": ("tests/fixtures/racket", "**/*"),
    "racket_oracle": ("tests/fixtures/racket_oracle.json", None),
    "racket_reader_oracle": ("tests/fixtures/racket_reader_oracle.json", None),
    "replay_fixture": ("benchmarks/replay/fixtures/self_v1_75_0.json", None),
    "replay_golden": ("benchmarks/replay/results/self_v1_75_0-golden.json", None),
    "goldset_corpus": ("benchmarks/goldset/corpus", "**/*"),
    "goldset_gold": ("benchmarks/goldset/gold.json", None),
    "route_queries": ("benchmarks/route_recall/queries.json", None),
    "route_holdout": ("benchmarks/route_recall/holdout.json", None),
    "route_emitted_cases": ("benchmarks/route_recall/emitted_task_cases.json", None),
    "route_emitted_holdout": ("benchmarks/route_recall/emitted_task_holdout.json", None),
    "schema_baseline": ("benchmarks/schema_baseline.json", None),
    "token_tasks": ("benchmarks/tasks.json", None),
}


def _digest(rel: str, pattern: str | None) -> str:
    p = REPO / rel
    h = hashlib.sha256()
    if pattern is None:
        h.update(p.read_bytes())
        return h.hexdigest()
    files = sorted(f for f in p.glob(pattern) if f.is_file() and "__pycache__" not in f.parts)
    for f in files:
        h.update(str(f.relative_to(p)).replace("\\", "/").encode())
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def _external_pins() -> dict:
    tasks = json.loads((REPO / "benchmarks" / "tasks.json").read_text(encoding="utf-8"))
    out = {}
    for repo in tasks.get("repos", []):
        out[repo["id"]] = repo["sha"]
    return out


def compute() -> dict:
    return {
        "schema": "jcm-harness-corpora/v1",
        "corpora": {name: {"path": rel, "pattern": pat, "sha256": _digest(rel, pat)} for name, (rel, pat) in CORPORA.items()},
        "external_pins": _external_pins(),
    }


def pin() -> None:
    MANIFEST.write_text(json.dumps(compute(), indent=2) + "\n", encoding="utf-8")


def verify() -> list[str]:
    if not MANIFEST.exists():
        return ["harness/corpora.json missing; run `python -m harness corpora --pin`"]
    want = json.loads(MANIFEST.read_text(encoding="utf-8"))
    have = compute()
    bad = []
    for name, entry in want["corpora"].items():
        got = have["corpora"].get(name)
        if got is None:
            bad.append(f"{name}: no longer defined in harness/corpora.py")
        elif got["sha256"] != entry["sha256"]:
            bad.append(f"{name} ({entry['path']}): sha256 {got['sha256'][:12]} != pinned {entry['sha256'][:12]}")
    if have["external_pins"] != want.get("external_pins"):
        bad.append(f"external_pins moved: {want.get('external_pins')} -> {have['external_pins']}")
    return bad
