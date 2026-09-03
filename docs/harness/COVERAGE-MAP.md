# COVERAGE MAP: STANDARD.md criteria against the existing tests and benchmarks

2026-09-03, branch `harness/source-of-truth` at `f68a728`. Built from
`ARCHAEOLOGY.md` section 1 (491 test files, each mapped to a criterion) and
section 2 (benchmark scripts and artifacts). "Pass/fail" means an assertion
exists that fails a build; "number" means a figure a human reads.

## 1. Criteria to artifacts

### 1. Correctness of what is returned

**Existing artifacts:** 128 files: `test_architecture_metrics.py`, `test_architecture_tools.py`, `test_assemble_task_context.py`, `test_blast_radius.py`, `test_bm25_correctness.py`, `test_byte_offset_symbol_names.py`, `test_call_extraction.py`, `test_call_graph_ast.py`, `test_call_hierarchy.py`, `test_check_delete_safe.py`, `test_check_edit_safe.py`, `test_check_references.py`, `test_check_rename_safe.py`, `test_churn_rate.py`, `test_class_hierarchy.py`, `test_cleanup.py`, `test_complexity.py`, `test_confidence.py`, `test_confidence_score_scale.py`, `test_context_providers.py`, `test_cross_repo.py`, `test_dbt_provider.py`, `test_dead_code_v2.py`, `test_decorator_awareness.py`, `test_decorator_census.py`, `test_decorator_routes.py`, `test_delivery_metrics.py`, `test_dispatch_resolution.py`, `test_dispatcher.py`, `test_dispatcher_arg_mutation.py`, `test_django_provider.py`, `test_endpoint_impact.py`, `test_endpoint_infra_impact.py`, `test_express_provider.py`, `test_extraction_candidates.py`, `test_file_summaries.py`, `test_find_dead_code.py`, `test_find_implementations.py`, `test_find_importers.py`, `test_find_similar_symbols.py`, `test_format.py`, `test_fqn.py`, `test_framework_profiles.py`, `test_fuzzy_search.py`, `test_generic_hardened.py`, `test_get_context_bundle.py`, `test_get_file_outline_integration.py`, `test_get_file_tree.py`, `test_get_group_contracts.py`, `test_get_untested_symbols.py`, `test_hardening.py`, `test_hotspots.py`, `test_identity_normalized_tier.py`, `test_index_dependency.py`, `test_investigator_deletion_safety.py`, `test_js_class_field_phantom_methods.py`, `test_local_encoder.py`, `test_lsp_bridge.py`, `test_nesting_depth_channels.py`, `test_next_entry_points.py`, `test_nextjs_provider.py`, `test_nuxt_provider.py`, `test_nuxt_srcdir.py`, `test_pagerank.py`, `test_parity_map.py`, `test_parser.py`, `test_plan_refactoring.py`, `test_plan_turn.py`, `test_project_intel.py`, `test_property_based.py`, `test_psr4.py`, `test_python_relative_imports.py`, `test_python_sibling_imports.py`, `test_racket_fidelity.py`, `test_racket_lang_gate.py`, `test_racket_language.py`, `test_racket_reader.py`, `test_rails_provider.py`, `test_related_symbols.py`, `test_render_diagram.py`, `test_replay_metrics.py`, `test_retrieval_tools.py`, `test_reuse_audit.py`, `test_route_utils.py`, `test_runtime_phase1.py`, `test_runtime_phase3.py`, `test_runtime_phase4.py`, `test_runtime_phase5.py`, `test_rust_fidelity.py`, `test_scip_evidence.py`, `test_search_ast_encoder_contract.py`, `test_search_columns.py`, `test_search_perf.py`, `test_semantic_search.py`, `test_signal_fusion.py`, `test_suggest_queries.py`, `test_symbol_complexity.py`, `test_symbol_diff.py`, `test_tectonic_map.py`, `test_tier1_roundtrip.py`, `test_toml_end_line.py`, `test_ts_type_only_imports.py`, `test_undeclared_table_guard.py`, `test_v1_108_101.py`, `test_v1_108_103.py`, `test_v1_108_118.py`, `test_v1_108_119.py`, `test_v1_108_120.py`, `test_v1_108_137.py`, `test_v1_108_173.py`, `test_v1_108_224.py`, `test_v1_108_226.py`, `test_v1_108_229.py`, `test_v1_108_231.py`, `test_v1_108_273.py`, `test_v1_108_277.py`, `test_v1_108_58.py`, `test_v1_108_59.py`, `test_v1_108_63.py`, `test_v1_108_78.py`, `test_v1_108_80.py`, `test_v1_80_10_dead_code_intra_file_calls.py`, `test_v1_80_7_dead_code_js_reexports.py`, `test_v1_80_9_lodash_class.py`, `test_winnow_symbols.py`, `test_yaml_byte_extent.py`, `test_yaml_key_coercion.py`, `test_yaml_line_location.py`

