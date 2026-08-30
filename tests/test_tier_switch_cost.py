"""A mid-session tier switch is priced against the cache it invalidates.

⚠⚠ The defect: `set_tool_tier("standard")` and the shipped `model_tier_map`
both offered a narrowing that CANNOT REPAY ITSELF. `full` -> `standard` drops
9 of 91 tools and 1,810 schema tokens -- 6.7% -- while invalidating the whole
cached prefix, so it costs a full-rate write of 25,157 tokens to save 181 per
request: **174 requests to break even with an empty history, 864 with 100k.**

⚠⚠ **The intuition inverts on exactly the case that applies.** Uncached, the
same switch saves 1,810 tokens every request at no one-time cost and pays back
immediately. It is only wrong because the block is CACHED, which this
repository measured at 86% of baseline input. Every test below that asserts a
refusal has a sibling asserting the switch is still allowed in the direction
where it pays -- a gate that refused everything would satisfy half of them.
"""
from __future__ import annotations

import pytest

from jcodemunch_mcp import config as config_mod
from jcodemunch_mcp import server as server_mod
from jcodemunch_mcp.tier_switch_cost import (
    CACHE_READ_MULTIPLIER, CACHE_WRITE_MULTIPLIER, breakeven_requests, classify,
)

TIERS = ("core", "standard", "full")


# --------------------------------------------------------------------------- #
# The arithmetic
# --------------------------------------------------------------------------- #

def test_breakeven_is_write_cost_over_recurring_saving():
    # 10,000 -> 5,000: write 5,000 * 1.25 = 6,250; save 5,000 * 0.1 = 500.
    assert breakeven_requests(10_000, 5_000) == pytest.approx(12.5)


def test_history_only_ever_raises_the_breakeven():
    """⚠ `tools` is serialised AHEAD of system and messages, so the switch
    invalidates the accumulated turns too. Switching late is worse than early,
    and a price that ignores history is a FLOOR."""
    base = breakeven_requests(10_000, 5_000)
    prev = base
    for hist in (1_000, 10_000, 100_000):
        cur = breakeven_requests(10_000, 5_000, history_tokens=hist)
        assert cur > prev
        prev = cur


def test_a_widening_never_repays_and_is_not_a_defect():
    assert breakeven_requests(5_000, 10_000) is None
    assert classify(5_000, 10_000) == ("widening", None)


def test_noop_is_distinct_from_widening():
    assert classify(5_000, 5_000) == ("noop", None)


def test_classify_splits_paying_from_non_paying_at_the_horizon():
    verdict, be = classify(10_000, 5_000, horizon=100)
    assert (verdict, round(be, 1)) == ("pays", 12.5)
    # A 1% narrowing: tiny recurring saving, full-price write.
    verdict, be = classify(10_000, 9_900, horizon=100)
    assert verdict == "does_not_pay"
    assert be > 100


def test_the_multipliers_are_the_published_ones():
    """⚠ These are PUBLISHED rates, not measurements. Pinning them means a
    silent edit shows up as a failure rather than as a moved verdict."""
    assert (CACHE_READ_MULTIPLIER, CACHE_WRITE_MULTIPLIER) == (0.1, 1.25)


# --------------------------------------------------------------------------- #
# The measured surface
# --------------------------------------------------------------------------- #

def test_schema_tokens_per_profile_are_distinct_and_ordered():
    """The control. Every refusal test below is satisfied by a function that
    returns the same number for every tier."""
    weights = {t: server_mod._schema_tokens_for_profile(t) for t in TIERS}
    assert weights["core"] < weights["standard"] < weights["full"]
    assert weights["core"] > 0


def test_schema_tokens_price_what_the_client_ACTUALLY_receives():
    """⚠⚠ The first draft filtered the raw catalog by the tier bundle and was
    wrong by three tools in EVERY tier -- it kept the hidden front door and
    dropped the force-included tier controls. It priced a surface no client is
    ever sent. The only defensible source is the function `list_tools` uses."""
    for tier in TIERS:
        published = server_mod._build_tools_list(profile_override=tier)
        assert server_mod._schema_tokens_for_profile(tier) == sum(
            server_mod._schema_weight(t) for t in published
        )
        assert "set_tool_tier" in {t.name for t in published}, (
            f"{tier} dropped a force-included tier control"
        )


def test_profile_override_changes_nothing_when_omitted():
    assert [t.name for t in server_mod._build_tools_list()] == [
        t.name for t in server_mod._build_tools_list(profile_override=None)
    ]


def test_there_is_one_schema_weigher():
    """⚠ It was a closure inside `_tool_surface_stats` until pricing needed the
    same scale. Two copies that agree digit for digit are what make a later
    divergence invisible -- the `analyze_perf._percentile` lesson."""
    import inspect
    src = inspect.getsource(server_mod._tool_surface_stats)
    assert "_schema_weight" in src
    assert "def _weight" not in src


def test_standard_is_the_narrowing_that_does_not_pay():
    """The measurement this whole file exists for, asserted as a PROPERTY of
    the live catalog rather than as the literal 174."""
    verdict, be = classify(
        server_mod._schema_tokens_for_profile("full"),
        server_mod._schema_tokens_for_profile("standard"),
    )
    assert verdict == "does_not_pay"
    assert be > 100

    verdict, be = classify(
        server_mod._schema_tokens_for_profile("full"),
        server_mod._schema_tokens_for_profile("core"),
    )
    assert verdict == "pays", "core is the real narrowing and must stay allowed"
    assert be < 10


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #

