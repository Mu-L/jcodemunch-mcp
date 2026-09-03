# attic: benchmark scripts whose premise is gone

Moved here 2026-09-03 by the harness build (docs/harness/DESIGN.md section 6),
not deleted: none has a test depending on it, and each still documents how a
measurement was once taken. Classification and evidence in
docs/harness/ARCHAEOLOGY.md section B.

| script | what it measured | why it is stale |
|---|---|---|
| `profile_backpressure.py` | watcher backpressure, 72 checks (720049b, 2026-03-23) | exercises `wait_for_fresh` and the staleness `_meta`, both retired in 0d90e76 (2026-03-28) |
| `profile_config_regression.py` | cold/warm all-tool timings against a local FlatCAM_EVO checkout (2a6880c) | local-only corpus, no committed artifact; superseded by `benchmarks/self_latency/` |
| `profile_language_filter.py` | `languages=["python"]` vs none on the same local corpus | same |
| `ab_v1_70_0.py` | v1.70.0 `detail_level` A/B (76cd23e, 2026-04-19) | one-release A/B; the setting it compared is unchanged since |

Nothing here is run by any tier. Delete only through `harness/retired.json`
if a test is ever attached to one of them.