**Pass/fail or number:** `test_rust_fidelity*.py`, `test_racket_*.py` (frozen oracles, four buckets = 0) and `test_channel_accuracy.py` (recall 1.0) are pass/fail on Floors; `replay.yml --gate 0.02` is pass/fail in CI; the ~120 parser and tool regression pins are pass/fail on specific defects. `benchmarks/deadcode_eval/` (fp_rate 0.6292) is a NUMBER only.

**Missing to make it a gate:** A repo-wide `search_symbols` precision/recall number with a floor; oracles beyond Rust/Racket; a replay set larger than 10 self queries. `deadcode_eval` needs a coverage run and a floor on fp_rate before it can gate.

### 2. Token reduction per task

**Existing artifacts:** 13 files: `test_benchmark_grep_baseline.py`, `test_get_repo_map.py`, `test_savings_baseline.py`, `test_search_result_cache.py`, `test_search_symbols_defaults.py`, `test_token_budget_context.py`, `test_truncated_flag.py`, `test_v1_108_129.py`, `test_v1_108_158.py`, `test_v1_108_167.py`, `test_v1_108_208.py`, `test_v1_108_55.py`, `test_v1_108_70.py`

**Pass/fail or number:** `test_benchmark_reference.py` (30) and `test_provenance.py` are pass/fail on SYNC (pins present, artifact mirrors agree, no hand-typed constant); they do not assert the ratio. `benchmark.yml` recomputes weekly and only WARNS. `results.md`/`jcm_reference.json` are numbers.

**Missing to make it a gate:** A floor assertion on the recomputed ratio (>= 20x) and on per-repo jcm tokens (<= committed + 10%) that fails the workflow; a fixture-based offline variant so the fast tier can at least check the harness still runs.

### 3. Index freshness and incremental cost

**Existing artifacts:** 82 files: `test_absence_wiring_guard.py`, `test_bm25_cache_single_flight.py`, `test_branch_indexing.py`, `test_dead_code_corpus_adequacy.py`, `test_deferred_summarization.py`, `test_embed_drift.py`, `test_embedding_model_change.py`, `test_framework_build_trees_are_skipped.py`, `test_freshness.py`, `test_generation_contract.py`, `test_get_changed_symbols.py`, `test_git_root_identity.py`, `test_git_sha_verification.py`, `test_identity_mode.py`, `test_incremental.py`, `test_index_file.py`, `test_index_file_head_advance.py`, `test_local_integration.py`, `test_mtime_optimization.py`, `test_negative_evidence.py`, `test_pack_index_survives_orphan_sweep.py`, `test_parse_cache.py`, `test_parser_generation_upgrade.py`, `test_pid_reuse_identity.py`, `test_process_locks.py`, `test_racket_config_reparse.py`, `test_refresh_campaign.py`, `test_refresh_corpus_unreadable.py`, `test_register_edit.py`, `test_reindex_state.py`, `test_repeat_root_walk_additional.py`, `test_resolve_repo.py`, `test_resolve_repo_nested_repo_boundary.py`, `test_result_cache.py`, `test_result_cache_isolation.py`, `test_runtime_phase0.py`, `test_search_result_cache.py`, `test_selective_snapshot.py`, `test_sqlite_store.py`, `test_storage.py`, `test_telemetry_db_skip.py`, `test_v1_108_0.py`, `test_v1_108_105.py`, `test_v1_108_106.py`, `test_v1_108_107.py`, `test_v1_108_108.py`, `test_v1_108_126.py`, `test_v1_108_127.py`, `test_v1_108_151.py`, `test_v1_108_160.py`, `test_v1_108_166.py`, `test_v1_108_168.py`, `test_v1_108_169.py`, `test_v1_108_175.py`, `test_v1_108_176.py`, `test_v1_108_177.py`, `test_v1_108_178.py`, `test_v1_108_179.py`, `test_v1_108_180.py`, `test_v1_108_181.py`, `test_v1_108_183.py`, `test_v1_108_184.py`, `test_v1_108_185.py`, `test_v1_108_190.py`, `test_v1_108_191.py`, `test_v1_108_192.py`, `test_v1_108_193.py`, `test_v1_108_200.py`, `test_v1_108_209.py`, `test_v1_108_210.py`, `test_v1_108_223.py`, `test_v1_108_225.py`, `test_v1_108_227.py`, `test_v1_108_269.py`, `test_v1_108_56.py`, `test_verdict_coverage_calibration.py`, `test_watch_once.py`, `test_watcher_dynamic.py`, `test_watcher_hash_delta.py`, `test_watcher_knob_parity.py`, `test_watcher_lock.py`, `test_watcher_memory_cache.py`

