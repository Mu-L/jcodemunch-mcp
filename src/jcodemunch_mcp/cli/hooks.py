"""Claude Code hook handlers for jCodemunch enforcement.

PreToolUse  — steering toward jCodemunch before a native file tool runs, all
              gated on the target being inside an INDEXED repo (jcm can serve
              it there; elsewhere the hints would just error):
              Read on a large code file → get_file_outline / get_symbol_source;
              Grep → search_text / search_symbols / find_references;
              Glob → get_file_tree / search_symbols / get_repo_outline;
              Bash command lines that OPEN with a search command
              (grep/rg/find/...) → the same jcm routes.
PostToolUse — auto-reindex after Edit/Write to keep the index fresh.

Both read JSON from stdin and write JSON to stdout per the Claude Code
hooks specification.

Output channels — the one rule this module turns on: a hook that exits 0 reaches
the model ONLY via ``hookSpecificOutput.additionalContext``. Both stderr and
top-level ``systemMessage`` surface to the user instead (on events that honor
them — PreCompact discards ``systemMessage`` outright), so steering text written
to either is silently inert. Exit 2 does feed stderr to the model, but it also
blocks the call, which is not what an advisory nudge wants.
"""

import itertools
import json
import logging
import os
import re
import subprocess
import sys

logger = logging.getLogger(__name__)


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
        from ..storage.transcript_roots import register_from_transcript_path
        register_from_transcript_path(data.get("transcript_path"))
    except Exception:
        pass


# Extensions that benefit from jCodemunch structural navigation.
# Kept intentionally broad — mirrors languages.py LANGUAGE_REGISTRY.
_CODE_EXTENSIONS: set[str] = {
    ".py", ".pyi",
    ".js", ".jsx", ".mjs", ".cjs",
    ".ts", ".tsx", ".mts", ".cts",
    ".go",
    ".rs",
    ".java",
    ".php",
    ".rb",
    ".cs", ".cshtml", ".razor",
    ".cpp", ".c", ".h", ".hpp", ".cc", ".cxx", ".ino", ".pde",
    ".vhd", ".vhdl", ".vho", ".vhs",
    ".v", ".vh", ".sv", ".svh",
    ".swift",
    ".kt", ".kts",
    ".scala",
    ".dart",
    ".lua", ".luau",
    ".ex", ".exs",
    ".erl", ".hrl",
    ".vue", ".astro", ".svelte",
    ".sql",
    ".gd",       # GDScript
    ".al",       # AL (Business Central)
    ".gleam",
    ".nix",
    ".hcl", ".tf",
    ".proto",
    ".graphql", ".gql",
    ".verse",
    ".jl",       # Julia
    ".r", ".R",
    ".hs",       # Haskell
    ".f90", ".f95", ".f03", ".f08",  # Fortran
    ".groovy",
    ".pl", ".pm",  # Perl
    ".bash", ".sh", ".zsh",
}

# Minimum file size to trigger jCodemunch suggestion.
# Override with JCODEMUNCH_HOOK_MIN_SIZE env var.
# Garbage parses to the DEFAULT, never to a crash: this module is imported by
# every hook subcommand, so a ValueError here would kill all hooks at once.
try:
    _MIN_SIZE_BYTES = int(os.environ.get("JCODEMUNCH_HOOK_MIN_SIZE", "4096"))
except ValueError:
    _MIN_SIZE_BYTES = 4096


def _norm_path(path: str) -> str:
    """Normalise a path for comparison against indexed source roots.

    ``realpath`` is load-bearing: ``index_folder`` records ``source_root`` via
    ``Path.resolve()`` (symlinks resolved), so an ``abspath``-only comparison
    never matches a session addressed through a symlink component (macOS
    ``/tmp`` -> ``/private/tmp``, symlinked homes/worktrees) and the whole
    steering layer goes silently inert.
    """
    return os.path.normcase(os.path.realpath(path))


