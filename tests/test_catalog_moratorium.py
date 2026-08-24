"""The catalog moratorium — a convention needs a test, not a habit.

The 2026-08-02 deep-research report's blunt finding: *"the product has crossed
the point where adding a tool automatically adds value."* 91 catalog actions,
route@1 under 50%, and issue #397 where generated guidance named 25 tools while
the server exposed 6. An action `route` never proposes is functionally absent,
so catalog growth past the front door's reach adds schema, documentation,
compatibility surface and test matrix while adding no reachable capability.

A moratorium written only in CONTRIBUTING.md is a habit. This file is the
policy: the ceiling is pinned, and raising it is an explicit edit that shows in
a diff and needs a reviewer to agree. That is the whole mechanism — not to make
a new action impossible, but to make it deliberate.

⚠ **The exit bar is named HERE, before the work, deliberately.** Same discipline
as the #398 Arc 4 thresholds in ROADMAP.md: neither side picks the bar after
seeing results.

⚠⚠ **The leakage ceiling is not decoration — without it the exit gate rewards
corrupting the corpus.** "Raise route@1 to 60%" is trivially satisfiable by
writing queries that paraphrase tool descriptions, which is the exact failure
v1.108.218's target audit was conducted to avoid. A recall bar with no leakage
bar is an invitation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BENCH = REPO / "benchmarks" / "route_recall"
RESULTS = BENCH / "results.json"           # visible corpus, MEASURED not GATED
HOLDOUT_RESULTS = BENCH / "holdout_results.json"   # the gate
HOLDOUT_CORPUS = BENCH / "holdout.json"

#: Catalog actions visible under `full`, pinned 2026-08-02 at v1.108.218.
#: Raising this is the deliberate act the moratorium exists to require.
CATALOG_CEILING = 91

# --------------------------------------------------------------------------- #
# Exit conditions. ALL must hold before CATALOG_CEILING may rise.               #
# --------------------------------------------------------------------------- #
#
# ⚠⚠ **The gate is `holdout.json`, NOT `queries.json`, and moving it there was a
# correction to this file's first version.** v1.108.219 gated on
# `queries.json` — the same corpus whose misses were about to be fixed. Fitting
# rules to a corpus and then scoring on it measures memorisation. The
# deep-research report said "held-out, low-leakage corpus" and that word was
# dropped when the gate was first written.
#
# The correction was not cosmetic. Measured 2026-08-02 BEFORE any routing fix:
#
#     visible queries.json          route@1  45.8%   name leakage 0.133
#     holdout.json (all 44)         route@1  20.5%   name leakage 0.057
#     holdout.json control subset   route@1  40.0%   name leakage 0.108
#
# ⚠ Read the CONTROL row for the like-for-like comparison: the full held-out set
# is enriched for hard cases by construction (24 of 44 entries mirror intents the
# counterfactual named as defective), so its 20.5% is not an "average user query"
# figure. The honest statement is that the visible corpus flatters comparable
# queries by ~6 points, and its higher leakage is the reason.

#: ⚠⚠ THE GATE IS THE CONTROL SUBSET, and this is the THIRD correction to it.
#:
#:   v1.108.219 gated on queries.json -- the corpus whose misses were about to
#:     be fixed. That certifies memorisation.
#:   v1.108.220 moved the gate to holdout.json, then measured after the fixes:
#:     aggregate 20.5% -> 65.9%, which CLEARS a 50% bar.
#:   It cleared it for the wrong reason. Broken out by class:
#:
#:       rule_preempted      (targeted)     8.3% -> 91.7%
#:       no_lexical_overlap  (targeted)     0.0% -> 83.3%
#:       control             (UNtargeted)  40.0% -> 40.0%
#:
#: The fixes moved exactly what they aimed at and nothing else. The aggregate
#: rose because 24 of 44 held-out entries mirror intents whose defects were
#: read off `explanations.json` before the rules were written. **The same author
#: wrote the holdout and the rules**, so those 24 are fitted, not held out, and
#: 65.9% is an upper bound rather than a measurement.
#:
#: The control subset is the only part of the corpus the fixes did not aim at.
#: Gating there is not a moved goalpost -- it is the definition of "held-out"
#: that the previous two versions of this gate both failed to implement.
EXIT_CONTROL_AT_1 = 55.0
EXIT_BASELINE_CONTROL_AT_1 = 40.0

#: Measured every run and reported, but NOT the gate: an aggregate over a corpus
#: partly fitted to the fix cannot certify anything.
AGGREGATE_IS_GATED = False

#: Leakage on the HELD-OUT corpus, measured at 0.057. Binding, with headroom for
#: honest corpus growth. Without this the recall bar is met by paraphrasing tool
#: descriptions into queries.
EXIT_MAX_NAME_LEAKAGE = 0.08

#: The visible corpus is still measured every run — it is the larger sample and
#: its per-gate breakdown drives the work. It is simply not the gate.
VISIBLE_CORPUS_IS_GATED = False

#: Actions that exist, are tested, and are deliberately NOT exposed. Each entry
#: is a decision the moratorium made, not an oversight.
WITHHELD = {
    "investigate_deletion_safety": (
        "v1.108.214. Importable and covered by 19 tests. Exposing it would make "
        "it the 92nd action while route@1 is under 50% — it does not jump the "
        "queue merely because we wrote it."
    ),
    "explain_route": (
        "v1.108.217. A 92nd action whose job is explaining why the 91st is hard "
        "to reach would be self-refuting. Driven by the benchmark harness."
    ),
    "investigate_reuse_before_write": (
        "v1.108.296. Importable, exported, and covered by its own test module. "
        "Measured at the time it was written, control route@1 was 40.0% against "
        "an exit bar of 55.0% -- the moratorium's condition 1 was not met, and "
        "an action the router would not propose is functionally absent however "
        "good it is. Exposing it is a separate decision from writing it."
    ),
}


def _catalog():
    import sys

    sys.argv = [sys.argv[0]]  # server module inspects argv on import
    from jcodemunch_mcp.server import _catalog_names

    return _catalog_names()


class TestCeiling:
    def test_the_catalog_has_not_grown(self):
        names = _catalog()
        assert len(names) <= CATALOG_CEILING, (
            f"the catalog grew to {len(names)}, above the moratorium ceiling of "
            f"{CATALOG_CEILING}.\n\n"
            "This is not a bug in the test. Adding a top-level action is under "
            "moratorium until ALL of:\n"
            f"  1. route@1 >= {EXIT_CONTROL_AT_1}% on the held-out CONTROL "
            f"subset (baseline {EXIT_BASELINE_CONTROL_AT_1}%);\n"
            f"  2. mean name leakage <= {EXIT_MAX_NAME_LEAKAGE} at that "
            "measurement, so the bar was not met by paraphrasing descriptions;\n"
            "  3. generated guidance references only callable actions under the "
            "active surface (#397).\n\n"
            "If the new action is genuinely warranted, raise CATALOG_CEILING in "
            "this file in the same commit. The visible diff IS the policy."
        )

    def test_the_ceiling_is_not_slack(self):
        """A ceiling far above the real count enforces nothing."""
        names = _catalog()
        assert len(names) == CATALOG_CEILING, (
            f"catalog is {len(names)} but the pin says {CATALOG_CEILING}; a "
            "ceiling with headroom lets an action land without a decision"
        )


class TestWithheldActions:
    @pytest.mark.parametrize("action", sorted(WITHHELD))
    def test_a_withheld_action_is_not_exposed(self, action):
        assert action not in _catalog(), (
            f"{action} is exposed. {WITHHELD[action]}"
        )

    def test_withheld_actions_still_exist(self):
        """The moratorium withholds a SURFACE, never a capability. If these stop
        importing, the policy has quietly become deletion."""
        from jcodemunch_mcp.investigator import (  # noqa: F401
            explain_route,
            investigate_deletion_safety,
            investigate_reuse_before_write,
        )


class TestExitConditions:
    @pytest.fixture
    def holdout(self):
        if not HOLDOUT_RESULTS.exists():
            pytest.skip("holdout_results.json not present")
        return json.loads(HOLDOUT_RESULTS.read_text(encoding="utf-8"))

    @pytest.fixture
    def visible(self):
        if not RESULTS.exists():
            pytest.skip("route_recall results.json not present")
        return json.loads(RESULTS.read_text(encoding="utf-8"))["summary"]

    def _control_at_1(self, holdout) -> float:
        """route@1 over the control subset only.

        The control entries mirror intents that were NOT defective, so they are
        the regression detector: a fix that raises the aggregate while breaking
        these has made routing worse, not better.
        """
        corpus = json.loads(HOLDOUT_CORPUS.read_text(encoding="utf-8"))
        mirrors = {q["q"]: q.get("mirrors", "control") for q in corpus["queries"]}
        rows = [r for r in holdout["per_query"] if mirrors.get(r["query"]) == "control"]
        assert rows, "the held-out corpus has no control entries to regress against"
        hits = sum(1 for r in rows if r["route_rank"] == 1)
        return round(100.0 * hits / len(rows), 1)

    def test_the_gate_is_the_held_out_corpus(self, holdout, visible):
        """The correction this file's first version needed.

        Scoring the gate on the corpus whose misses are being fixed certifies
        overfitting. Measured before any fix, the two disagreed by 25.3 points
        overall and ~6 on comparable queries, with leakage explaining the gap.
        """
        assert VISIBLE_CORPUS_IS_GATED is False
        assert holdout["summary"]["queries"] >= 40, (
            "a held-out corpus too small to be a gate"
        )
        # Both are measured every run. Only one binds.
        assert "route_recall" in visible

    def test_control_subset_has_not_regressed(self, holdout):
        """A fix that breaks a working route is not progress."""
        ctrl = self._control_at_1(holdout)
        assert ctrl >= EXIT_BASELINE_CONTROL_AT_1 - 0.1, (
            f"control-subset route@1 fell to {ctrl}% (baseline "
            f"{EXIT_BASELINE_CONTROL_AT_1}%). Intents that already routed "
            "correctly are now broken."
        )

    def test_the_aggregate_is_reported_but_not_gated(self, holdout):
        """The finding that forced the third version of this gate.

        v1.108.220's rules took the held-out aggregate from 20.5% to 65.9% while
        the untargeted control subset stayed at exactly 40.0%. A number that
        moves only where the fix aimed is a measurement of the fix's aim.
        """
        assert AGGREGATE_IS_GATED is False
        agg = holdout["summary"]["route_recall"]["@1"]
        ctrl = self._control_at_1(holdout)
        assert agg >= ctrl - 0.1, (
            "the aggregate has fallen below the control subset; the fitted "
            "classes have regressed and the corpus split needs re-reading"
        )

    def test_moratorium_still_in_force(self, holdout):
        """Fails on the day the moratorium may lift. That is the point.

        ⚠ It has fired once already, at v1.108.220, and the answer was NOT to
        lift. The aggregate cleared a 50% bar on a corpus 24/44 fitted to the
        fix. Reading that as an exit would have certified overfitting, which is
        the failure this whole gate exists to prevent.
        """
        s = holdout["summary"]
        leak = s["leakage"]["mean_name_overlap"]
        ctrl = self._control_at_1(holdout)
        met = ctrl >= EXIT_CONTROL_AT_1 and leak <= EXIT_MAX_NAME_LEAKAGE
        assert not met, (
            f"control-subset route@1 {ctrl}% (bar {EXIT_CONTROL_AT_1}%) at name "
            f"leakage {leak} (ceiling {EXIT_MAX_NAME_LEAKAGE}). The exit "
            "conditions are MET on the untargeted subset. This failure is a "
            "prompt, not a defect: decide explicitly whether to lift the "
            "moratorium, then update this test."
        )

    def test_a_recall_bar_without_a_leakage_bar_would_be_gameable(self, holdout):
        """Non-vacuous: the leakage ceiling has to be able to bind."""
        assert EXIT_MAX_NAME_LEAKAGE < 1.0
        leak = holdout["summary"]["leakage"]["mean_name_overlap"]
        assert leak <= EXIT_MAX_NAME_LEAKAGE, (
            f"held-out leakage {leak} already exceeds the ceiling "
            f"{EXIT_MAX_NAME_LEAKAGE} the exit gate relies on"
        )

    def test_the_held_out_corpus_is_genuinely_harder(self, holdout, visible):
        """Records the gap rather than asserting a direction.

        If the held-out corpus ever scores ABOVE the visible one, something is
        wrong with one of them and the gate should not be trusted until it is
        understood.
        """
        h = holdout["summary"]["route_recall"]["@1"]
        v = visible["route_recall"]["@1"]
        assert h <= v + 5.0, (
            f"held-out route@1 ({h}%) exceeds visible ({v}%) — the held-out set "
            "is supposed to be at least as hard; investigate before trusting "
            "either number"
        )


class TestGuidanceMatchesTheSurface:
    """Exit condition 3, measured rather than asserted (#397).

    The failure was not theoretical: generated `CLAUDE.md` named 25 tools while
    a default server exposed 6, so the policy meant to ensure jCodeMunch got
    used instead instructed the agent to call tools that were not there.
    """

    def test_counter_policy_names_only_front_door_actions(self, monkeypatch):
        import re
        import sys

        monkeypatch.setenv("JCODEMUNCH_TOOL_SURFACE", "counter")
        sys.argv = [sys.argv[0]]
        from jcodemunch_mcp.cli import init as _init

        policy = _init.active_policy()
        referenced = set(_init._TOOL_REF_RE.findall(policy))

        from jcodemunch_mcp.server import _CANONICAL_TOOL_NAMES

        known = set(_CANONICAL_TOOL_NAMES)
        callable_now = {"order", "menu", "route"} | {
            "jcodemunch_guide", "announce_model", "set_tool_tier",
        }
        leaked = (referenced & known) - callable_now
        assert not leaked, (
            "the counter policy names actions the client will not offer the "
            f"model: {sorted(leaked)} (#397)"
        )

    def test_full_policy_names_only_real_actions(self, monkeypatch):
        import sys

        monkeypatch.setenv("JCODEMUNCH_TOOL_SURFACE", "full")
        sys.argv = [sys.argv[0]]
        from jcodemunch_mcp.cli import init as _init
        from jcodemunch_mcp.server import _CANONICAL_TOOL_NAMES

        policy = _init.active_policy()
        referenced = set(_init._TOOL_REF_RE.findall(policy))
        known = set(_CANONICAL_TOOL_NAMES) | {"order", "menu", "route"}
        # Only judge tokens that LOOK like our actions; prose contains other
        # backticked identifiers (config keys, env vars) that are not tools.
        suspects = {r for r in referenced if r.startswith((
            "get_", "find_", "check_", "search_", "index_", "plan_", "list_",
            "assemble_", "winnow_", "render_", "suggest_", "digest",
        ))}
        assert suspects <= known, sorted(suspects - known)