**Pass/fail or number:** The absence-claim, cache-isolation, subject-state, freshness-classification and corpus-adequacy pins are pass/fail on properties. Incremental and cold index COST exists only as two hand measurements in DISCOVERY.md section 3 (738 ms, 13.88 s).

**Missing to make it a gate:** A `benchmarks/self_latency/` harness that writes cold-index and one-file-reindex timings for the self corpus and a floor (2x committed) in the threshold file.

### 4. Tool-surface discipline

**Existing artifacts:** 33 files: `test_audit_agent_config.py`, `test_catalog_moratorium.py`, `test_counter.py`, `test_counter_surface_stability.py`, `test_description_smells.py`, `test_dispatch_schema_parity.py`, `test_embedding_provider_advice.py`, `test_generated_policy_matches_tools_list.py`, `test_guide_respects_disabled_tools.py`, `test_init_policy_matches_surface.py`, `test_kind_enum_is_derived.py`, `test_mcp_instructions.py`, `test_prompts.py`, `test_readonly_annotations.py`, `test_response_cap.py`, `test_retrieval_counterfactual.py`, `test_route_recall_artifacts_are_fresh.py`, `test_schema_baseline_transcription.py`, `test_schema_budget.py`, `test_search_ast_encoder_contract.py`, `test_server.py`, `test_surface_cli.py`, `test_surface_offer.py`, `test_tier_resolver.py`, `test_tier_runtime.py`, `test_tier_switch_cost.py`, `test_tool_registration.py`, `test_v1_108_104.py`, `test_v1_108_110.py`, `test_v1_108_114.py`, `test_v1_108_153.py`, `test_v1_108_156.py`, `test_v1_108_271.py`

**Pass/fail or number:** `test_schema_budget.py` (ceiling 4,000 + 5% drift), `test_counter_surface_stability.py` (byte pin), `test_schema_baseline_transcription.py`, `test_description_smells.py`, `test_catalog_moratorium.py`, `test_route_recall_artifacts_are_fresh.py`, `test_tier_switch_cost.py` are all pass/fail. WARNING: STANDARD section 4 states the moratorium bar as route@1 >= 60% on the human corpus; ARCHAEOLOGY section C shows the gated bar moved on 2026-08-02 to the held-out CONTROL subset at >= 55% (baseline 40.0%, n=20) and the aggregate is deliberately NOT gated. The standard must be corrected to the test, not the test to the standard.

**Missing to make it a gate:** Nothing for enforcement. `tests/test_server.py` pins `len(tools) == 90` as a literal (live: 91), a second copy of the surface count; it should read the count from `_build_tools_list()` or the baseline.

### 5. Latency

**Existing artifacts:** 15 files: `test_fast_path_no_hydration.py`, `test_integrity_check_cost.py`, `test_progress.py`, `test_provider_metadata_and_perf.py`, `test_resolve_repo.py`, `test_search_perf.py`, `test_tsconfig_walk_cost.py`, `test_v1_108_147.py`, `test_v1_108_171.py`, `test_v1_108_172.py`, `test_v1_108_182.py`, `test_v1_108_2.py`, `test_v1_108_206.py`, `test_v1_108_81.py`, `test_v1_108_83.py`