def _enforce_mode() -> str:
    """jCodemunch enforcement tier for native file tools (``JCODEMUNCH_ENFORCE``).

    * ``"advisory"`` (default): nudge via ``additionalContext`` but **allow** —
      the v1.108.47 behavior. A hard deny here would break Read-before-Edit.
    * ``"strict"``: **deny** a native Read/Grep that an indexed-repo jcm route
      can already serve. Targeted reads (``offset``/``limit``), tiny files, and
      paths outside every indexed repo still pass, so the escape hatch is always
      one step away and jcm is never blamed for a search it can't serve.
    * ``"off"``: no nudge, no deny — fully silent.

    Unknown values fall back to ``"advisory"`` so a typo never hard-blocks tools.
    Opt in to strict with ``jcodemunch-mcp init --strict`` (persists the env var
    into ~/.claude/settings.json) or by exporting it yourself.
    """
    val = os.environ.get("JCODEMUNCH_ENFORCE", "advisory").strip().lower()
    if val in {"strict", "deny", "block", "hard"}:
        return "strict"
    if val in {"off", "0", "false", "no", "none", "silent"}:
        return "off"
    return "advisory"


def _emit_pretooluse_deny(reason: str) -> int:
    """Emit a Claude Code PreToolUse ``deny`` decision (stdout JSON) and exit 0.

    The deny lives in the JSON decision channel, and exit code stays 0 so the
    harness reads the decision, not a crash.
    """
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    return 0


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


def _read_hook_payload() -> "dict | None":
    """Parse the hook's stdin JSON; None for unparseable or non-dict payloads.

    A hook must never crash on hostile input; callers treat None as allow.
    """
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def run_pretooluse() -> int:
    """PreToolUse hook: steer Claude toward jCodemunch before native file tools.

    Dispatch per tool (Grep/Glob/Bash-search/Read) is described in the module
    docstring. Strength is set by ``_enforce_mode()`` (``JCODEMUNCH_ENFORCE``): the default
    ``advisory`` tier nudges the model but allows (so Read-before-Edit and the
    Grep fallback keep working); ``strict`` denies the same calls but only when
    an indexed-repo jcm route can serve them — targeted reads (``offset`` /
    ``limit``), tiny files, non-code files, and paths outside every indexed repo
    always pass; ``off`` is fully silent.

    Returns exit code (always 0 — errors are swallowed to avoid blocking).
    """
    data = _read_hook_payload()
    if data is None:
        return 0  # Unparseable or hostile payload shape → allow

    _note_transcript_root(data)

    mode = _enforce_mode()
    if mode == "off":
        return 0  # No nudge, no deny.

    tool_input = data.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0

    tool_name = data.get("tool_name", "")

    # Search interception: Grep/Glob do a job a jcm route already covers,
    # entirely off the savings meter; Bash (grep/rg/find at the start of the
    # command line) is the dominant unhooked route for the same job — and
    # under strict mode, the escape hatch a denied Grep funnels the model
    # into. Defensive: the hook must never crash the agent's search, so
    # swallow anything unexpected.
    if tool_name in ("Grep", "Glob", "Bash"):
        try:
            cwd = data.get("cwd", "")
            if tool_name == "Bash":
                return _handle_bash(tool_input, cwd, mode)
            deny = mode == "strict"
            if not deny and not _search_nudge_enabled():
                return 0  # Guaranteed silent — skip the store load below.
            if not _path_overlaps(
                _grep_search_root(tool_input, cwd), _indexed_source_roots()
            ):
                return 0  # Nothing indexed / outside every repo → allow.
            pattern = (tool_input.get("pattern") or "").strip()
            what = f"this {tool_name}" + (f" for `{pattern}`" if pattern else "")
            return _emit_search_steering(tool_name, what, deny=deny)
        except Exception:
            logger.debug("%s interception failed", tool_name, exc_info=True)
            return 0

    # --- Read interception ---
    file_path = tool_input.get("file_path", "")
    if not isinstance(file_path, str) or not file_path:
        return 0

    # Check extension
    _, ext = os.path.splitext(file_path)
    if ext.lower() not in _CODE_EXTENSIONS:
        return 0  # Not a code file → allow

    # Check size
    try:
        size = os.path.getsize(file_path)
    except (OSError, ValueError):
        return 0  # Can't stat (missing, or hostile path e.g. NUL byte) → allow

    if size < _MIN_SIZE_BYTES:
        return 0  # Small file → allow

    # Targeted reads (offset/limit set) are likely pre-edit — allow silently.
    if tool_input.get("offset") is not None or tool_input.get("limit") is not None:
        return 0

    # Both tiers only speak when the file lives inside an indexed repo — jcm
    # can actually serve it there. Outside every indexed repo the recommended
    # tools would just error, teaching the model that jcm hints are unreliable.
    try:
        roots = _indexed_source_roots()
        if not roots or not _path_overlaps(_norm_path(file_path), roots):
            return 0
    except Exception:
        logger.debug("indexed-roots gate failed", exc_info=True)
        return 0  # Never block on a store hiccup.

    if mode == "strict":
        # Strict: deny the full-file read. Targeted reads (offset/limit) have
        # already passed above, so the pre-Edit escape hatch is always open.
        return _emit_pretooluse_deny(
            f"jCodemunch strict mode: this {size:,}-byte code file is in an "
            "indexed repo. Use get_file_outline + get_symbol_source instead "
            "of a full Read. For an exact-line pre-Edit read, pass "
            "offset/limit and it will pass. (JCODEMUNCH_ENFORCE=advisory "
            "for warn-only, =off to disable.)"
        )

    # Advisory: full-file exploratory read on a large code file — warn but allow.
    # Hard deny breaks the Edit workflow (Claude Code requires Read before Edit).
    return _emit_additional_context(
        "PreToolUse",
        f"jCodemunch hint: this is a {size:,}-byte code file. "
        "Prefer get_file_outline + get_symbol_source for exploration. "
        "Use Read only when you need exact line numbers for Edit.",
    )


