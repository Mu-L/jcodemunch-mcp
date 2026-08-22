"""Structural-landmark enrichment for the session snapshot (Gap 4A)."""

import logging

from ._common import _iter_loaded_repos

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
        from ...tools.pagerank import compute_pagerank
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

    # Load all indexed repos and find which ones contain session files
    store = IndexStore()
    repo_indices: dict[str, object] = {}
    try:
        repos = store.list_repos()
    except Exception:
        return ""

    for repo_id, idx in _iter_loaded_repos(store, repos):
        if repo_id in repo_indices:
            continue
        if idx.source_files:
            repo_indices[repo_id] = idx

    if not repo_indices:
        return ""

    parts: list[str] = []

    for repo_id, index in repo_indices.items():
        if not index.imports or not index.source_files:
            continue

        # Compute PageRank
        try:
            pr_scores, _ = compute_pagerank(
                index.imports, index.source_files,
                alias_map=getattr(index, "alias_map", None),
                psr4_map=getattr(index, "psr4_map", None),
            )
        except Exception:
            logger.debug("PageRank failed for %s", repo_id, exc_info=True)
            continue

        if not pr_scores:
            continue

        # Rank files by PageRank, then pick top symbols from those files
        top_files = sorted(pr_scores.items(), key=lambda x: x[1], reverse=True)[:top_n * 2]
        top_file_set = {f for f, _ in top_files}

        # Collect symbols from top-ranked files
        symbol_pr: list[tuple[dict, float]] = []
        for sym in index.symbols:
            f = sym.get("file", "")
            if f in top_file_set:
                symbol_pr.append((sym, pr_scores.get(f, 0.0)))

        # Sort by PageRank score, take top_n
        symbol_pr.sort(key=lambda x: x[1], reverse=True)
        landmarks = symbol_pr[:top_n]

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
        session_edited = {ef for ef in edited_files}
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