**Pass/fail or number:** `test_analyze_perf_totals.py`, `test_v1_108_182.py` (provider/parse budgets), heartbeat and watchdog pins are pass/fail on BEHAVIOUR (a budget fires, a heartbeat emits). No test or artifact asserts a duration of any tool call.

**Missing to make it a gate:** The self-corpus latency harness (same as criterion 3) with per-tool warm p95 and a 2x floor; a documented runner-noise band before the floor tightens.

### 6. Install, configuration and client friction

**Existing artifacts:** 78 files: `test_adaptive_languages.py`, `test_anthropic_optional.py`, `test_cache_mode.py`, `test_claude_md_policy.py`, `test_cli.py`, `test_cli_output_encoding.py`, `test_code_index_path_is_honoured.py`, `test_config.py`, `test_config_check_hooks.py`, `test_config_check_matches_resolver.py`, `test_config_lazy_load.py`, `test_config_set.py`, `test_config_watcher_keys.py`, `test_configuration_md_defaults.py`, `test_copilot_hook.py`, `test_count_cap_end_to_end.py`, `test_delete_index_cli.py`, `test_docs_config_parity.py`, `test_explicit_embed_model_wins.py`, `test_extra_extensions.py`, `test_gcm.py`, `test_groq_explainer.py`, `test_groq_voice.py`, `test_handshake_watchdog.py`, `test_hook_output_channels.py`, `test_hook_steering_fixes.py`, `test_hooks.py`, `test_init.py`, `test_init_client_schemas.py`, `test_init_hooks_paths.py`, `test_init_minimal.py`, `test_install_copilot_hooks.py`, `test_install_pack.py`, `test_install_uninstall.py`, `test_org_license.py`, `test_pack_api_transport.py`, `test_pack_marker_not_a_repo_index.py`, `test_path_entry_point_invariants.py`, `test_path_map.py`, `test_post_tool_use_hook.py`, `test_process_code_freshness.py`, `test_readonly_annotations.py`, `test_render_diagram_integration.py`, `test_render_diagram_viewer.py`, `test_runtime_phase6.py`, `test_schtasks_locale.py`, `test_security_exclusions_are_project_overridable.py`, `test_share_savings.py`, `test_size_cap_end_to_end.py`, `test_skills.py`, `test_source_drift.py`, `test_stdio_guard.py`, `test_storage_path_resolution.py`, `test_streamable_http_integration.py`, `test_streamable_http_sessions.py`, `test_strict_deny_requires_resolvable_target.py`, `test_summarizer.py`, `test_v1_108_115.py`, `test_v1_108_121.py`, `test_v1_108_122.py`, `test_v1_108_128.py`, `test_v1_108_150.py`, `test_v1_108_159.py`, `test_v1_108_164.py`, `test_v1_108_194.py`, `test_v1_108_199.py`, `test_v1_108_207.py`, `test_v1_108_57.py`, `test_v1_108_64.py`, `test_v1_108_72.py`, `test_v1_108_84.py`, `test_v1_108_85.py`, `test_v1_108_86.py`, `test_v1_108_92.py`, `test_version_check.py`, `test_watch_all.py`, `test_watch_claude.py`, `test_watcher_serve.py`

**Pass/fail or number:** `init`/`uninstall`/`upgrade_config`/hook/client-config pins, `test_config_isolation_guard.py`, `test_docs_config_parity.py` (documented -> exists, one direction), `test_mcp_instructions.py`, `test_cli_env_split.py` are pass/fail. The published-artifact handshake is manual; CLIENTS.md configs are unparsed.

**Missing to make it a gate:** A reverse config-parity test with an INTERNAL_KEYS allowlist (16 keys undocumented today); a CLIENTS.md block parser; a post-publish handshake job.

### 7. Stability across releases

**Existing artifacts:** 15 files: `test_call_references_model.py`, `test_dependency_graph_imports_alias.py`, `test_find_references_line_numbers.py`, `test_future_version_no_false_absence.py`, `test_license_identifier_agreement.py`, `test_lockfile_version_sync.py`, `test_migration.py`, `test_offload_contract.py`, `test_plugin_manifest_sync.py`, `test_route_binary_pilot_is_frozen.py`, `test_runtime_phase2.py`, `test_runtime_phase7.py`, `test_server_json_sync.py`, `test_v1_108_74.py`, `test_whatsnew.py`

