# Token Baselines

Per-release snapshots of token-savings + latency per tool. Used by
`analyze_perf(compare_release="1.74.0")` to detect regressions in compression
ratio or per-tool latency drift across releases.

## Schema

```jsonc
{
  "version": "1.74.0",
  "captured_at": "2026-04-25T08:34:00Z",
  "session": {
    "session_calls": 137,
    "session_tokens_saved": 1264476,
    "session_duration_s": 412.3
  },
  "tools": {
    "search_symbols": {
      "calls": 42,
      "tokens_saved": 308124,
      "p50_ms": 42.1,
      "p95_ms": 188.4
    },
    "...": "..."
  }
}
```

⚠⚠ **The latency keys are OPTIONAL and the shipped baseline does not have
them.** `capture_token_baseline.py` writes `tokens_saved` for every tool in the
session breakdown and adds `calls`/`p50_ms`/`p95_ms` only for tools the latency
ring had recorded — so a capture taken from a token-only reading produces
entries with `tokens_saved` alone. `v1.108.163.json`, the only baseline in this
directory, is exactly that shape for all three of its tools.

⚠ Do not author a baseline by hand from the schema above. A fully-populated
fixture is what hid the fabricated-delta defect: `analyze_perf` used to
difference latency against a missing key as if it were `0.0`, and every test
fixture carried the key. `analyze_perf` now returns `null` plus a
`not_comparable` entry for any field the baseline never recorded.

## Capturing

Run any representative workload against the indexer (the README's
"benchmark commands" or the harness in `benchmarks/harness/run_benchmark.py`),
then snapshot:

```bash
python benchmarks/harness/capture_token_baseline.py
```

The script writes `benchmarks/token_baselines/v{VERSION}.json` derived from
the live `get_session_stats` reading.

## Comparing

```python
analyze_perf(window="session", compare_release="1.74.0")
# returns baseline_diff (top level) with per-tool deltas, and baseline_meta
# with tools_not_fully_comparable when the baseline could not answer a field
```

The compare path is read-only — it never mutates the saved baseline file.

⚠ The diff is always against the in-memory SESSION, whatever `window` says;
`window` selects the dataset the rankings use, not the baseline comparand.
