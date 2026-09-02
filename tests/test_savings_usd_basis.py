"""The dollar figure states what it prices (2026-09-02).

Fourth instance of a documented family — `hit_rate_basis`,
`schema_tokens_basis`, `basis: excess_calls` — and the rule each time is the
same: **a figure whose basis is unstated gets a wrong one supplied for free.**

Prompted by a competitor (Graft) converting claimed token savings to a *blended
session rate*. That is the right correction for tokens CONSUMED and the wrong
one for tokens AVOIDED. Measured on this box across 25 transcripts: **98.6% of
input is cache reads**, a 0.1166x blended multiplier — dividing by it would cut
the figure ~8.6x and would price an avoided token as though it were in the cache
being re-read. It was never written, so it is never read.

⚠⚠ **THE FIX IS A LABEL AND `test_the_dollar_arithmetic_is_untouched` is what
keeps it one.** A number quietly scaled by 0.1166 would answer neither the
"what did this save" question nor the "what did I actually pay" question, and
nothing on the wire would show it had happened — the `analyze_perf` raw
`hit_rate` rule. The arithmetic must stay exactly as it was.
"""

from __future__ import annotations

import json

from jcodemunch_mcp.cli import receipt as R


def test_the_dollar_arithmetic_is_untouched():
    """⚠⚠ The non-negotiable half: a label was added, not a scale factor."""
    # $5.00/MTok on 1,000,000 avoided tokens is exactly $5.00, unchanged.
    assert R.dollar_savings(1_000_000, "opus") == 5.0
    assert R.dollar_savings(1_000_000, "sonnet") == 2.0
    assert R.dollar_savings(1_000_000, "haiku") == 1.0
    assert R.dollar_savings(1_000_000, "fable") == 10.0
    assert R.dollar_savings(0, "opus") == 0.0
    # And nothing near the measured blended multiplier crept in.
    assert R.dollar_savings(1_000_000, "opus") != 5.0 * 0.1166


def test_rates_surface_carries_the_basis():
    """`--rates` exists so consumers price their own counts off one table.

    Handing them the rates without the basis reproduces the omission one
    process downstream, which is how the jMunch Console ended up with a
    duplicate rate table in the first place.
    """
    payload = json.loads(R.render_rates())
    assert payload["savings_usd_basis"] == R.SAVINGS_USD_BASIS
    assert payload["savings_usd_note"] == R.SAVINGS_USD_NOTE


def test_the_basis_names_both_omissions():
    """A basis that does not say WHAT is excluded is a label, not a basis."""
    note = R.SAVINGS_USD_NOTE.lower()
    assert "once" in note
    assert "cache-write" in note or "cache write" in note
    assert "cache read" in note
    assert "floor" in note


def test_the_human_surface_carries_it_too():
    """⚠⚠ The v1.108.312 lesson, which this is one field over from.

    A machine-readable field the CLI does not print leaves the human surface
    carrying the defect — and a human is exactly who supplies a missing basis.
    Both rendered blocks must say it.
    """
    import inspect

    totals_src = inspect.getsource(R)
    # The windowed total and the lifetime meter are rendered by different
    # functions; neither may be the only one that discloses.
    assert totals_src.count("Floor:") >= 2, (
        "both the windowed total and the lifetime meter must state the basis"
    )


def test_render_json_attaches_basis_to_the_figure():
    """The basis travels WITH the number, not in a sibling document."""
    agg = {
        "totals": {"savings_tokens": 2_000_000, "calls": 10,
                   "actual_tokens": 100, "baseline_tokens": 200},
        "per_tool": {},
    }
    payload = json.loads(R.render_json(agg, model="opus"))
    assert payload["savings_usd"] == 10.0
    assert payload["savings_usd_basis"] == R.SAVINGS_USD_BASIS
    assert payload["savings_usd_note"] == R.SAVINGS_USD_NOTE
