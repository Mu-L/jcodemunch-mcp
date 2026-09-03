"""`python -m harness [fast|full|bench|all|check ID [--stamp]|threshold ID|thresholds|corpora]`

The single entry point that decides whether a change is acceptable
(docs/harness/DESIGN.md). Exit code is non-zero on any test failure, any Floor
violation, or any tier over its runtime ceiling. Every threshold verdict is
printed as one line: id, criterion, floor, observed, PASS|FAIL.

Tier membership: harness/tiers.json. Floors: harness/thresholds.json (only).
Corpus checksums: harness/corpora.json. Results: harness/results/latest.json
when --write-results is given.

Methodology rules R1-R62 (docs/harness/ARCHAEOLOGY.md section A) bind the bench
tier; the assertions that enforce them cite the rule number.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from harness import thresholds as T  # noqa: E402
from harness import corpora as C  # noqa: E402

TIERS = json.loads((HERE / "tiers.json").read_text(encoding="utf-8"))
RESULTS_DIR = HERE / "results"
PY = sys.executable


def _env() -> dict:
    return {
        "os": platform.platform(),
        "python": platform.python_version(),
        "cpus": os.cpu_count(),
        "runner": "github" if os.environ.get("GITHUB_ACTIONS") else "local",
        "commit": _git("rev-parse", "--short", "HEAD"),
    }


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=REPO, text=True, encoding="utf-8", errors="replace").strip()
    except Exception:
        return "unknown"


def _run(cmd: list[str], *, env: dict | None = None) -> tuple[int, str, float]:
    t0 = time.perf_counter()
    e = dict(os.environ)
    e.setdefault("PYTHONPATH", str(REPO / "src"))
    e.setdefault("PYTHONIOENCODING", "utf-8")
    if env:
        e.update(env)
    proc = subprocess.run(cmd, cwd=REPO, env=e, text=True, capture_output=True, encoding="utf-8", errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out, time.perf_counter() - t0


_SUMMARY = re.compile(r"(?:(\d+) passed)?(?:, )?(?:(\d+) skipped)?(?:, )?(?:(\d+) failed)?")


def _pytest_summary(out: str) -> dict:
    line = ""
    for ln in out.splitlines()[::-1]:
        if re.search(r"\b(passed|failed|error)\b", ln) and (" in " in ln):
            line = ln
            break
    def grab(word: str) -> int:
        m = re.search(rf"(\d+) {word}", line)
        return int(m.group(1)) if m else 0
    return {"passed": grab("passed"), "skipped": grab("skipped"), "failed": grab("failed") + grab("error"), "line": line.strip()}


def _xdist_args() -> list[str]:
    """Probe the interpreter that will RUN pytest, not this one.

    First run of the fast tier under a bare `python -m harness` took 110 s
    serial and failed its own 90 s ceiling: the conda interpreter had no
    xdist while `.venv` did. `uv run python -m harness` is the documented
    spelling; a serial fallback is announced so a ceiling failure reads as
    "wrong interpreter", not "slow tests" (FINDINGS F-12).
    """
    probe = subprocess.run([PY, "-c", "import xdist"], capture_output=True)
    if probe.returncode == 0:
        return ["-n", "auto", "--dist", "loadfile"]
    print(f"[harness] WARNING: pytest-xdist not importable by {PY}; running SERIAL. "
          "Use `uv run python -m harness` (the .venv has xdist).", file=sys.stderr)
    return []


# --------------------------------------------------------------------------- measurers
# Each returns the OBSERVED value for a threshold id, or None when it can only be
# established by a test/harness the tier runs (the verdict then comes from that
# run's exit code, and `check` says so).

def _m_languages_registry() -> int:
    from jcodemunch_mcp.parser.languages import LANGUAGE_REGISTRY
    return len(LANGUAGE_REGISTRY)


def _m_languages_extensions() -> int:
    from jcodemunch_mcp.parser.languages import LANGUAGE_EXTENSIONS
    return len(LANGUAGE_EXTENSIONS)


def _m_counter_saving() -> float:
    b = json.loads((REPO / "benchmarks" / "schema_baseline.json").read_text(encoding="utf-8"))
    return round(1 - b["counter_full"] / b["full_full"], 4)


def _m_claude_md() -> int:
    return len((REPO / "CLAUDE.md").read_text(encoding="utf-8"))


def _m_core_compact() -> int:
    """Identical method to tests/test_schema_budget.py::test_live_core_compact (cl100k, live build)."""
    import tiktoken
    from jcodemunch_mcp import config as config_module
    from jcodemunch_mcp.server import _build_tools_list
    enc = tiktoken.get_encoding("cl100k_base")
    cfg = config_module._GLOBAL_CONFIG  # type: ignore[attr-defined]
    original = {k: cfg.get(k) for k in ("tool_profile", "compact_schemas")}
    try:
        cfg["tool_profile"] = "core"
        cfg["compact_schemas"] = True
        tools = _build_tools_list()
        payload = [{"name": t.name, "description": t.description, "inputSchema": t.inputSchema} for t in tools]
        return len(enc.encode(json.dumps(payload, separators=(",", ":"))))
    finally:
        for k, v in original.items():
            if v is None:
                cfg.pop(k, None)
            else:
                cfg[k] = v


def _m_route_control() -> float:
    """Same computation as tests/test_catalog_moratorium.py::_control_at_1 over the committed artifact."""
    bench = REPO / "benchmarks" / "route_recall"
    holdout = json.loads((bench / "holdout_results.json").read_text(encoding="utf-8"))
    corpus = json.loads((bench / "holdout.json").read_text(encoding="utf-8"))
    mirrors = {q["q"]: q.get("mirrors", "control") for q in corpus["queries"]}
    rows = [r for r in holdout["per_query"] if mirrors.get(r["query"]) == "control"]
    hits = sum(1 for r in rows if r["route_rank"] == 1)
    return round(100.0 * hits / len(rows), 1)


def _m_rust(bucket: str):
    def f() -> int:
        r = json.loads((REPO / "benchmarks" / "rust_fidelity" / "results.json").read_text(encoding="utf-8"))
        s = r.get("summary", r)
        return int(s[bucket])
    return f


def _m_racket(bucket: str):
    def f() -> int:
        r = json.loads((REPO / "benchmarks" / "racket_fidelity" / "results.json").read_text(encoding="utf-8"))
        s = r.get("summary", r)
        return int(s[bucket])
    return f


def _m_goldset_recall() -> float:
    r = json.loads((REPO / "benchmarks" / "provenance" / "channel_accuracy.json").read_text(encoding="utf-8"))
    chans = r.get("channels", r)
    vals = [v["recall"] for v in chans.values() if isinstance(v, dict) and "recall" in v]
    return min(vals)


def _m_ci_timeout() -> int:
    text = (REPO / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    m = re.search(r"^\s*timeout-minutes:\s*(\d+)", text, re.M)
    return int(m.group(1)) if m else 10**6


MEASURERS = {
    "languages.registry_min": _m_languages_registry,
    "languages.extensions_min": _m_languages_extensions,
    "counter.saving_min": _m_counter_saving,
    "claude_md.max_chars": _m_claude_md,
    "schema.core_compact_ceiling": _m_core_compact,
    "route.control_at1": _m_route_control,
    "fidelity.rust.extra": _m_rust("extra"),
    "fidelity.rust.wrong_span": _m_rust("wrong_span"),
    "fidelity.rust.undercount": _m_rust("undercount"),
    "fidelity.rust.qual_mismatch": _m_rust("qual_mismatch"),
    "fidelity.racket.extra": _m_racket("extra"),
    "fidelity.racket.wrong_span": _m_racket("wrong_span"),
    "goldset.recall_min": _m_goldset_recall,
    "ci.test_job_timeout_minutes": _m_ci_timeout,
}

# Thresholds whose verdict is carried by a test or harness exit code rather than
# a value the runner can read on its own.
DELEGATED = {
    "replay.max_relative_drop": "benchmarks/replay/run_replay.py --gate (bench tier) / .github/workflows/replay.yml",
    "schema.drift_tolerance": "tests/test_schema_budget.py (fast tier)",
    "token.grand_ratio_vs_grep": "benchmarks/harness/run_benchmark.py --floor (bench tier, network)",
    "token.per_repo_rise_max": "benchmarks/harness/run_benchmark.py --floor (bench tier, network)",
    "coverage.min": "pytest --cov-fail-under (full tier)",
    "suite.fast_seconds": "this runner, fast tier wall clock",
    "suite.full_seconds": "this runner, full tier wall clock",
    "ci.skips_ubuntu": "this runner / test.yml, pytest summary",
    "ci.skips_windows": "this runner / test.yml, pytest summary",
}


def check(tid: str, *, stamp: bool = False) -> tuple[bool | None, object]:
    e = T.get(tid)
    if tid in MEASURERS:
        observed = MEASURERS[tid]()
        ok = T.passes(tid, observed)
        print(T.verdict_line(tid, observed))
        if stamp:
            _stamp(tid, observed)
        return ok, observed
    if not DELEGATED.get(tid, "").startswith("this runner"):
        print(f"{tid:<40} crit {e['criterion']:<3} floor {e['comparator']} {e['floor']!s:<12} delegated to {DELEGATED.get(tid, '?')}")
    return None, None


def _stamp(tid: str, observed: object) -> None:
    data = json.loads(T.THRESHOLDS_PATH.read_text(encoding="utf-8"))
    for e in data["thresholds"]:
        if e["id"] == tid:
            e["measured"] = {"value": observed, "commit": _git("rev-parse", "--short", "HEAD"),
                             "date": time.strftime("%Y-%m-%d"), "env": platform.platform()}
    T.THRESHOLDS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def offline_checks(stamp: bool = False) -> tuple[bool, list[dict]]:
    ok_all = True
    rows = []
    for tid in T.load(announce=False):
        ok, obs = check(tid, stamp=stamp)
        rows.append({"id": tid, "floor": T.floor(tid), "observed": obs, "verdict": "PASS" if ok else ("FAIL" if ok is False else "DELEGATED")})
        if ok is False:
            ok_all = False
    return ok_all, rows


def _skips_floor_id() -> str:
    return "ci.skips_windows" if sys.platform.startswith("win") else "ci.skips_ubuntu"


# --------------------------------------------------------------------------- tiers

def tier_fast(result: dict) -> bool:
    t0 = time.perf_counter()
    ok = True
    print("== corpora checksums")
    bad = C.verify()
    if bad:
        ok = False
        for b in bad:
            print("  MISMATCH", b)
    else:
        print("  all pinned corpora match harness/corpora.json")
    files = TIERS["fast"]
    print(f"== fast tier: {len(files)} files")
    rc, out, secs = _run([PY, "-m", "pytest", *files, "-q", "-p", "no:cacheprovider", *_xdist_args()])
    summ = _pytest_summary(out)
    print("  ", summ["line"])
    if rc != 0:
        ok = False
        print(out[-4000:])
    print("== ruff check src/")
    rc2, out2, _ = _run([PY, "-m", "ruff", "check", "src/"])
    print("  ", out2.strip().splitlines()[-1] if out2.strip() else "")
    if rc2 != 0:
        ok = False
    print("== offline thresholds")
    ok3, rows = offline_checks()
    ok = ok and ok3
    for u in TIERS.get("unclear", []):
        print(f"REVIEW  {u['path']}: {u['question']}")
    wall = time.perf_counter() - t0
    fl = T.floor("suite.fast_seconds")
    print(T.verdict_line("suite.fast_seconds", round(wall, 2)))
    if wall > fl:
        ok = False
    result["tiers"]["fast"] = {"seconds": round(wall, 2), **{k: summ[k] for k in ("passed", "skipped", "failed")}, "ruff_ok": rc2 == 0}
    result["thresholds"] = rows
    return ok


def tier_full(result: dict) -> bool:
    t0 = time.perf_counter()
    cov = T.floor("coverage.min")
    print(f"== full tier: tests/ with --cov-fail-under={cov}")
    rc, out, secs = _run([PY, "-m", "pytest", "tests/", "-q", "-p", "no:cacheprovider", *_xdist_args(),
                          "--tb=short", "--cov=src", "--cov-report=term", f"--cov-fail-under={cov}"])
    summ = _pytest_summary(out)
    print("  ", summ["line"])
    ok = rc == 0
    if not ok:
        print(out[-6000:])
    m = re.search(r"^TOTAL\s+\d+\s+\d+\s+(\d+)%", out, re.M)
    cov_obs = int(m.group(1)) if m else None
    if cov_obs is not None:
        print(T.verdict_line("coverage.min", cov_obs))
    sid = _skips_floor_id()
    print(T.verdict_line(sid, summ["skipped"]))
    if not T.passes(sid, summ["skipped"]):
        ok = False
    wall = time.perf_counter() - t0
    print(T.verdict_line("suite.full_seconds", round(wall, 2)))
    if wall > T.floor("suite.full_seconds"):
        ok = False
    result["tiers"]["full"] = {"seconds": round(wall, 2), **{k: summ[k] for k in ("passed", "skipped", "failed")}, "coverage_pct": cov_obs}
    return ok


def tier_bench(result: dict, *, offline: bool) -> bool:
    t0 = time.perf_counter()
    ok = True
    arts: dict = {}
    for step in TIERS["bench"]:
        if step.get("network") and offline:
            print(f"== {step['name']}: SKIPPED (--offline; needs network)")
            arts[step["name"]] = {"skipped": "offline"}
            continue
        print(f"== {step['name']}: {' '.join(step['cmd'])}")
        rc, out, secs = _run([PY, *step["cmd"]])
        tail = "\n".join(out.strip().splitlines()[-3:])
        print(f"   rc={rc} {secs:.1f}s\n   " + tail.replace("\n", "\n   "))
        arts[step["name"]] = {"rc": rc, "seconds": round(secs, 2), "tail": tail}
        if rc != 0:
            ok = False
        if step.get("restore"):
            subprocess.run(["git", "checkout", "--", *step["restore"]], cwd=REPO)
    lat = RESULTS_DIR / "self_latency.json"
    if lat.exists():
        arts["self_latency"] = json.loads(lat.read_text(encoding="utf-8"))
    wall = time.perf_counter() - t0
    result["tiers"]["bench"] = {"seconds": round(wall, 2), "ok": ok}
    result["artifacts"] = arts
    return ok


def write_results(result: dict) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    p = RESULTS_DIR / "latest.json"
    p.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m harness")
    ap.add_argument("command", nargs="?", default="all",
                    choices=["fast", "full", "bench", "all", "check", "threshold", "thresholds", "corpora"])
    ap.add_argument("id", nargs="?")
    ap.add_argument("--stamp", action="store_true", help="check: write the observed value into thresholds.json `measured`")
    ap.add_argument("--offline", action="store_true", help="bench: skip steps that need the network")
    ap.add_argument("--write-results", action="store_true", help="write harness/results/latest.json")
    ap.add_argument("--pin", action="store_true", help="corpora: (re)write harness/corpora.json checksums")
    a = ap.parse_args(argv)

    if a.command == "threshold":
        print(T.floor(a.id))
        return 0
    if a.command == "thresholds":
        for tid, e in T.load(announce=False).items():
            print(f"{tid:<40} crit {e['criterion']:<3} {e['comparator']} {e['floor']!s:<10} set {e['set_at']['date']} @{e['set_at']['commit']}  measured {e.get('measured') and e['measured'].get('value')}")
        return 0
    if a.command == "corpora":
        if a.pin:
            C.pin()
            print("pinned", C.MANIFEST)
        bad = C.verify()
        print("mismatches:", bad or "none")
        return 1 if bad else 0
    if a.command == "check":
        if a.id:
            ok, _ = check(a.id, stamp=a.stamp)
            return 0 if ok in (True, None) else 1
        ok, _ = offline_checks(stamp=a.stamp)
        return 0 if ok else 1

    result = {"schema": "jcm-harness-result/v1", "date": time.strftime("%Y-%m-%dT%H:%M:%S"), "env": _env(), "tiers": {}}
    ok = True
    if a.command in ("fast", "all"):
        ok = tier_fast(result) and ok
    if a.command in ("full", "all"):
        ok = tier_full(result) and ok
    if a.command in ("bench", "all"):
        ok = tier_bench(result, offline=a.offline) and ok
    if a.write_results:
        print("results ->", write_results(result))
    print("HARNESS", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
