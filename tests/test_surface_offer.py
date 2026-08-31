"""The priced, opt-in surface offer (surface_offer.py).

The property under test is not "an offer renders". It is that the offer is a
MESSAGE: it never writes config, it is priced by what ``list_tools`` actually
publishes, it always carries its basis, and every route out of it (accept,
undo, silence) is reachable by a command the user types.
"""

from __future__ import annotations

import pytest

from jcodemunch_mcp import config as config_module
from jcodemunch_mcp import surface_offer
from jcodemunch_mcp.surface_offer import (
    CURRENT_DEFAULT_SURFACE,
    build_offer,
    render_offer_lines,
)
from jcodemunch_mcp.tier_switch_cost import SCHEMA_TOKENS_BASIS


def _offer(**over):
    kwargs = dict(
        current_surface="full",
        current_tools=91,
        current_schema_tokens=26943,
        offer_tools=6,
        offer_schema_tokens=1050,
        catalog_tools=94,
        seen=False,
    )
    kwargs.update(over)
    return build_offer(**kwargs)


# --- omit-when-clean ------------------------------------------------------- #


def test_offer_renders_for_a_full_install():
    offer = _offer()
    assert offer is not None
    assert offer["schema_tokens_delta"] == 26943 - 1050


def test_silenced_install_gets_no_offer():
    assert _offer(seen=True) is None


def test_install_already_on_the_target_surface_gets_no_offer():
    assert _offer(current_surface=CURRENT_DEFAULT_SURFACE) is None


@pytest.mark.parametrize("tokens", [1050, 900, 0])
def test_non_positive_delta_refuses(tokens):
    """An offer with nothing to sell must not render.

    Reachable in the wild: ``disabled_tools`` can trim the visible surface below
    the front door's own weight. A row that appears with no saving behind it
    trains people to skip the row that matters.
    """
    assert _offer(current_schema_tokens=tokens) is None


def test_surface_comparison_is_case_and_space_insensitive():
    assert _offer(current_surface="  Counter  ") is None


# --- the basis travels with the number ------------------------------------- #


def test_offer_carries_its_basis():
    offer = _offer()
    assert offer["schema_tokens_basis"] == SCHEMA_TOKENS_BASIS
    assert "NOT a per-request saving" in offer["schema_tokens_basis_note"]


def test_human_rendering_prints_the_basis_and_the_switching_cost():
    """A machine-readable field the CLI does not print leaves the human surface
    carrying the defect, and a human is exactly who supplies the wrong basis
    (the 1.108.312 lesson). Both must appear in the rendered text."""
    text = "\n".join(render_offer_lines(_offer()))
    assert SCHEMA_TOKENS_BASIS in text
    assert "NOT a per-request saving" in text
    assert "cache-written once" in text


def test_human_rendering_states_that_capability_is_preserved():
    text = "\n".join(render_offer_lines(_offer()))
    assert "85 tools would stop being advertised" in text
    assert "order/menu/route" in text


def test_every_exit_route_is_a_command_the_user_types():
    offer = _offer()
    for key, expect in (
        ("switch_command", "tool_surface counter"),
        ("undo_command", "tool_surface full"),
        ("silence_command", "surface_offer_seen true"),
    ):
        assert expect in offer[key]
        assert offer[key] in "\n".join(render_offer_lines(offer))


# --- the offer is a message, not a migration -------------------------------- #


_WRITERS = frozenset(
    {"set_config", "save_config", "upgrade_config", "write_text", "write_bytes", "open"}
)


def _reached_names(src: str) -> set[str]:
    """Names this source actually CALLS or IMPORTS, ignoring prose.

    A text scan cannot do this job: surface_offer.py's own docstring explains
    the ``upgrade_config`` freeze at length, and a substring ratchet fires on
    the explanation instead of the behaviour. (A ratchet can pass -- or fail --
    against something other than the defect it names.)
    """
    import ast

    reached: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            reached.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            reached.add((node.module or "").split(".")[0])
            reached.update(a.name for a in node.names)
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                reached.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                reached.add(fn.attr)
    return reached


def test_module_never_writes_config():
    """The freeze exists so a package update cannot collapse a user's surface.
    An offer that could apply itself would reintroduce exactly that."""
    import pathlib

    src = pathlib.Path(surface_offer.__file__).read_text(encoding="utf-8")
    reached = _reached_names(src)
    assert not (reached & _WRITERS), f"surface_offer.py must not reach {reached & _WRITERS}"
    assert "config" not in reached, "surface_offer.py must not import config"


