"""PreCompact / SessionStart: session-snapshot restore (#334 bridge)."""

from ._common import (
    _emit_additional_context,
    _note_transcript_root,
    _read_hook_payload,
)
from .landmarks import _build_landmark_section


def _build_session_snapshot() -> str:
    """Render the session snapshot; "" when there is nothing worth injecting.

    Consumed by ``run_sessionstart``, which injects it into the model after a
    compact/resume/fork (``run_precompact`` no longer emits it — PreCompact has
    no exit-0 output channel).

    The hook runs as a SEPARATE process from the MCP server, so the in-process
    SessionJournal is empty (#334). Read the live journal the server persists
    incrementally first; fall back to the in-process journal (covers embedded
    invocations). Never renders a zero-state snapshot as if it were data.
    """
    snapshot_text = ""
    live_context = None
    try:
        from ...tools.get_session_snapshot import snapshot_from_live
        live = snapshot_from_live()
        if live:
            snapshot_text = live.get("snapshot", "")
            live_context = live.get("_context")
    except Exception:
        snapshot_text = ""

    if not snapshot_text:
        try:
            from ...tools.get_session_snapshot import get_session_snapshot
            snap = get_session_snapshot()
            structured = snap.get("structured", {})
            if structured.get("total_files_explored") or structured.get("total_searches"):
                snapshot_text = snap.get("snapshot", "")
        except Exception:
            snapshot_text = ""

    if not snapshot_text:
        return ""  # No journal → nothing worth injecting.

    # Enrich with structural landmarks (PageRank top-N) and recently-changed
    # symbols. Seed from the live journal context when we have one so landmarks
    # work out-of-process too; skip entirely on the no-journal fallback.
    try:
        landmarks = _build_landmark_section(context=live_context)
        if landmarks:
            snapshot_text += landmarks
    except Exception:
        pass  # Landmark enrichment must not block compaction

    return snapshot_text


def run_precompact() -> int:
    """PreCompact hook: register the transcript root before compaction.

    PreCompact has NO exit-0 output channel at all: it has no
    ``additionalContext``, and Claude Code documents that it discards a
    PreCompact hook's ``systemMessage`` (this hook used to emit the session
    snapshot there — into a field nobody ever received). The snapshot reaches
    the model via ``run_sessionstart`` on ``source=compact`` instead, which is
    the half that matters.

    Returns exit code (always 0 — errors are swallowed to avoid blocking).
    """
    _note_transcript_root(_read_hook_payload())  # no-ops on None by contract
    return 0


def run_sessionstart() -> int:
    """SessionStart hook: restore the session snapshot to the model.

    Injects on compact/resume/fork, where the persisted journal still describes
    this session. Stays silent on startup/clear — an unrelated session's journal
    would present stale files as current focus.

    Returns exit code (always 0 — errors are swallowed to avoid blocking).
    """
    data = _read_hook_payload()
    if data is None:
        return 0

    # Earliest hook to fire on a resumed session, so this is the earliest point
    # a custom-profile transcript root can be learned (#421) — every other hook
    # waits for a first Read or Edit. Registered BEFORE the source gate, because
    # the root is a property of the session, not of whether we inject anything.
    _note_transcript_root(data)

    source = data.get("source")
    source = source.strip().lower() if isinstance(source, str) else ""
    if source not in {"compact", "resume", "fork"}:
        return 0  # Fresh session — no prior state worth restoring.

    try:
        snapshot_text = _build_session_snapshot()
    except Exception:
        return 0  # Never block session startup.

    if not snapshot_text.strip():
        return 0  # Nothing worth injecting.

    label = {
        "compact": "restored after compaction",
        "resume": "restored on resume",
        "fork": "carried into this fork",
    }[source]
    return _emit_additional_context(
        "SessionStart",
        f"## jCodemunch session state ({label})\n\n{snapshot_text}",
    )
