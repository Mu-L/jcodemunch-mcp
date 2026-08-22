"""Shared plumbing for the Claude Code hook handlers.

Helpers used by more than one hook family; each family lives in its own
module (steering / reindex / snapshot / landmarks / taskcomplete /
briefing) and the package ``__init__`` re-exports the ``run_*`` entry
points, so ``server.py`` dispatch is unchanged.
"""

import json
import os
import sys


def _note_transcript_root(data) -> None:
    """Record the profile this session's transcripts live under (jcm#421).

    Every hook payload carries ``transcript_path``, and the projects root is its
    grandparent, so the hooks are how ``receipt`` learns about profiles started
    with a custom ``CLAUDE_CONFIG_DIR``. Silent by construction: it writes one
    small file under the index store and touches neither stdout (which Claude
    Code parses as the hook's reply) nor the hook's exit code.
    """
    try:
        if not isinstance(data, dict):
            return
        from ...storage.transcript_roots import register_from_transcript_path
        register_from_transcript_path(data.get("transcript_path"))
    except Exception:
        pass


def _read_hook_payload() -> "dict | None":
    """Parse the hook's stdin JSON; None for unparseable or non-dict payloads.

    A hook must never crash on hostile input; callers treat None as allow.
    """
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _emit_additional_context(event_name: str, text: str) -> int:
    """Emit model-facing additionalContext for an exit-0 hook.

    Not available on every event — PreCompact and TaskCompleted have no such
    channel.

    Past 10,000 characters the text is NOT truncated: Claude Code writes it to a
    file and hands the model a path plus a short preview. Nothing is lost, but the
    model pays a re-read to see it, so keep emissions well under that. Measured on
    this repo's index: the SubagentStart briefing is ~866 characters, and snapshot
    plus landmarks ~91.
    """
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": text,
        }
    }))
    return 0


def _norm_path(path: str) -> str:
    """Normalise a path for comparison against indexed source roots.

    ``realpath`` is load-bearing: ``index_folder`` records ``source_root`` via
    ``Path.resolve()`` (symlinks resolved), so an ``abspath``-only comparison
    never matches a session addressed through a symlink component (macOS
    ``/tmp`` -> ``/private/tmp``, symlinked homes/worktrees) and the whole
    steering layer goes silently inert.
    """
    return os.path.normcase(os.path.realpath(path))


def _path_overlaps(root: str, source_roots: list[str]) -> bool:
    """True when *root* is equal to, inside, or an ancestor of any indexed root.

    The ancestor case matters too: grepping a parent directory that *contains*
    an indexed repo is still a search jcm can serve.
    """
    for sr in source_roots:
        if root == sr or root.startswith(sr + os.sep) or sr.startswith(root + os.sep):
            return True
    return False


def _repo_owner_name(entry: dict) -> "tuple[str, str]":
    """(owner, name) from an ``IndexStore.list_repos()`` entry, or ("", "").

    The real store keys entries ``{"repo": "owner/name", ...}`` — there is no
    top-level ``owner``/``name``. Three hook loops read those absent keys for
    months and silently skipped every repo (briefing, landmarks, task
    diagnostics all dead); the only producer of the owner/name shape was a
    wrong test mock, so no fallback for it — ``repo`` is the one authority.
    """
    repo = entry.get("repo") or ""
    if isinstance(repo, str) and "/" in repo:
        owner, name = repo.split("/", 1)
        if owner and name:
            return owner, name
    return "", ""


def _iter_loaded_repos(store, repos):
    """Yield ``(repo_id, idx)`` for each loadable entry of ``list_repos()``.

    Membership and scoping guards stay with each caller — the landmark,
    taskcomplete and subagent loops genuinely differ there.
    """
    for entry in repos:
        owner, name = _repo_owner_name(entry)
        if not owner or not name:
            continue
        try:
            idx = store.load_index(owner, name)
        except Exception:
            continue
        if not idx:
            continue
        yield f"{owner}/{name}", idx