def test_the_write_ratchet_fires_against_a_reintroduced_writer():
    """Non-vacuity: a green ratchet and an absent ratchet look identical.

    Run it against the defect, not only against the fixed tree.
    """
    bad = (
        "from . import config\n"
        "def go():\n"
        "    config.set_config('tool_surface', 'counter')\n"
    )
    reached = _reached_names(bad)
    assert reached & _WRITERS
    assert "config" in reached


def test_upgrade_config_still_cannot_back_inject_tool_surface():
    """The offer must not have been 'fixed' by unfreezing the key.

    ``tool_surface`` stays out of the template on purpose; if it ever appears
    there uncommented, a package update starts changing served surfaces and the
    offer becomes redundant in the worst possible way.
    """
    template = config_module.generate_template()
    for line in template.splitlines():
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        assert '"tool_surface"' not in stripped


def test_offer_target_matches_what_a_fresh_install_actually_gets():
    """Binds the offered surface to `_fresh_config_content`'s real default.

    Without this the two drift and we offer a surface new installs no longer
    receive -- the offer would be advertising a default that does not exist.
    """
    import inspect

    src = inspect.getsource(config_module._fresh_config_content)
    assert f'"{CURRENT_DEFAULT_SURFACE}"' in src


# --- the new config key ----------------------------------------------------- #


def test_surface_offer_seen_is_a_declared_bool_defaulting_false():
    assert config_module.DEFAULTS["surface_offer_seen"] is False
    assert config_module.CONFIG_TYPES["surface_offer_seen"] is bool


def test_surface_offer_seen_ships_commented_in_the_template():
    """Silencing must be the user's act, never a template default."""
    template = config_module.generate_template()
    assert "surface_offer_seen" in template
    for line in template.splitlines():
        stripped = line.strip()
        if "surface_offer_seen" in stripped:
            assert stripped.startswith("//")


# --- priced by what list_tools publishes, never a second copy ---------------- #


def test_surface_override_prices_the_counter_branch_exactly():
    """`surface_override` must reproduce what a counter client actually receives.

    The counter branch deliberately BYPASSES tier filtering and
    ``disabled_tools``. A hand-rolled count would apply them and under-report
    the surface -- which is `_schema_tokens_for_profile`'s defect one axis over
    (that one was wrong by three tools in every tier).
    """
    from jcodemunch_mcp import server

    priced = {t.name for t in server._build_tools_list(surface_override="counter")}
    served = {t.name for t in server._build_tools_list()}

    assert priced == (server._COUNTER_FRONT_DOOR | server._ALWAYS_PRESENT_TOOLS)
    # Non-vacuity: the override must actually change the answer on this box,
    # or the assertion above proves nothing about the override.
    assert priced != served


def test_offer_is_omitted_from_stats_when_already_on_the_default(monkeypatch):
    from jcodemunch_mcp import server

    monkeypatch.setattr(server, "_effective_surface", lambda: "counter")
    monkeypatch.setattr(
        server, "_surface_resolution", lambda: ("counter", "counter", True)
    )
    assert "surface_offer" not in server._tool_surface_stats()


def test_offer_appears_in_stats_for_a_full_install(monkeypatch):
    from jcodemunch_mcp import server

    monkeypatch.setattr(server, "_effective_surface", lambda: "full")
    monkeypatch.setattr(server, "_surface_resolution", lambda: ("full", "full", True))
    monkeypatch.setattr(
        server.config_module,
        "get",
        lambda key, default=None: False if key == "surface_offer_seen" else default,
    )
    stats = server._tool_surface_stats()
    offer = stats.get("surface_offer")
    assert offer is not None
    # Priced off the same block the receipt reports, not a recomputation.
    assert offer["current_schema_tokens"] == stats["schema_tokens_visible"]
    assert offer["offer_schema_tokens"] < offer["current_schema_tokens"]


def test_a_failed_offer_computation_never_breaks_the_status_command(monkeypatch):
    """A status command must not fail because an advisory row could not be built."""
    from jcodemunch_mcp import server

    def boom(*a, **k):
        raise RuntimeError("no")

    monkeypatch.setattr(server, "_build_tools_list", boom)
    assert (
        server._surface_offer(
            current_surface="full",
            current_tools=91,
            current_schema_tokens=26943,
            catalog_tools=94,
        )
        is None
    )


# --- the one-time server-start notice --------------------------------------- #


