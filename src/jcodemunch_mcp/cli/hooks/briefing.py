"""SubagentStart: condensed, surface-aware repo orientation."""

import logging
import os

from ._common import (
    _emit_additional_context,
    _iter_loaded_repos,
    _norm_path,
    _note_transcript_root,
    _path_overlaps,
    _read_hook_payload,
)

logger = logging.getLogger(__name__)


def run_subagentstart() -> int:
    """SubagentStart hook: inject condensed repo orientation for spawned agents.

    Reads hook JSON from stdin. Returns a compact briefing containing:
      - Repo stats (files, symbols, languages)
      - Top 15 structurally central symbols (PageRank)
      - Available jCodemunch tool catalog

    Returns exit code (always 0).
    """
    data = _read_hook_payload()
    if data is None:
        return 0
    _note_transcript_root(data)

    try:
        from ...storage import IndexStore
        store = IndexStore()
        repos = store.list_repos()
    except Exception:
        return 0

    if not repos:
        return 0

    # Scope to the repo(s) containing the subagent's cwd when it names one:
    # hydrating + PageRanking EVERY indexed repo per spawn is minutes-scale on
    # big multi-repo boxes, and a briefing about unrelated repos is noise.
    # No cwd (or no overlap) keeps the brief-everything fallback.
    cwd = data.get("cwd", "")
    if isinstance(cwd, str) and cwd:
        try:
            norm_cwd = _norm_path(cwd)
            scoped = [
                e for e in repos
                if (sr := (e.get("source_root") or "").strip())
                and _path_overlaps(norm_cwd, [_norm_path(sr)])
            ]
            if scoped:
                repos = scoped
        except Exception:
            logger.debug("cwd scoping failed", exc_info=True)

    parts = ["## jCodemunch Repo Briefing"]

    for repo_id, idx in _iter_loaded_repos(store, repos):
        # Stats
        n_files = len(idx.source_files)
        n_symbols = len(idx.symbols)
        langs = set()
        for sym in idx.symbols:
            lang = sym.get("language")
            if lang:
                langs.add(lang)
        lang_str = ", ".join(sorted(langs)[:8]) if langs else "unknown"

        parts.append(f"\n### {repo_id}")
        parts.append(f"- **Files:** {n_files} | **Symbols:** {n_symbols} | **Languages:** {lang_str}")

        # Top central symbols via PageRank
        if idx.imports and idx.source_files:
            try:
                from ...tools.pagerank import compute_pagerank
                pr_scores, _ = compute_pagerank(
                    idx.imports, idx.source_files,
                    alias_map=getattr(idx, "alias_map", None),
                    psr4_map=getattr(idx, "psr4_map", None),
                )
                if pr_scores:
                    top_files = sorted(pr_scores.items(), key=lambda x: x[1], reverse=True)[:30]
                    top_file_set = {f for f, _ in top_files}
                    sym_pr = sorted(
                        [(sym, pr_scores.get(sym.get("file", ""), 0.0)) for sym in idx.symbols if sym.get("file", "") in top_file_set],
                        key=lambda x: x[1],
                        reverse=True,
                    )[:15]
                    if sym_pr:
                        parts.append("- **Key symbols:**")
                        for sym, _ in sym_pr:
                            parts.append(f"  - `{sym.get('name', '?')}` ({sym.get('kind', '')}, {sym.get('file', '')}:{sym.get('line', 0)})")
            except Exception:
                pass

    # Tool catalog (compact). Must match the surface the subagent's MCP client
    # actually advertises: under the counter front door the raw catalog names
    # are NOT callable, and briefing them trains the model to distrust jcm.
    if _tool_surface() == "counter":
        parts.append("\n### Available jCodemunch Tools (Counter front door)")
        parts.append(
            "This server exposes three entry points: `menu` (search the tool "
            "catalog for the right action), `order` (execute a catalog action "
            "by name), and `route` (classify a task to a recommended action). "
            "Start with `menu` or `route`, then `order` the action it names."
        )
    else:
        parts.append("\n### Available jCodemunch Tools")
        parts.append(
            "search_symbols, get_symbol_source, get_context_bundle, get_file_content, "
            "search_text, get_ranked_context, find_importers, find_references, "
            "check_references, get_dependency_graph, get_class_hierarchy, "
            "get_call_hierarchy, get_blast_radius, get_impact_preview, "
            "get_changed_symbols, find_dead_code, get_untested_symbols, "
            "get_symbol_complexity, get_churn_rate, get_hotspots, get_repo_health, "
            "get_coupling_metrics, get_extraction_candidates, check_rename_safe, "
            "plan_refactoring, "
            "get_file_outline, get_file_tree, get_repo_outline, index_folder, "
            "index_repo, embed_repo, plan_turn, suggest_queries, "
            "get_session_context, get_session_snapshot, get_session_stats, "
            "get_cross_repo_map, get_layer_violations, audit_agent_config, "
            "get_dead_code_v2, search_columns"
        )
        parts.append("\nUse `plan_turn` to get recommended approach for your task.")

    return _emit_additional_context("SubagentStart", "\n".join(parts))


def _tool_surface() -> str:
    """Effective ``tool_surface`` as the MCP server would resolve it (env wins,
    then config). Best-effort: any failure reads as ``full``.

    Duplicates the resolution order of ``server._effective_surface()`` on
    purpose: importing the server module here would put its full import cost
    in front of every subagent spawn, and this hook only needs the one key.

    Reads via ``config.get`` — NOT ``load_config()``, which returns None (its
    job is populating the module global) and, worse, defaults to
    ``create_missing=True``: a config READ from a hook process must never
    WRITE a config file into the user's storage dir (Maintenance Practice 8).
    ``config.get``'s lazy load passes ``create_missing=False`` for exactly
    that reason, and its env-var fallback layer already honors
    ``JCODEMUNCH_TOOL_SURFACE``.
    """
    # The env pre-check is load-bearing for PRECEDENCE, not just import cost:
    # config.get's env layer is a FALLBACK (a config-file value would win),
    # while the server resolves env-wins. Checking env first keeps the two in
    # agreement — and skips the config import when the env var decides.
    val = (os.environ.get("JCODEMUNCH_TOOL_SURFACE") or "").strip().lower()
    if val:
        return val
    try:
        from ...config import get as _config_get
        return str(_config_get("tool_surface") or "full").strip().lower()
    except Exception:
        logger.debug("tool_surface config read failed", exc_info=True)
        return "full"