# ---------------------------------------------------------------------------
# Grep/Glob/Bash-search → jCodemunch nudge (PreToolUse, matcher
# "Read|Grep|Glob|Bash")
# ---------------------------------------------------------------------------

def _search_nudge_enabled() -> bool:
    """Whether the search→jcm nudge is active. Set JCODEMUNCH_HOOK_GREP_NUDGE=0
    (or false/no/off) to silence it."""
    return os.environ.get("JCODEMUNCH_HOOK_GREP_NUDGE", "1").strip().lower() not in {
        "0", "false", "no", "off",
    }


def _indexed_source_roots() -> list[str]:
    """Normalised absolute source roots of every locally-indexed repo.

    Loaded fresh per call (the hook is a short-lived process). Best-effort:
    any failure yields ``[]`` so the hook silently allows the search rather
    than ever blocking it on a store hiccup.
    """
    try:
        from ..storage import IndexStore
        roots: list[str] = []
        for entry in IndexStore().list_repos():
            sr = (entry.get("source_root") or "").strip()
            if sr:
                roots.append(_norm_path(sr))
        return roots
    except Exception:
        return []


def _grep_search_root(tool_input: dict, cwd: str) -> str:
    """Resolve the directory a Grep/Glob call will actually scan (normalised)."""
    path = (tool_input.get("path") or "").strip()
    base = cwd or os.getcwd()
    if not path:
        root = base
    elif os.path.isabs(path):
        root = path
    else:
        root = os.path.join(base, path)
    return _norm_path(root)


def _path_overlaps(root: str, source_roots: list[str]) -> bool:
    """True when *root* is equal to, inside, or an ancestor of any indexed root.

    The ancestor case matters too: grepping a parent directory that *contains*
    an indexed repo is still a search jcm can serve.
    """
    for sr in source_roots:
        if root == sr or root.startswith(sr + os.sep) or sr.startswith(root + os.sep):
            return True
    return False