@pytest.fixture
def clean_tier():
    server_mod._reset_session_tiers()
    yield
    server_mod._reset_session_tiers()


async def _set_tier(tier):
    from jcodemunch_mcp.server import call_tool
    import json
    from mcp.types import CallToolResult
    res = await call_tool("set_tool_tier", {"tier": tier})
    content = res.content if isinstance(res, CallToolResult) else res
    return json.loads(content[0].text)


@pytest.mark.asyncio
async def test_set_tool_tier_refuses_the_narrowing_that_does_not_pay(clean_tier):
    server_mod._set_session_tier("full")
    out = await _set_tier("standard")
    assert out["changed"] is False
    assert out["refused"] == "switch_does_not_pay"
    assert out["tier"] == "full"
    assert server_mod._effective_profile() == "full", "the tier moved anyway"
    assert out["switch_cost"]["breakeven_requests"] > 100
    # ⚠⚠ BODY, not `_meta`. `meta_fields` defaults to `[]`, so a reason
    # placed in `_meta` is stripped on a DEFAULT install -- the first draft
    # did exactly that and this assertion is what caught it.
    assert "startup" in out["reason"], "the refusal must name the way to get it"
    assert "_meta" not in out


@pytest.mark.asyncio
async def test_set_tool_tier_still_allows_the_narrowing_that_pays(clean_tier):
    """⚠ Non-vacuity for the test above: a gate that refuses every narrowing
    passes it and breaks the product."""
    server_mod._set_session_tier("full")
    out = await _set_tier("core")
    assert out["changed"] is True
    assert "refused" not in out
    assert server_mod._effective_profile() == "core"


@pytest.mark.asyncio
async def test_widening_is_never_refused(clean_tier):
    """⚠⚠ Escalating after a capability-gated failure BUYS A CAPABILITY.
    Refusing it to save tokens trades a correct answer for a cheap one, which
    is the worse error -- so this must hold even though it never repays."""
    for start in ("core", "standard"):
        server_mod._reset_session_tiers()
        server_mod._set_session_tier(start)
        out = await _set_tier("full")
        assert out["changed"] is True, f"{start} -> full was refused"
        assert server_mod._effective_profile() == "full"


@pytest.mark.asyncio
async def test_a_switch_to_the_current_tier_is_a_noop_not_a_refusal(clean_tier):
    server_mod._set_session_tier("full")
    out = await _set_tier("full")
    assert out["changed"] is False
    assert "refused" not in out


@pytest.mark.asyncio
async def test_a_refused_switch_emits_no_list_changed(clean_tier, monkeypatch):
    """⚠ The notification IS the cost. Refusing the switch while still telling
    the client the list moved would pay the whole bill for nothing."""
    calls = []

    async def _spy():
        calls.append(1)

    monkeypatch.setattr(server_mod, "_emit_tools_list_changed", _spy)
    server_mod._set_session_tier("full")
    await _set_tier("standard")
    assert calls == []
    await _set_tier("core")
    assert len(calls) == 1, "the allowed switch must still notify"


# --------------------------------------------------------------------------- #
# The shipped default map
# --------------------------------------------------------------------------- #

def test_no_default_map_entry_targets_a_switch_that_would_be_refused():
    """⚠⚠ Asserted as a PROPERTY, not as 'sonnet maps to full'. The old test
    pinned the map's contents, so it could only pass while the pessimizing
    route existed -- it was the defect's witness, not its guard.

    ⚠ Judged from `full`, the tier a session starts in by default and the only
    one any of these entries can narrow FROM.
    """
    full = server_mod._schema_tokens_for_profile("full")
    offenders = []
    for source, mapping in _shipped_maps().items():
        for pattern, tier in mapping.items():
            if tier not in TIERS:
                continue
            verdict, be = classify(full, server_mod._schema_tokens_for_profile(tier))
            if verdict == "does_not_pay":
                offenders.append(f"{source}: {pattern} -> {tier} ({be:,.0f} reqs)")
    assert not offenders, (
        "a shipped model_tier_map routes a model at a switch the server "
        "refuses: " + ", ".join(offenders)
    )


def _shipped_maps() -> "dict[str, dict]":
    """Every copy of the map that reaches a user.

    ⚠⚠ The first draft read `DEFAULTS` alone and passed while the CONFIG
    TEMPLATE -- the copy actually written into a user's `config.jsonc` -- still
    routed `claude-sonnet` and `gpt-4o` at `standard`. Fixing the constant and
    leaving the template is this project's most-repeated error: **we fix the
    reported call site and leave the mechanism.** A guard over one copy of a
    duplicated value is a guard over none.
    """
    import json
    import re
    from pathlib import Path

    maps = {"DEFAULTS": config_mod.DEFAULTS["model_tier_map"]}
    template = config_mod._fresh_config_content(Path("."))
    block = re.search(r'"model_tier_map":\s*(\{.*?\})', template, re.S)
    assert block, "the config template no longer declares model_tier_map"
    maps["config template"] = json.loads(block.group(1))
    return maps
