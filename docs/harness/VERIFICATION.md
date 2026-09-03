# VERIFICATION — is the harness trustworthy? (2026-09-03)

Branch `harness/source-of-truth`. Box: Windows 11 10.0.26200, Python 3.12.4
(`.venv` via uv 0.9.5), 24 logical CPUs. Every number below is from a log in
the session scratchpad, named beside it.

## 1. Three runs on the same commit

`uv run python -m harness fast --write-results`, three consecutive runs:

| run | pytest | wall (ceiling 90 s) | offline threshold observations |
|---|---|---|---|
| 1 | 1159 passed, 7 skipped, 1 xfailed, 45.88 s | 48.42 s PASS | identical to run 3 |
| 2 | 1159 passed, 7 skipped, 1 xfailed, 48.93 s | 50.31 s PASS | identical to run 3 |
| 3 | 1159 passed, 7 skipped, 1 xfailed, 52.46 s | 53.90 s PASS | see below |

Observations were byte-identical across runs (`harness_fast_uv{2,3}.json`
compared as dicts): rust/racket buckets 0, goldset recall 1.0, core_compact
3,972, counter saving 0.9587, route control 40.0, languages 79/164, CLAUDE.md
136,359 chars, CI timeout 20. The only quantity that varied was wall clock,
within 5.5 s (11%) of the median, inside the 90 s ceiling with margin.

`uv run python -m harness bench --offline --write-results`, one run
(`harness_bench_run1.log`): every step rc=0, 31.24 s wall; self-latency
artifact within every floor. The three self-latency runs that SET the floors
are in `harness/results/self_latency_three_runs.json` (spreads: cold index
0.1 s, one-file reindex 2.8 ms, warm p95 at most 2.7 ms across the four
tools; `search_text` cold spread 108 ms, which is why cold values carry no
floor).

⚠ Three earlier runs under a bare `python -m harness` (`harness_fast_run{1,2,3}.log`)
FAILED the ceiling at 110.95 / 112.44 / 121.05 s because that interpreter has
no xdist and pytest ran serial (FINDINGS F-12). The ceiling was not moved;
the runner now probes the target interpreter and says so.

## 2. Deliberate regression (throwaway branch, reverted)

`throwaway/regression-A`: wrapped `search_symbols` in a 40 ms sleep
(product code, one file), ran `benchmarks/self_latency/measure.py`.
Output (`regressionA.json`):

```
latency.search_symbols_warm_p95_ms       crit 5   floor <= 23           observed 54.6         FAIL
```

The message names the criterion (5), the Floor (<= 23) and the observed
value (54.6). The other five floors stayed PASS, so the failure is located,
not global. Branch deleted, `src/` restored, `git status` clean.

## 3. Historical bug reintroduced (throwaway branch, reverted)

`throwaway/regression-B`: reintroduced #572 (the shared result cache handing
out its stored object) by removing both `_isolate` calls in
`storage/token_tracker.py` lines 365 and 373. Ran the two LOAD-BEARING files
that guard it:

```
7 failed, 22 passed in 1.89s    (tests/test_result_cache_isolation.py, tests/test_result_cache.py)
```

The migrated tests still catch it. Branch deleted, `src/` restored.

## 4. Tier ceilings on this machine

| tier | measured | ceiling | verdict |
|---|---|---|---|
| fast | 48.42 / 50.31 / 53.90 s | 90 s (`suite.fast_seconds`) | PASS x3 |
| full | 141.79 s post-build (`suite_after_build.log`), 188.43 s pre-build (`suite_before.log`) | 360 s (`suite.full_seconds`) | PASS |
| bench (offline) | 31.24 s | 300 s (design) | PASS |

## 5. Network

`tests/conftest.py::_no_network` raises on any non-loopback `socket.connect`
for the whole session; the full suite ran green under it (9,193 passed,
19 skipped, 1 xfailed after the build; the one failure was the harness's own
subprocess-encoding defect, fixed in `20cd077`). The bench tier's only
network step (`token_benchmark`) is declared `network: true` in
`harness/tiers.json` and was skipped under `--offline`, as printed in the
log. No harness command reached the network.

## 6. Suite before and after the migration

| | passed | skipped | failed | xfailed | total | wall |
|---|---|---|---|---|---|---|
| before (`f68a728`) | 9,155 | 19 | 0 | 0 | 9,174 | 188.43 s |
| after build (`db12157`) | 9,193 | 19 | 1 (F-12's cause, fixed next commit) | 1 | 9,214 | 141.79 s |
| final (`74e1859`+docs) | 9194 | 19 | 0 | 1 | 9,214 | 146.99 s |

The +40 are the new gate tests; the xfail is F-01. No test that passed
before fails after.