# jcm alternative-route text per intercepted search tool.
_SEARCH_ROUTES = {
    "Grep": (
        "  - search_text     : same regex/substring scan, ranked + winnowed\n"
        "  - search_symbols  : when hunting a definition (function/class/const/type)\n"
        "  - find_references / find_importers : 'where is X used / who imports this'"
    ),
    "Glob": (
        "  - get_file_tree   : ranked, token-budgeted file listing\n"
        "  - search_symbols  : when the filename hunt is really a symbol hunt\n"
        "  - get_repo_outline: structure overview without a directory walk"
    ),
}
# Bash covers the same searches as Grep, plus find-style file discovery.
_SEARCH_ROUTES["Bash"] = (
    _SEARCH_ROUTES["Grep"]
    + "\n  - get_file_tree   : instead of `find` for file discovery"
)


def _emit_search_steering(tool_name: str, what: str, *, deny: bool) -> int:
    """Emit the nudge or deny for an already-gated search interception.

    Emit-only by design: each caller owns its own gate (nudge switch, store
    load, indexed-root overlap), because the Bash caller needs the loaded
    roots for its token scan and a gate here would either re-check what the
    caller proved or force a second store load.
    """
    routes = _SEARCH_ROUTES[tool_name]
    if deny:
        return _emit_pretooluse_deny(
            f"jCodemunch strict mode: {what} targets an indexed repo. Use the jcm "
            f"routes instead:\n{routes}\n"
            "(JCODEMUNCH_ENFORCE=advisory for warn-only, =off to disable.)"
        )
    return _emit_additional_context(
        "PreToolUse",
        f"jCodemunch: {what} targets an indexed repo. Exhaust the jcm "
        "routes first, since they're tighter and credited (a raw scan is neither):\n"
        f"{routes}\n"
        f"Fall back to {tool_name} only once those come up empty.",
    )


# Search commands intercepted at the START of a Bash command line (a grep
# after a pipe filters the previous command's output, which jcm cannot serve),
# mapped to whether strict mode may DENY them. Only pure searches are
# deniable: `find ... -delete` / `-exec` open with the same word, and a deny
# steering to search routes cannot do the deletion.
_BASH_SEARCH_COMMANDS = {
    "grep": True, "egrep": True, "fgrep": True,
    "rg": True, "ag": True, "ack": True,
    "find": False,
}
_BASH_SEARCH_RE = re.compile(
    r"^\s*(?:command\s+)?(" + "|".join(_BASH_SEARCH_COMMANDS) + r")\b"
)

# Absolute or ~-anchored path tokens inside a command line.
_BASH_PATH_TOKEN_RE = re.compile(r"(?:^|[\s=])((?:/|~/)[^\s;|&)>\"']+)")


def _bash_targets_outside_roots(command: str, roots: "list[str]") -> bool:
    """True when the command names an absolute/home path outside every indexed
    root — a search jcm cannot serve, so a strict deny would block real work
    while falsely claiming the search targets an indexed repo."""
    if re.search(r"(?:^|[\s='\"])\.\./", command):
        return True  # ../ escapes cwd; where it lands is not worth resolving.
    for tok in _BASH_PATH_TOKEN_RE.findall(command):
        if not _path_overlaps(_norm_path(os.path.expanduser(tok)), roots):
            return True
    return False


def _handle_bash(tool_input: dict, cwd: str, mode: str) -> int:
    """Bash PreToolUse branch: intercept command lines that OPEN with a local
    search command (grep/rg/find/...) scanning an indexed repo — the dominant
    route by which the model does exactly the job the jcm routes cover, and
    the escape hatch a strict-denied Grep would otherwise funnel it into.

    Any other Bash command (builds, git, pipelines that merely filter output
    through grep) passes silently. Strict mode denies only the pure-search
    commands, and only when the command names no path outside every indexed
    root; everything else it can only nudge, because the hook cannot judge an
    arbitrary command line safely enough to block it.
    """
    command = tool_input.get("command", "")
    if not isinstance(command, str):
        return 0
    m = _BASH_SEARCH_RE.match(command)
    if not m:
        return 0
    cmd_word = m.group(1)
    deny = mode == "strict" and _BASH_SEARCH_COMMANDS[cmd_word]
    if deny and re.search(r"[|&;]", command):
        deny = False  # Pipeline/compound: the non-search half is real work.
    if not deny and not _search_nudge_enabled():
        return 0  # Guaranteed silent — skip the store load below.
    roots = _indexed_source_roots()
    # Overlap is judged on cwd only — parsing arbitrary shell for target
    # paths is not worth it; relative-path searches from the repo root are
    # the dominant pattern.
    root = _norm_path(cwd or os.getcwd())
    if not _path_overlaps(root, roots):
        return 0  # Outside every indexed repo — allow silently.
    if _bash_targets_outside_roots(command, roots):
        return 0  # Search names a path jcm cannot serve — stay silent.
    return _emit_search_steering("Bash", f"this `{cmd_word}` command", deny=deny)