**Pass/fail or number:** `test_server_json_sync.py`, `test_plugin_manifest_sync.py`, `test_lockfile_version_sync.py`, `test_whatsnew*.py`, `test_claude_md_rotation.py`, the replay gate, and the byte-pinned counter surface are pass/fail.

**Missing to make it a gate:** Required status checks on `main` (only `license/cla` today) and a release pre-flight that reads CI for HEAD. Both are settings/scripts, not tests.

### 8. Security and integrity of what is indexed

**Existing artifacts:** 28 files: `test_build.py`, `test_build_tree_spellings.py`, `test_credentials.py`, `test_file_io_encoding_guard.py`, `test_hardening.py`, `test_install_pack_member_confinement.py`, `test_org_http.py`, `test_paid_embeddings_optin.py`, `test_rate_limit.py`, `test_redact.py`, `test_response_cap.py`, `test_runtime_phase0.py`, `test_runtime_phase6.py`, `test_savings_by_tool.py`, `test_scip_evidence.py`, `test_sdist_exclusions.py`, `test_secret_classifier.py`, `test_security.py`, `test_security_disclosure.py`, `test_subprocess_encoding_guard.py`, `test_summarize_from_docstrings.py`, `test_tools.py`, `test_v1_108_163.py`, `test_v1_108_234.py`, `test_v1_108_270.py`, `test_v1_108_71.py`, `test_v1_108_73.py`, `test_v1_108_95.py`

**Pass/fail or number:** `test_build.py`, `test_sdist_exclusions.py` (allowlist both directions), `test_security*.py`, `test_security_disclosure.py`, redaction, path-validation, symlink-escape, zip-slip and CACHEDIR.TAG pins are pass/fail; the CI tar grep is pass/fail.

**Missing to make it a gate:** A SECURITY.md limits-table parity test (the "500 files" discrepancy); a dependency audit step; a decision on empty `trusted_folders`.

### 9. Observability and telemetry honesty

**Existing artifacts:** 72 files: `test_analyze_perf_totals.py`, `test_blast_radius_package_granular_verdict.py`, `test_cache_hit_rate_basis.py`, `test_call_outcome_contract.py`, `test_capability_certificate.py`, `test_counts_survive_truncation.py`, `test_digest.py`, `test_get_file_risk.py`, `test_git_history_coverage.py`, `test_health_radar.py`, `test_health_radar_action.py`, `test_index_channel_tri_state.py`, `test_issue_456_perf_correlation.py`, `test_list_repos.py`, `test_meta_disclosure.py`, `test_missing_content_cache_is_reported.py`, `test_observatory.py`, `test_observatory_clone_depth.py`, `test_offload.py`, `test_org_rollup.py`, `test_parse_warnings.py`, `test_perf_db_path_resolution.py`, `test_perf_telemetry.py`, `test_perf_trim_is_per_database.py`, `test_provenance.py`, `test_pulse.py`, `test_ranking_ledger.py`, `test_receipt.py`, `test_repo_health.py`, `test_retrieval_counterfactual.py`, `test_retrieval_inflation.py`, `test_reuse_audit.py`, `test_runtime_phase2.py`, `test_runtime_phase3.py`, `test_runtime_phase7.py`, `test_savings_baseline.py`, `test_savings_by_tool.py`, `test_savings_two_carriers.py`, `test_savings_usd_basis.py`, `test_session_journal.py`, `test_session_snapshot.py`, `test_session_state.py`, `test_skill_candidates.py`, `test_stop_rule.py`, `test_suggest_corrections.py`, `test_taskcomplete_real_contract.py`, `test_tool_surface_clamp.py`, `test_transcript_roots.py`, `test_turn_budget.py`, `test_unloadable_index_rebuild_disclosure.py`, `test_v1_108_102.py`, `test_v1_108_134.py`, `test_v1_108_136.py`, `test_v1_108_139.py`, `test_v1_108_146.py`, `test_v1_108_148.py`, `test_v1_108_152.py`, `test_v1_108_162.py`, `test_v1_108_165.py`, `test_v1_108_174.py`, `test_v1_108_186.py`, `test_v1_108_187.py`, `test_v1_108_188.py`, `test_v1_108_189.py`, `test_v1_108_201.py`, `test_v1_108_211.py`, `test_v1_108_230.py`, `test_v1_108_272.py`, `test_v1_108_275.py`, `test_v1_108_276.py`, `test_v1_108_99.py`, `test_weight_tuning.py`

