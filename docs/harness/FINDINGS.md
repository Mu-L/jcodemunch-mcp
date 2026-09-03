# FINDINGS from the harness build (2026-09-03, branch `harness/source-of-truth`)

Rule: a test that fails against current code is a finding, never a weakened
assertion. Product-code seams are listed here too. IDs are referenced from
the tests that carry them.

| ID | Finding | Where | Status |
|---|---|---|---|
| F-01 | `SECURITY.md` limits table says "File count limit ... 500 files"; `security.DEFAULT_MAX_INDEX_FILES` is 10,000 and `DEFAULT_MAX_FOLDER_FILES` 2,000. | `tests/test_security_md_limits_parity.py::test_file_count_limit_row_matches_code` (strict xfail) | FIXED 2026-09-03: SECURITY.md row now states 10,000 / 2,000; the xfail marker is gone and both defaults must appear in the row |
| F-02 | `STANDARD.md` §4 stated the route floor as "route@1 >= 60% on the human corpus"; the gated assertion is control-subset route@1 >= 40.0 (baseline, minus 0.1) and 55.0 is the moratorium EXIT bar, a target. Design doc repeated the 55 as a floor. | `harness/thresholds.json` route.control_at1; `tests/test_catalog_moratorium.py` | FIXED in the threshold file; STANDARD.md corrected in Phase 6 |
| F-03 | 12 config keys documented nowhere: `trusted_folders_whitelist_mode`, `server_output`, `server_output_threshold`, `worktree_base_path`, `git_root_identity`, `git_blame_enabled`, `summarizer_max_failures`, `cache_mode`, `summarize_from_docstrings`, `render_diagram_viewer_enabled`, `mermaid_viewer_path`, and `runtime_redact_enabled` (documented only as `JCODEMUNCH_RUNTIME_REDACT`). | `tests/test_config_docs_reverse_parity.py` INTERNAL_KEYS | OPEN: each needs a CONFIGURATION.md row or removal; the list may only shrink |
| F-04 | `tests/test_server.py` pins `len(tools) == 90` as a literal while the live `full` profile serves 91 (COVERAGE-MAP §4.3). The test passes because it disables `test_summarizer`; the literal is a second copy of the surface count. | `tests/test_server.py` | OPEN: LOAD-BEARING, untouched; should derive from `_build_tools_list()` |
| F-05 | Local skip count is 19 under `uv run pytest` and 13 under `PYTHONPATH=src python -m pytest` (CLAUDE.md). The delta is environmental (which optional deps the two interpreters see) and both are under the N7 floors (25 windows / 30 ubuntu). | `suite_before.log` vs CLAUDE.md | OPEN: reconcile which interpreter CLAUDE.md's line describes |
| F-06 | `benchmarks/cache_stability/results.json` is pinned by nothing and every number moved on re-run (reshuffled_share 0.139 -> 0.196). Excluded from every tier; UNCLEAR. | `harness/tiers.json` excluded/unclear | OPEN: pin a corpus snapshot or label non-deterministic |
| F-07 | Cold `search_text` was 8.8 s vs cold `search_symbols` 2.6 s on the full repo index (DISCOVERY §3). On the src-only self corpus the harness measures 251-359 ms cold and 135 ms warm p95 vs 10-13 ms for `search_symbols`: `search_text` is 10x the cost of `search_symbols` warm. | `harness/results/self_latency_three_runs.json` | OPEN: the first thing a latency profile should explain |
| F-08 | A 40 MB gitignored `.ab_bench_idx/` directory sits in the repo root and contains a recursively nested copy of itself three levels deep (an old A/B index that indexed its own store). Harmless to the harness; found by a grep for the attic scripts. | repo root, `.gitignore:55` | OPEN: delete by hand; not touched here |
| F-09 | The first draft of the self-latency harness repeated cold indexes in-process by wiping the store; the IndexStore LRU kept the old .db open and the second run failed `no such table: symbols`. Cold means a fresh process and a fresh store; the harness now does that. | `benchmarks/self_latency/measure.py` | FIXED in the harness (not a product defect) |
| F-10 | `benchmark.yml` has been warning "published benchmark numbers have moved" since 2026-08-31 (jcm tokens moved DOWN on all three repos). With `--floor` the upward direction fails; the downward direction still only warns and the artifact stays stale until re-synced. | `benchmarks/jcm_reference.json`, `results.md` | OPEN: re-sync per Practice 4 |
| F-11 | The 0x08 scar recurred during this build: a `\b` inside a non-raw Python string in a heredoc became a literal BACKSPACE in `thresholds.json` guard patterns and the ratchet's non-vacuity test caught it (an inert pattern matched nothing). Same class as `tests/test_nesting_depth_channels.py`. | `harness/thresholds.json` history | FIXED; the non-vacuity check is what saw it |
| F-12 | Under a bare `python -m harness` (the conda interpreter on this box) pytest-xdist is not importable, the fast tier ran SERIAL at 108.9-110.4 s of pytest (110.95-121.05 s wall) and failed its own 90 s ceiling on all three runs. Under `uv run python -m harness` the same tier is 45.9 s of pytest (48.4 s wall). The ceiling was NOT loosened; the runner now probes the target interpreter and announces a serial fallback. | `harness/__main__.py::_xdist_args`; `scratchpad/harness_fast_run{1,2,3}.log` vs `harness_fast_uv1.log` | FIXED in the runner; the spelling in CLAUDE.md is `uv run python -m harness` |

## Product-code seams

None. No file under `src/` was modified in this build. (`benchmarks/`,
`tests/`, `harness/`, `.github/workflows/`, `.gitignore` only.)

## Tests that fail against current code

- none since F-01 was fixed (2026-09-03).