def _self_invocation() -> list[str]:
    """Argv prefix that re-invokes THIS jcodemunch-mcp install.

    The hook process inherits Claude Code's minimal hook-shell PATH — the very
    reason ``init``'s ``_hook_invocation`` writes an absolute path into
    settings.json — so a bare-name child spawn dies silently on exactly the
    installs (pipx, pip --user, framework Python) that needed the absolute
    path. Prefer the path this process was launched with; fall back to
    ``python -m jcodemunch_mcp`` which needs no PATH lookup at all.
    """
    argv0 = sys.argv[0] or ""
    base = os.path.basename(argv0).lower()
    # isabs is load-bearing: a RELATIVE argv0 would be re-resolved against the
    # hook's cwd — the checked-out (untrusted) repo — where a file named
    # jcodemunch-mcp must never become the thing we execute. init writes
    # absolute paths, so absolute is the only legitimate shape.
    if base.startswith("jcodemunch-mcp") and os.path.isabs(argv0) and os.path.exists(argv0):
        return [argv0]
    return [sys.executable, "-m", "jcodemunch_mcp"]


def _spawn_index_file(file_path: str) -> None:
    """Fire-and-forget `index-file` spawn shared by both PostToolUse handlers.

    One owner for the spawn kwargs, the Windows console flag, and the except
    tuple (ValueError covers hostile NUL-byte paths) — a hardening applied to
    one handler must not miss the other.
    """
    try:
        kwargs: dict = dict(
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # On Windows, CREATE_NO_WINDOW prevents a console flash
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        subprocess.Popen(
            _self_invocation() + ["index-file", file_path],
            **kwargs,
        )
    except (OSError, ValueError):
        pass  # executable unavailable / hostile path → skip silently


def run_posttooluse() -> int:
    """PostToolUse hook: auto-index files after Edit/Write.

    Reads hook JSON from stdin, extracts the file path, and spawns
    ``jcodemunch-mcp index-file <path>`` as a fire-and-forget background
    process to keep the index fresh.

    Non-code files are skipped.  Errors are swallowed silently.

    Returns exit code (always 0).
    """
    data = _read_hook_payload()
    if data is None:
        return 0

    _note_transcript_root(data)

    tool_input = data.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    file_path = tool_input.get("file_path", "")
    if not isinstance(file_path, str) or not file_path:
        return 0

    # Only re-index code files
    _, ext = os.path.splitext(file_path)
    if ext.lower() not in _CODE_EXTENSIONS:
        return 0

    # Fire-and-forget: spawn index-file in background
    _spawn_index_file(file_path)
    return 0


def run_copilot_posttooluse() -> int:
    """GitHub Copilot ``postToolUse`` hook: auto-index files after Edit/Write.

    Adapter for the Copilot CLI / cloud-agent hook payload shape, which
    differs from Claude Code's:

    Copilot stdin JSON::

        {
            "timestamp": "...",
            "cwd": "...",
            "toolName": "edit" | "write" | "create_file" | ...,
            "toolArgs": "{\\"path\\": \\"/abs/path/to/file.py\\", ...}",
            "toolResult": "..."
        }

    ``toolArgs`` arrives as a JSON-encoded **string**, not a nested object.
    Tool names vary across Copilot tool implementations, so we extract a
    file path heuristically: any value at the top level of toolArgs whose
    key matches ``path``/``file_path``/``filename``/``filePath`` and points
    at an existing file. If the file is a code file under a directory that
    has been indexed, spawn ``jcodemunch-mcp index-file <path>`` as a
    fire-and-forget background process. Errors are swallowed silently —
    Copilot ignores postToolUse stdout/exit code, so a failing reindex
    must never disrupt the agent flow.
    """
    data = _read_hook_payload()
    if data is None:
        return 0

    tool_args_raw = data.get("toolArgs", "")
    if isinstance(tool_args_raw, str):
        try:
            tool_args = json.loads(tool_args_raw) if tool_args_raw else {}
        except (json.JSONDecodeError, ValueError):
            return 0
        if not isinstance(tool_args, dict):
            return 0  # toolArgs decoded to a non-dict (list/str/number)
    elif isinstance(tool_args_raw, dict):
        tool_args = tool_args_raw
    else:
        return 0

    file_path = ""
    for key in ("file_path", "filePath", "path", "filename"):
        v = tool_args.get(key)
        if isinstance(v, str) and v:
            file_path = v
            break
    if not file_path:
        return 0

    _, ext = os.path.splitext(file_path)
    if ext.lower() not in _CODE_EXTENSIONS:
        return 0

    _spawn_index_file(file_path)
    return 0


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
        from jcodemunch_mcp.tools.get_session_snapshot import snapshot_from_live
        live = snapshot_from_live()
        if live:
            snapshot_text = live.get("snapshot", "")
            live_context = live.get("_context")
    except Exception:
        snapshot_text = ""

    if not snapshot_text:
        try:
            from jcodemunch_mcp.tools.get_session_snapshot import get_session_snapshot
            snap = get_session_snapshot()
            structured = snap.get("structured", {})
            if structured.get("total_files_explored") or structured.get("total_searches"):
                snapshot_text = snap.get("snapshot", "")
        except Exception:
            snapshot_text = ""

    if not snapshot_text:
        # No journal → nothing worth injecting. (The old user-facing fallback
        # text died with PreCompact's discarded output channel.)
        return ""

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
    data = _read_hook_payload()
    if data is not None:
        _note_transcript_root(data)
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


# ---------------------------------------------------------------------------
# Landmark enrichment helpers (Gap 4A — Structural Landmarks)
# ---------------------------------------------------------------------------

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
        from ..storage import IndexStore
        from ..tools.pagerank import compute_pagerank
        from ..tools.session_journal import get_journal
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


# ---------------------------------------------------------------------------
# Post-task diagnostics hook (Gap 4B)
# ---------------------------------------------------------------------------

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
        from ..tools.session_state import load_live_journal
        # Freshness bound: a stale _session_live.json from a dead prior
        # session must not present days-old edits as this task's work.
        live = load_live_journal(max_age_minutes=240)
        if live and (edits := live.get("files_edited")):
            context = {"files_edited": edits}
    except Exception:
        logger.debug("live journal read failed", exc_info=True)
    if not context:
        try:
            from ..tools.session_journal import get_journal
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
        from ..storage import IndexStore
        store = IndexStore()
        repos = store.list_repos()
    except Exception:
        return 0

    diagnostics: list[dict] = []

    for repo_id, idx in _iter_loaded_repos(store, repos):
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
            from ..tools.find_dead_code import find_dead_code
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
            from ..tools.get_untested_symbols import get_untested_symbols
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
            from ..tools.check_references import check_references
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


# ---------------------------------------------------------------------------
# Subagent briefing hook (Gap 4C)
# ---------------------------------------------------------------------------

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
        from ..storage import IndexStore
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
                from ..tools.pagerank import compute_pagerank
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
        from ..config import get as _config_get
        return str(_config_get("tool_surface") or "full").strip().lower()
    except Exception:
        logger.debug("tool_surface config read failed", exc_info=True)
        return "full"