**Pass/fail or number:** Tri-state, `*_basis`, refusal-over-zero, ledger-trust and stop-rule pins are pass/fail on properties. There is no enumeration: deleting one of these files fails nothing.

**Missing to make it a gate:** A `tests/test_standard_invariants.py` that lists every honesty pin by name and fails if one is missing or collects zero tests.

### 10. Breadth of language support

**Existing artifacts:** 32 files: `test_al.py`, `test_arrow_functions.py`, `test_asm_language.py`, `test_astro.py`, `test_blade.py`, `test_constant_extraction_guard.py`, `test_css.py`, `test_dart_imports.py`, `test_gleam_imports.py`, `test_go_routers_provider.py`, `test_html_file_class.py`, `test_json.py`, `test_languages.py`, `test_laravel_provider.py`, `test_luau_language.py`, `test_new_languages.py`, `test_new_languages_v143.py`, `test_racket_collections.py`, `test_racket_language.py`, `test_razor.py`, `test_runtime_phase4.py`, `test_rust_fidelity.py`, `test_scala_parser.py`, `test_sql_language.py`, `test_svelte.py`, `test_swift_parser.py`, `test_templates.py`, `test_ts_module_extensions.py`, `test_v1_108_125.py`, `test_v1_108_161.py`, `test_v1_108_281.py`, `test_yaml_language.py`

**Pass/fail or number:** Per-language extractor tests are pass/fail on specific constructs; language-support doc parity pins exist. Nothing pins the COUNT.

**Missing to make it a gate:** A test pinning `len(LANGUAGE_REGISTRY)`/`len(LANGUAGE_EXTENSIONS)` against the threshold file, failing on a decrease.

### N1. Test-suite runtime ceiling

**Existing artifacts:** none

**Pass/fail or number:** Observed only (188 s `-n auto` here; CI 9m44s-15m59s). No assertion.

**Missing to make it a gate:** `timeout-minutes` on the CI job; the harness records its own wall clock per tier.

### N2. Coverage floor

**Existing artifacts:** none

**Pass/fail or number:** `--cov-fail-under=74` in CI is pass/fail; the value is UNKNOWN locally.

**Missing to make it a gate:** Emit `coverage.json` as an artifact; record the percentage per release.

### N3. Lint and types

**Existing artifacts:** none

**Pass/fail or number:** `ruff check src/` is a CI job (pass/fail). `tests/` is unlinted (292 findings); no type checker.

**Missing to make it a gate:** Auto-fix `tests/`, add it to the job; baseline a type checker as a ratchet.

### N4. Deterministic benchmark output

**Existing artifacts:** 11 files: `test_benchmark_reference.py`, `test_channel_accuracy.py`, `test_deadcode_eval_harness.py`, `test_racket_fidelity_artifacts.py`, `test_replay_metrics.py`, `test_route_binary_pilot_is_frozen.py`, `test_route_recall_artifacts_are_fresh.py`, `test_rust_fidelity_artifacts.py`, `test_schema_baseline_transcription.py`, `test_v1_108_149.py`, `test_v1_108_228.py`

**Pass/fail or number:** `test_route_recall_artifacts_are_fresh.py`, `test_channel_accuracy.py`, `test_rust_fidelity_artifacts.py`, `test_racket_fidelity_artifacts.py`, `test_provenance.py` re-run or re-derive artifacts and are pass/fail. `cache_stability/results.json` is pinned by nothing and moved on re-run.

**Missing to make it a gate:** Pin or label `cache_stability`; a checksum manifest for every corpus the harness reads.

### N5. No network access during tests

**Existing artifacts:** 1 files: `test_sdist_exclusions.py`

**Pass/fail or number:** By inspection only (one grep-based pin in `test_v1_108_226.py` checks a redirect flag, not sockets).

**Missing to make it a gate:** A session-scoped socket-blocking fixture with a `network` marker opt-out.

