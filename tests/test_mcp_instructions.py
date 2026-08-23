"""The MCP `instructions` string sent in the initialize response.

Until v1.108.292 we sent none. That is invisible in a normal session and
expensive in a DEFERRED one: a host over its schema budget ships tool NAMES only
and withholds the JSONSchemas, so on the default surface an agent sees 91 bare
strings and none of the descriptions we budget and smell-test. `instructions`
travels on a separate track from the tool list and arrives whole either way.

The property under test is the one that rots: **what the string advertises is
what the server will dispatch.** A tool named here that we do not serve is worse
than saying nothing, because it sends the agent to a name that does not exist.
"""

from __future__ import annotations

import ast
import inspect
import re

from jcodemunch_mcp import server as server_mod
from jcodemunch_mcp.server import (
    _COUNTER_FRONT_DOOR,
    _MCP_INSTRUCTIONS_MAX_CHARS,
    _build_tools_list,
    _instruction_tool_names,
    _mcp_instructions,
    _tool_search_query,
)

_SURFACES = ("full", "counter")

# Tool names appear in the prose as bare identifiers. Anything matching this that
# is not a real tool is either a typo or a tool we dropped.
_NAME_RE = re.compile(r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b")

# Lowercase snake_case words in the prose that are deliberately not tool names.
_NOT_TOOL_NAMES = {"file_line", "one_at_a_time"}


def _served_names(surface: str) -> set:
    """Every tool name the server will dispatch on `surface`."""
    if surface == "counter":
        return set(_COUNTER_FRONT_DOOR)
    return {t.name for t in _build_tools_list()}


def test_both_surfaces_say_something_within_budget():
    for surface in _SURFACES:
        text = _mcp_instructions(surface)
        assert text.strip(), f"{surface}: empty instructions"
        assert len(text) <= _MCP_INSTRUCTIONS_MAX_CHARS, (
            f"{surface}: {len(text)} chars exceeds the "
            f"{_MCP_INSTRUCTIONS_MAX_CHARS} budget. Trim the prose; nothing "
            "proves a longer string survives un-truncated."
        )


def test_every_tool_named_is_a_tool_we_dispatch():
    """The whole point. Prose that names a tool we do not serve is a wrong turn."""
    for surface in _SURFACES:
        text = _mcp_instructions(surface)
        served = _served_names(surface)
        mentioned = {
            m for m in _NAME_RE.findall(text.replace("mcp__jcodemunch__", ""))
            if m not in _NOT_TOOL_NAMES
        }
        # Only judge names that LOOK like ours: a mention that is not served and
        # is not a plausible tool name at all would be a prose word, not a claim.
        unknown = {m for m in mentioned if m not in served}
        assert not unknown, (
            f"{surface}: instructions name {sorted(unknown)}, which the server "
            "does not dispatch on this surface. Either the tool moved or the "
            "prose is stale."
        )


def test_named_tools_are_the_ones_the_lookup_loads():
    for surface in _SURFACES:
        names = _instruction_tool_names(surface)
        assert names, f"{surface}: names no tools at all"
        query = _tool_search_query(surface)
        assert query.startswith("select:")
        loaded = query[len("select:"):].split(",")
        assert loaded == [f"mcp__jcodemunch__{n}" for n in names], (
            f"{surface}: the ToolSearch query and the bullet list disagree. An "
            "agent that follows the query would load a different set than the "
            "one the bullets tell it to use."
        )
        # The query must appear verbatim in the string it is built for.
        assert query in _mcp_instructions(surface)


def test_counter_surface_names_only_the_front_door():
    """On `counter` the other 91 tools are unreachable by name; naming one strands
    the agent on a tool `list_tools` never showed it."""
    assert set(_instruction_tool_names("counter")) == set(_COUNTER_FRONT_DOOR)


def test_unrecognized_surface_falls_back_to_full():
    """`_effective_surface` normalises garbage to "full"; so must this, or a typo
    in tool_surface serves the full catalog under front-door instructions."""
    assert _mcp_instructions("countr") == _mcp_instructions("full")


def test_initialization_options_carry_the_instructions():
    opts = server_mod._initialization_options()
    if "instructions" not in type(opts).model_fields:  # pragma: no cover - old SDK
        return
    assert opts.instructions == _mcp_instructions()


def test_every_server_run_passes_our_initialization_options():
    """Three transports, three call sites. A bare `create_initialization_options()`
    at any of them sends an empty `instructions` and nothing fails at runtime.

    ⚠ Asserts on the CALL, not on the helper: a test that only checked
    `_initialization_options()` would pass against a tree where stdio was
    rewired back and sse was not.
    """
    tree = ast.parse(inspect.getsource(server_mod))
    sites = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "run"):
            continue
        if not (isinstance(fn.value, ast.Name) and fn.value.id == "server"):
            continue
        sites.append(node)

    assert len(sites) == 3, (
        f"expected 3 server.run() transports, found {len(sites)}. A new one needs "
        "_initialization_options() too."
    )
    for site in sites:
        args = site.args
        assert len(args) >= 3, f"server.run() at line {site.lineno} takes no options"
        opts = args[2]
        assert isinstance(opts, ast.Call), f"line {site.lineno}: options is not a call"
        assert isinstance(opts.func, ast.Name) and opts.func.id == "_initialization_options", (
            f"server.run() at line {site.lineno} does not pass "
            "_initialization_options(); its handshake sends no instructions."
        )


def test_server_info_reports_our_version_not_the_sdks():
    """`Server(name)` with no `version=` makes the SDK report its OWN version in
    `serverInfo`. We did that until v1.108.292, so every host that displays a
    server version displayed the mcp package number.

    ⚠ Asserts INEQUALITY with the SDK version too: `version=__version__` and the
    default both produce a plausible-looking string, and only one of them is ours.

    ⚠⚠ Green here does NOT prove the wire carries a real version. `__version__`
    falls back to "unknown" when the distribution metadata is absent, which is
    every `PYTHONPATH=src` run including our own local suite. That fallback is
    deliberate and predates this (the `--version` flag has always done it):
    "unknown" is an honest could-not-establish, where "1.26.0" was a confident
    answer about a different package.
    """
    from importlib.metadata import version as _dist_version

    from jcodemunch_mcp import __version__

    opts = server_mod._initialization_options()
    assert opts.server_version == __version__
    assert opts.server_version != _dist_version("mcp")