def test_log_line_carries_delta_basis_and_both_exits():
    line = surface_offer.render_offer_log_line(_offer())
    assert "25,893" in line
    assert SCHEMA_TOKENS_BASIS in line
    assert "not a per-request saving" in line
    assert "order/menu/route" in line
    assert "config set tool_surface counter" in line
    assert "config set surface_offer_seen true" in line
    assert "appears once" in line


def test_log_line_is_one_line():
    """A multi-line banner on a stdio server's stderr is chatter, and this
    server has a handshake watchdog for exactly that class of noise."""
    assert "\n" not in surface_offer.render_offer_log_line(_offer())


def _announce_env(tmp_path, monkeypatch, offer=True):
    from jcodemunch_mcp import server

    monkeypatch.setenv("CODE_INDEX_PATH", str(tmp_path))
    monkeypatch.setattr(
        server,
        "_tool_surface_stats",
        lambda *a, **k: {"surface_offer": _offer()} if offer else {},
    )
    return server


def test_the_latch_records_who_announced(tmp_path, monkeypatch):
    """⚠ A once-per-install notice with no attribution cannot answer "did a
    human ever see this?" -- the first version recorded only time, surface and
    version, and a background server whose stderr nobody reads had consumed the
    one announcement on the dev box before anyone observed it.
    """
    import json
    import os

    server = _announce_env(tmp_path, monkeypatch)
    assert server._announce_surface_offer("stdio") is True
    latch = json.loads(
        (tmp_path / "surface_offer_state.json").read_text(encoding="utf-8")
    )
    assert latch["pid"] == os.getpid()
    assert latch["transport"] == "stdio"
    assert latch["surface"] == "full"
    assert latch["announced_at"]


def test_the_call_site_passes_the_real_transport():
    """A default-valued parameter that no call site fills is indistinguishable
    from the defect it was added to fix (the `repo=` lesson, #508)."""
    import ast
    import pathlib as _pl

    import jcodemunch_mcp.server as server_mod

    tree = ast.parse(_pl.Path(server_mod.__file__).read_text(encoding="utf-8"))
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "_announce_surface_offer"
    ]
    assert len(calls) == 1
    assert calls[0].args, "the one call site must pass a transport, not rely on the default"


def test_announcement_fires_once_then_latches(tmp_path, monkeypatch, caplog):
    server = _announce_env(tmp_path, monkeypatch)
    with caplog.at_level("WARNING"):
        assert server._announce_surface_offer() is True
    assert any("tool_surface is" in r.getMessage() for r in caplog.records)
    assert (tmp_path / "surface_offer_state.json").is_file()
    # Second start says nothing.
    assert server._announce_surface_offer() is False


def test_nothing_to_offer_announces_nothing_and_writes_no_latch(tmp_path, monkeypatch):
    """A run with nothing to say must not consume the one announcement."""
    server = _announce_env(tmp_path, monkeypatch, offer=False)
    assert server._announce_surface_offer() is False
    assert not (tmp_path / "surface_offer_state.json").exists()


def test_an_unwritable_latch_still_announces(tmp_path, monkeypatch, caplog):
    """Fails in the recoverable direction: repeating an advisory line is
    recoverable, suppressing it forever is not."""
    server = _announce_env(tmp_path, monkeypatch)
    import pathlib

    monkeypatch.setattr(
        pathlib.Path, "mkdir", lambda *a, **k: (_ for _ in ()).throw(OSError("ro"))
    )
    with caplog.at_level("WARNING"):
        assert server._announce_surface_offer() is True


def test_a_pricing_failure_never_breaks_server_start(tmp_path, monkeypatch):
    from jcodemunch_mcp import server

    monkeypatch.setenv("CODE_INDEX_PATH", str(tmp_path))

    def boom(*a, **k):
        raise RuntimeError("no")

    monkeypatch.setattr(server, "_tool_surface_stats", boom)
    assert server._announce_surface_offer() is False


def test_announcement_runs_above_both_transport_dispatch_branches():
    """One call must cover every transport exactly once.

    Asserting the call site, not just the function: `serve` has two dispatch
    branches (with and without the watcher) and six `asyncio.run` sites between
    them. A per-transport call is how one of six silently misses.
    """
    import ast
    import pathlib

    import jcodemunch_mcp.server as server_mod

    tree = ast.parse(pathlib.Path(server_mod.__file__).read_text(encoding="utf-8"))
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "_announce_surface_offer"
    ]
    assert len(calls) == 1, f"expected exactly one call site, found {len(calls)}"