### N6. Agent-instruction budget

**Existing artifacts:** 4 files: `test_claude_md_rotation.py`, `test_claude_md_size.py`, `test_cli_env_split.py`, `test_key_files_split.py`

**Pass/fail or number:** `test_claude_md_size.py` (BUDGET 140,000) and `test_claude_md_rotation.py` are pass/fail. WARNING: ARCHAEOLOGY section C shows BUDGET was LOOSENED 130k -> 140k on 2026-08-27 (jjg) with the 10k buffer declared the last; the standard records 140,000 and must never raise it.

**Missing to make it a gate:** Nothing.

### N7. CI skip count

**Existing artifacts:** 3 files: `test_ci_env_reproduce_command.py`, `test_config_isolation_guard.py`, `test_optional_dep_skips_are_visible.py`

**Pass/fail or number:** Observed only. `test_optional_dep_skips_are_visible.py` keeps skips VISIBLE but nothing bounds the count.

**Missing to make it a gate:** Parse the summary line in the workflow and assert <= 30 ubuntu / <= 25 windows; reconcile the 19-vs-13 local delta first.

## 2. Inverse: tests that map to no criterion

1 file(s): `test_agent_selector.py`.

| test | what it guards | verdict |
|---|---|---|
| `test_agent_selector.py` | the `agent_selector` config map (per-client tool selection) | UNCLEAR in ARCHAEOLOGY section 5; proposed criterion 6a below. Untouched. |

The three STRUCTURAL files (`test_context_providers.py`,
`test_deadcode_eval_harness.py`, `test_render_diagram_integration.py`) map to
criteria 3, 1 and 6 through what they support; none is orphaned.

## 3. Proposed additions to the standard (not added yet)

| Proposed criterion | Evidence it is missing | Tests already guarding it |
|---|---|---|
| **6a. Client-specific surface selection**: the `agent_selector`/`model_tier_map`/`announce_model` path serves the right tier per client, and a switch is priced | `test_agent_selector.py` maps nowhere; `tier_switch_cost` and `set_tool_tier` pins sit under 4 by proximity, not by statement | `test_agent_selector.py`, `test_tier_switch_cost.py`, `test_v1_108_66*.py` |
| **3a. Multi-process coordination**: one watcher per repo, `indexwrite` lock, PID liveness, contended-lock reporting (#557, #375, the .261 47-minute outlier) | 14 files pin process locks and the registry; the standard mentions the lock only in passing under 3 | `test_process_locks*.py`, `test_v1_108_105.py`, `test_v1_108_108.py`, `test_watcher_*.py` |
| **9a. Evidence receipts**: `jcodemunch.evidence/v1` envelopes, fail-closed id reuse, deterministic `envelope_json` | 11 files under `evidence/` map to 9 by habit; receipts are a contract with jdoc/jdata parity, which 9 does not state | `test_evidence_*.py`, `test_producers*.py` |
| **8a. Runtime-trace ingestion safety**: redaction chokepoint, body cap, gzip-bomb guard, 503 without token | 10 runtime files map to 8; the standard's 8 names only indexing-side controls | `test_runtime_*.py`, `test_http_routes*.py` |

Each is a sub-criterion of an existing axis, so the ranking in `NICHE.md` does
not change; each needs a criterion block so its pins are enumerated by item 4
of the enforcement plan.

## 4. Corrections the coverage map forces on STANDARD.md (to apply in Phase 6)

1. Section 4 Floor "route@1 at or above 60%": the gated bar is the held-out
   CONTROL subset at >= 55% (2a1cc2a, v1.108.220); the 60% aggregate is a
   number, not a gate. Correct the standard to the test.
2. Section 2: `test_benchmark_reference.py` asserts SYNC, not the ratio; the
   standard's "MEASURED (weekly, warning-only)" is accurate but the Floor has
   no assertion anywhere. Status stays PARTIALLY until item 1 of the plan.
3. `tests/test_server.py` literal `90` vs the live 91: a second copy of a
   count the standard says must be recomputed. Log as a FINDING in Phase 4;
   the test is LOAD-BEARING (it guards `test_summarizer` being disabled by
   default) and is not retired.
4. Section N6: record that 140,000 was a loosening, so the floor is "no
   higher than 140,000", never "whatever the test says".
