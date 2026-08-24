"""Registry of Claude Code transcript roots seen on this machine.

Origin (jcm#421). ``jcodemunch-mcp receipt`` scanned a hardcoded
``~/.claude/projects``. That is only where transcripts land for the *default*
profile: ``CLAUDE_CONFIG_DIR`` relocates the whole config tree, so any session
started under a second profile writes its transcripts somewhere ``receipt``
never looked. The reporter measured 12 of 348 calls counted (~3%) on a
three-profile box, and the single-valued ``--projects-root`` override could not
fix it because no one path contains two profiles.

Nothing here is configured by the user. We already run inside every session, so
we can learn the roots from the sessions themselves:

* the MCP server reads ``CLAUDE_CONFIG_DIR`` at startup (it is inherited by the
  server process the client spawns), and
* every Claude Code hook event carries ``transcript_path``, whose grandparent
  *is* the projects root, as a backstop for clients that set the env var only
  for the CLI.

Both paths append to one small JSON file under the index store, next to
``_savings.json``. Registration is retroactive: the moment a root is known,
``receipt`` counts all the history already inside it.

Contains transcript *directory* paths only — no transcript contents, no repo
paths, no queries. Written under the index store, disclosed in the README's
background-behavior section alongside the lock files and the savings meter.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_FILE_NAME = "_transcript_roots.json"
# Generous for real setups (the reporter's box has three) and a cap on a file
# that a pathological client could otherwise grow without bound.
_MAX_ROOTS = 64


def _index_root(storage_path: Optional[str] = None) -> Path:
    base = storage_path or os.environ.get("CODE_INDEX_PATH") or "~/.code-index"
    return Path(os.path.expanduser(base))


def registry_path(storage_path: Optional[str] = None) -> Path:
    return _index_root(storage_path) / _FILE_NAME


def default_root() -> Path:
    """The projects root of the default profile."""
    return Path.home() / ".claude" / "projects"


def env_root() -> Optional[Path]:
    """The projects root implied by ``CLAUDE_CONFIG_DIR``, when set."""
    raw = os.environ.get("CLAUDE_CONFIG_DIR")
    if not raw or not raw.strip():
        return None
    return Path(os.path.expanduser(raw.strip())) / "projects"


def _key(path: Path) -> str:
    """Identity for de-duplication (case-insensitive where the OS is)."""
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    text = str(resolved)
    return text.casefold() if os.name == "nt" else text


def _read(storage_path: Optional[str] = None) -> list[str]:
    try:
        data = json.loads(registry_path(storage_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    roots = data.get("roots") if isinstance(data, dict) else None
    if not isinstance(roots, list):
        return []
    return [r for r in roots if isinstance(r, str) and r]


def register(root: Path | str, storage_path: Optional[str] = None) -> bool:
    """Record *root* as a place transcripts live. Best effort, never raises.

    Returns True when the file was updated (new root), False otherwise —
    callers use this for tests, not for control flow.
    """
    try:
        path = Path(os.path.expanduser(str(root)))
        if not path.name:
            return False
        existing = _read(storage_path)
        if str(path) in existing:
            return False  # exact-string hit: the steady state, no resolving
        seen = {_key(Path(r)) for r in existing}
        if _key(path) in seen:
            return False
        existing.append(str(path))
        if len(existing) > _MAX_ROOTS:
            existing = existing[-_MAX_ROOTS:]
        target = registry_path(storage_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"roots": existing}), encoding="utf-8")
        return True
    except Exception:
        logger.debug("transcript root registry: register failed", exc_info=True)
        return False


def register_from_transcript_path(
    transcript_path: str | None, storage_path: Optional[str] = None
) -> bool:
    """Register the projects root implied by a hook event's ``transcript_path``.

    Layout is ``<root>/<project-slug>/<session-uuid>.jsonl``, so the root is the
    file's grandparent. Called from hook entrypoints, which must never write to
    stdout (Claude Code parses hook stdout as the hook's reply) — this function
    only touches the registry file and swallows every error.
    """
    if not transcript_path:
        return False
    try:
        parent = Path(transcript_path).parent.parent
    except (OSError, ValueError):
        return False
    if not parent.name:
        return False
    return register(parent, storage_path)


def register_session_root(storage_path: Optional[str] = None) -> bool:
    """Register this process's own profile root, read from the environment.

    The client spawns the MCP server as a child, so ``CLAUDE_CONFIG_DIR`` is
    inherited. Nothing to register when it is unset: that is the default
    profile, which ``known_roots`` always includes anyway.
    """
    root = env_root()
    if root is None:
        return False
    return register(root, storage_path)


def known_roots(storage_path: Optional[str] = None) -> list[Path]:
    """Every projects root to scan: default + ``CLAUDE_CONFIG_DIR`` + registry.

    De-duplicated, and roots that no longer exist are skipped so a deleted
    profile stops costing a walk. Order is stable: the default root, then this
    process's own profile, then registered ones in registration order.
    """
    candidates: list[Path] = [default_root()]
    env = env_root()
    if env is not None:
        candidates.append(env)
    candidates.extend(Path(r) for r in _read(storage_path))

    out: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = _key(path)
        if key in seen:
            continue
        seen.add(key)
        try:
            if not path.is_dir():
                continue
        except OSError:
            continue
        out.append(path)
    return out
