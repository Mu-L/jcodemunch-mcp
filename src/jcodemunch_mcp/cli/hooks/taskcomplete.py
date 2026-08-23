"""TaskCompleted: post-task diagnostics (dead code / untested / dangling)."""

import itertools
import json
import logging
import sys

from ._common import (
    _iter_loaded_repos,
    _note_transcript_root,
    _read_hook_payload,
)

logger = logging.getLogger(__name__)


def run_taskcomplete() -> int:
    """TaskCompleted hook: surface dead code, untested symbols, and dangling refs.

    Reads hook JSON from stdin. Inspects files modified during the session
    and runs three diagnostic checks scoped to those files:
      1. find_dead_code — newly-orphaned symbols
      2. get_untested_symbols — new code with no test reachability
      3. check_references — dangling references to deleted/renamed symbols

    Returns exit code (always 0 — errors are swallowed to avoid blocking).
    """
    data = _read_hook_payload()
    if data is None:
        return 0
    _note_transcript_root(data)

    # The hook runs in a SEPARATE process from the MCP server, so the
    # in-process journal is empty here (#334 — the same defect run_precompact
    # was fixed for; this handler shipped without the bridge and its
    # diagnostics never fired in any real deployment). Read the persisted live
    # journal first; fall back to the in-process journal for embedded
    # invocations.
    context: dict = {}
    try:
        from ...tools.session_state import load_live_journal
        # Freshness bound: a stale _session_live.json from a dead prior
        # session must not present days-old edits as this task's work.
        live = load_live_journal(max_age_minutes=240)
        if live and (edits := live.get("files_edited")):
            context = {"files_edited": edits}
    except Exception:
        logger.debug("live journal read failed", exc_info=True)
    if not context:
        try:
            from ...tools.session_journal import get_journal
            journal = get_journal()
            context = journal.get_context(max_files=50, max_queries=0, max_edits=50)
        except Exception:
            logger.debug("in-process journal read failed", exc_info=True)
            return 0

    edited_files = [
        e["file"] for e in context.get("files_edited", [])
        if isinstance(e, dict) and e.get("file")  # disk JSON — shape not trusted
    ]
    if not edited_files:
        return 0  # Nothing modified — nothing to diagnose

    # Find which repos contain these files
    try:
        from ...storage import IndexStore
        store = IndexStore()
        repos = store.list_repos()
    except Exception:
        return 0

    diagnostics: list[dict] = []

    for repo_id, idx in _iter_loaded_repos(store, repos, wanted_files=edited_files):
        if not idx.source_files:
            continue

        # Scope: only files in this repo that were edited
        repo_files = set(idx.source_files)
        session_files = [f for f in edited_files if f in repo_files]
        session_file_set = set(session_files)
        if not session_files:
            continue

        diag: dict = {"repo": repo_id, "files_checked": len(session_files)}

        # 1. Dead code scoped to edited files
        try:
            from ...tools.find_dead_code import find_dead_code
            dead_result = find_dead_code(repo_id, granularity="symbol")
            if dead_result and not dead_result.get("error"):
                dead_in_session = [
                    s for s in dead_result.get("dead_symbols", [])
                    if s.get("file") in session_file_set
                ]
                if dead_in_session:
                    diag["dead_symbols"] = dead_in_session[:10]
        except Exception:
            pass

        # 2. Untested symbols in edited files
        try:
            from ...tools.get_untested_symbols import get_untested_symbols
            # Per-file on purpose: a corpus-wide call must CAP its result, and
            # a cap applied before the session filter silently drops this
            # session's symbols in exactly the worst-tested repos. Paying the
            # reachability build per file is the price of a lossless report.
            for sf in session_files[:5]:
                untested = get_untested_symbols(
                    repo_id, file_pattern=sf.replace("\\", "/"), max_results=5
                )
                if untested and not untested.get("error"):
                    syms = untested.get("untested_symbols", [])
                    if syms:
                        diag.setdefault("untested_symbols", []).extend(syms[:5])
        except Exception:
            pass

        # 3. Dangling references — check symbols that were in edited files
        try:
            from ...tools.check_references import check_references
            edited_syms = list(itertools.islice(
                (sym["name"] for sym in idx.symbols
                 if sym.get("file") in session_file_set),
                10,
            ))
            if edited_syms:
                # Batch mode: one resolve/load for all symbols instead of
                # one per symbol (the #406 sweep's form; see 7d0e996).
                ref_result = check_references(
                    repo_id, identifiers=edited_syms, max_content_results=3
                )
                if ref_result and not ref_result.get("error"):
                    for ref in ref_result.get("results", []):
                        if not ref.get("is_referenced"):
                            diag.setdefault("unreferenced_symbols", []).append(
                                ref.get("identifier")
                            )
        except Exception:
            pass

        if len(diag) > 2:  # More than just repo + files_checked
            diagnostics.append(diag)

    if not diagnostics:
        return 0

    # Build compact message for the agent
    parts = ["## Post-Task Diagnostics (jCodemunch)"]
    for diag in diagnostics:
        parts.append(f"\n### {diag['repo']} ({diag['files_checked']} files checked)")
        if "dead_symbols" in diag:
            parts.append(f"**Possibly orphaned:** {len(diag['dead_symbols'])} symbol(s)")
            for s in diag["dead_symbols"][:5]:
                parts.append(f"  - `{s.get('name', '?')}` ({s.get('file', '?')}:{s.get('line', 0)})")
        if "untested_symbols" in diag:
            parts.append(f"**No test coverage:** {len(diag['untested_symbols'])} symbol(s)")
            for s in diag["untested_symbols"][:5]:
                parts.append(f"  - `{s.get('name', '?')}` ({s.get('file', '?')})")
        if "unreferenced_symbols" in diag:
            parts.append(f"**Unreferenced:** {', '.join(f'`{s}`' for s in diag['unreferenced_symbols'][:5])}")

    # TaskCompleted lacks additionalContext; its only model-facing route is exit 2,
    # which also refuses task completion. These findings are advisory, so keep them
    # user-facing rather than blocking on them.
    result = {"systemMessage": "\n".join(parts)}
    json.dump(result, sys.stdout)
    return 0
