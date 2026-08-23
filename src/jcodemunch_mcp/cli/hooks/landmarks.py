"""Structural-landmark enrichment for the session snapshot (Gap 4A)."""

import logging

from ._common import _iter_loaded_repos, _top_symbols_by_pagerank

logger = logging.getLogger(__name__)


def _build_landmark_section(top_n: int = 20, context: "dict | None" = None) -> str:
    """Build a compact landmarks + recently-changed section for PreCompact.

    Queries all indexed repos visible in the session journal's edited files,
    computes PageRank to find the most structurally central symbols, and
    cross-references the journal's edit log to surface recently-changed symbols.

    When ``context`` is supplied (e.g. the live journal read by the
    out-of-process hook, #334) it is used instead of the empty in-process
    journal. Returns a markdown string to append to the snapshot, or "" if no
    data.
    """
    try:
        from ...storage import IndexStore
        from ...tools.session_journal import get_journal
    except Exception:
        logger.debug("landmark imports failed", exc_info=True)
        return ""

    if context is None:
        journal = get_journal()
        context = journal.get_context(max_files=50, max_queries=0, max_edits=50)
    edited_files = [e["file"] for e in context.get("files_edited", [])]
    accessed_files = [f["file"] for f in context.get("files_accessed", [])]

    if not edited_files and not accessed_files:
        return ""

    store = IndexStore()
    try:
        repos = store.list_repos()
    except Exception:
        return ""

    session_edited = set(edited_files)
    parts: list[str] = []
    seen: set[str] = set()

    for repo_id, index in _iter_loaded_repos(
        store, repos, wanted_files=edited_files + accessed_files
    ):
        if repo_id in seen or not index.imports or not index.source_files:
            continue
        seen.add(repo_id)

        try:
            landmarks = _top_symbols_by_pagerank(
                index, n_files=top_n * 2, n_syms=top_n
            )
        except Exception:
            logger.debug("PageRank failed for %s", repo_id, exc_info=True)
            continue

        if landmarks:
            parts.append(f"\n\n### Structural Landmarks ({repo_id})")
            for sym, score in landmarks:
                name = sym.get("name", "?")
                kind = sym.get("kind", "")
                f = sym.get("file", "")
                line = sym.get("line", 0)
                summary = sym.get("summary", "")
                loc = f"{f}:{line}" if line else f
                desc = f" — {summary}" if summary else ""
                parts.append(f"- `{name}` ({kind}, {loc}){desc}")

        # Recently-changed symbols: cross-ref edited files with index
        changed_syms: list[dict] = []
        for sym in index.symbols:
            if sym.get("file", "") in session_edited:
                changed_syms.append(sym)

        if changed_syms:
            parts.append(f"\n### Recently Changed ({repo_id})")
            # Deduplicate and limit
            seen: set[str] = set()
            count = 0
            for sym in changed_syms:
                sid = sym.get("id", sym.get("name", ""))
                if sid in seen:
                    continue
                seen.add(sid)
                name = sym.get("name", "?")
                kind = sym.get("kind", "")
                f = sym.get("file", "")
                line = sym.get("line", 0)
                parts.append(f"- `{name}` ({kind}, {f}:{line})")
                count += 1
                if count >= 20:
                    break

    return "\n".join(parts) if parts else ""
