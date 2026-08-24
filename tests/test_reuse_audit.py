"""Reuse-before-write as proof obligations.

The load-bearing test in this file is
``test_the_same_repo_downgrades_when_the_synonym_channel_is_off``. Everything
else guards a rule; that one guards the reason the module exists.

A reuse checker that finds nothing lexically and reports "write it" is right
about the repositories it can fully see and silently wrong about every
repository it cannot. The two states are indistinguishable in its output, and
they are indistinguishable exactly when the writer most needs them separated:
an intent of "modal" against an existing ``Dialog`` shares no token with it, so
only the embedding channel can connect them. That test runs one fixture, one
intent, and one difference -- whether the synonym channel was available -- and
requires the two verdicts to differ.

``_verdict`` is the only place a conclusion may be drawn, so it is also tested
in isolation. If those pass and the module still reports a bad verdict, the bug
is in obligation status assignment, not in the rule.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from jcodemunch_mcp.investigator import (
    ADAPT_CANDIDATE,
    LEXICAL,
    LEXICAL_ONLY,
    Obligation,
    REFUTED,
    REUSE_AVAILABLE,
    SATISFIED,
    SEMANTIC,
    STRUCTURAL,
    UNESTABLISHED,
    WRITE_JUSTIFIED,
)
from jcodemunch_mcp.investigator import (
    investigate_reuse_before_write as _investigate,
)
from jcodemunch_mcp.investigator.reuse_audit import (
    NOT_ESTABLISHED,
    _identifier_forms,
    _intent_terms,
    _verdict,
)
from jcodemunch_mcp.tools.index_folder import index_folder

# One tree carrying every shape the verdicts distinguish.
FIXTURE = {
    # LIVE and named for its intent: the reuse case.
    "src/dates.py": (
        "def format_iso_date(ts):\n"
        '    """Format a timestamp as an ISO 8601 string."""\n'
        "    return str(ts)\n"
    ),
    "src/app.py": (
        "from .dates import format_iso_date\n\n"
        "def boot(ts):\n"
        "    return format_iso_date(ts)\n"
    ),
    # DEAD and named for its intent: implemented, and nothing calls it.
    "src/ui.py": (
        "def render_modal_dialog(title, body):\n"
        '    """Render a modal dialog."""\n'
        "    return (title, body)\n"
    ),
}

#: Shares no token with anything in FIXTURE, so the lexical channel is
#: genuinely clean and the verdict turns on the semantic channel alone.
UNRELATED_INTENT = "slerp between two quaternions"


@pytest.fixture(scope="module")
def repo(tmp_path_factory) -> tuple[str, str]:
    root = tmp_path_factory.mktemp("reuse_fx")
    for rel, body in FIXTURE.items():
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    storage = str(Path(root) / ".index")
    res = index_folder(str(root), use_ai_summaries=False, storage_path=storage)
    return res.get("repo", str(root)), storage


def investigate(repo: tuple[str, str], intent: str, **kw) -> dict:
    """Always bound to the fixture's own storage.

    A call that forgot the keyword would investigate the developer's real
    index: it would pass, prove nothing, and read the machine it ran on.
    """
    kw.setdefault("storage_path", repo[1])
    return _investigate(repo[0], intent, **kw)


@pytest.fixture
def semantic_available(monkeypatch):
    """Stand in for a configured provider that searched and found nothing.

    Two seams, because the channel has two gates and both refuse without an
    encoder: ``_semantic_state`` decides whether to attempt the search at all,
    and ``search_symbols`` itself returns ``no_embedding_provider`` when asked
    for ``semantic_only`` without one.

    ⚠ The stand-in is deliberately NARROW. It intercepts only the
    ``semantic_only`` call and delegates every other call to the real function,
    so the lexical channel, the name probe and the liveness pass all run
    against the real index. A mock broad enough to satisfy the assertion would
    bypass the thing the assertion is about; tests that use this fixture assert
    on ``calls`` so a stand-in that stopped being reached cannot pass silently.

    Yields the list of intercepted calls.
    """
    import jcodemunch_mcp.investigator.reuse_audit as ra
    import jcodemunch_mcp.tools.search_symbols as ss

    real = ss.search_symbols
    calls: list[dict] = []

    def only_the_semantic_call(*args, **kw):
        if kw.get("semantic_only"):
            calls.append(kw)
            return {"results": []}
        return real(*args, **kw)

    monkeypatch.setattr(ra, "_semantic_state", lambda store, owner, name: ("used", ""))
    monkeypatch.setattr(ss, "search_symbols", only_the_semantic_call)
    return calls


def _ob(result: dict, name: str) -> dict:
    for o in result["obligations"]:
        if o["obligation"] == name:
            return o
    raise AssertionError(f"obligation {name!r} missing from {result['obligations']}")


# --- The headline: a channel that was off is not a channel that was clean --- #


class TestSemanticChannelIsLoadBearing:
    def test_write_justified_requires_the_semantic_obligation_satisfied(
        self, repo, semantic_available
    ):
        r = investigate(repo, UNRELATED_INTENT)
        assert semantic_available, "the semantic channel was never reached"
        assert _ob(r, "no_semantic_match")["status"] == SATISFIED
        assert r["channels"]["semantic"] == "ok"
        assert r["verdict"] == WRITE_JUSTIFIED

    def test_the_same_repo_downgrades_when_the_synonym_channel_is_off(self, repo):
        """One fixture, one intent, one difference. The verdicts must differ.

        Without this the module is a lexical search with a longer docstring.
        The repository below has no embeddings, so an existing implementation
        under a different vocabulary was never ruled out, and reporting
        ``write_justified`` would assert a search that did not happen.

        The channel state is asserted as "not usable" rather than pinned to one
        spelling: whether an unembedded repo reports ``no_provider`` or
        ``repo_not_embedded`` depends on what is installed on the machine
        running the test, and pinning it would make this test a property of the
        box. The states are pinned individually below, where each is forced.
        """
        r = investigate(repo, UNRELATED_INTENT)
        assert _ob(r, "no_semantic_match")["status"] == UNESTABLISHED
        assert r["verdict"] == LEXICAL_ONLY
        assert r["verdict"] != WRITE_JUSTIFIED
        assert r["channels"]["semantic"] != "ok"

    def test_no_provider_names_installing_one(self, repo, monkeypatch):
        """The two ways the channel goes dark need opposite advice, and telling
        a repo with an encoder to ``pip install`` is as useless as telling one
        without to ``embed_repo``."""
        import jcodemunch_mcp.retrieval.verdict as v

        monkeypatch.setattr(v, "_semantic_provider_available", lambda: False)
        r = investigate(repo, UNRELATED_INTENT)
        assert r["channels"]["semantic"] == "no_provider"
        assert "embedding provider" in r["recommended_next_action"]

    def test_an_unembedded_repo_names_embed_repo(self, repo, monkeypatch):
        import jcodemunch_mcp.retrieval.verdict as v
        import jcodemunch_mcp.storage.embedding_store as es

        monkeypatch.setattr(v, "_semantic_provider_available", lambda: True)
        monkeypatch.setattr(es.EmbeddingStore, "has_any", lambda self: False)
        r = investigate(repo, UNRELATED_INTENT)
        assert r["channels"]["semantic"] == "repo_not_embedded"
        assert "embed_repo" in r["recommended_next_action"]

    def test_the_lexical_channel_was_genuinely_clean_in_both(self, repo):
        """The downgrade must come from the semantic channel, not from a
        lexical miss that would have downgraded the verdict anyway."""
        r = investigate(repo, UNRELATED_INTENT)
        assert _ob(r, "no_lexical_match")["status"] == SATISFIED
        assert _ob(r, "no_name_twin")["status"] == SATISFIED
        assert r["candidates"] == []

    def test_an_unreadable_embedding_store_is_unknown_not_clean(self, repo, monkeypatch):
        """``has_any`` is tri-state and ``None`` means could-not-establish.

        Falling through on ``None`` would run a semantic search whose empty
        result is indistinguishable from a clean sweep, collapsing UNKNOWN into
        SATISFIED in the one obligation this module exists to keep honest.
        """
        import jcodemunch_mcp.retrieval.verdict as v
        import jcodemunch_mcp.storage.embedding_store as es

        monkeypatch.setattr(v, "_semantic_provider_available", lambda: True)
        monkeypatch.setattr(es.EmbeddingStore, "has_any", lambda self: None)
        r = investigate(repo, UNRELATED_INTENT)
        assert r["channels"]["semantic"] == "unknown"
        assert _ob(r, "no_semantic_match")["status"] == UNESTABLISHED
        assert r["verdict"] == LEXICAL_ONLY


# --- A dead match is not a reuse candidate --------------------------------- #


class TestLiveness:
    def test_a_live_match_refutes_and_is_offered_for_reuse(self, repo):
        r = investigate(repo, "format an ISO date")
        assert r["verdict"] == REUSE_AVAILABLE
        assert "format_iso_date" in [c["name"] for c in r["candidates"]]
        assert all(c["live"] is not False for c in r["candidates"])
        assert r.get("dead_matches") in (None, [])

    def test_a_strong_match_proven_dead_is_not_a_reuse_instruction(self, repo):
        """Pointing a writer at an unreferenced helper does not prevent
        duplication, it doubles the dead code -- and it is the failure a
        keyword matcher cannot detect, because the match looks identical."""
        r = investigate(repo, "render a Modal dialog")
        dead = r.get("dead_matches") or []
        assert [c["name"] for c in dead] == ["render_modal_dialog"]
        assert dead[0]["live"] is False
        assert dead[0]["match_strength"] >= 0.80, (
            "must be a STRONG match, or this proves nothing about strong matches"
        )
        assert r["verdict"] != REUSE_AVAILABLE
        assert r["reuse_candidates"] == []

    def test_the_dead_match_verdict_names_the_revive_or_delete_decision(self, repo):
        r = investigate(repo, "render a Modal dialog")
        assert r["verdict"] == ADAPT_CANDIDATE
        action = r["recommended_next_action"]
        assert "nothing references it" in action
        assert "render_modal_dialog" in action

    def test_the_dead_match_still_refuted_its_obligation(self, repo):
        """The obligation is genuinely refuted -- the name IS taken. Only the
        conclusion drawn from it changes."""
        r = investigate(repo, "render a Modal dialog")
        assert _ob(r, "no_name_twin")["status"] == REFUTED

    def test_unknown_liveness_still_refutes(self, repo, monkeypatch):
        """``live is None`` must block writing, not permit it. A candidate we
        could not check is never promoted to live and never dismissed as dead;
        the claim stays refused either way."""
        import jcodemunch_mcp.investigator.reuse_audit as ra

        monkeypatch.setattr(ra, "_establish_liveness", lambda repo, cands, sp: 0)
        r = investigate(repo, "format an ISO date")
        assert r["candidates"], "the fixture must produce a candidate to check"
        assert all(c["live"] is None for c in r["candidates"])
        assert r["verdict"] == REUSE_AVAILABLE
        assert r.get("dead_matches") in (None, [])

    def test_unknown_liveness_does_not_rescue_a_dead_match_into_reuse(
        self, repo, monkeypatch
    ):
        """The mirror of the test above, on the dead fixture. Unknown blocks
        writing; it must not promote an unchecked symbol to reusable."""
        import jcodemunch_mcp.investigator.reuse_audit as ra

        monkeypatch.setattr(ra, "_establish_liveness", lambda repo, cands, sp: 0)
        r = investigate(repo, "render a Modal dialog")
        assert r["verdict"] == REUSE_AVAILABLE
        assert r.get("dead_matches") in (None, []), (
            "nothing was established dead, so nothing may be reported dead"
        )


# --- Absence must be provable before it is asserted ------------------------ #


class TestAbsenceBlockers:
    @pytest.mark.parametrize(
        "blocker",
        [
            "index_changed",
            "coverage_is_incomplete",
            "index_truncation_meta",
            "_index_is_stale",
        ],
    )
    def test_any_blocker_downgrades_write_justified(
        self, repo, semantic_available, monkeypatch, blocker
    ):
        """Parametrized over the PROPERTY, not over the one path that reported
        it. Each of these is a state in which "we looked and it is not there"
        describes our reading rather than the repository."""
        clean = investigate(repo, UNRELATED_INTENT)
        assert clean["verdict"] == WRITE_JUSTIFIED, (
            "baseline must be the verdict this test downgrades"
        )

        import jcodemunch_mcp.investigator.reuse_audit as ra
        import jcodemunch_mcp.retrieval.verdict as v

        if blocker == "index_changed":
            monkeypatch.setattr(ra, "_index_was_rewritten", lambda index: True)
        elif blocker == "index_truncation_meta":
            monkeypatch.setattr(v, blocker, lambda cap: {"truncated": True})
        else:
            monkeypatch.setattr(v, blocker, lambda arg: True)

        r = investigate(repo, UNRELATED_INTENT)
        assert r["verdict"] == NOT_ESTABLISHED
        assert r["absence_unprovable"], (
            "the reason must be stated, not merely acted on"
        )
        assert "re-run" in r["recommended_next_action"].lower()

    def test_the_rewrite_probe_is_sampled_before_any_channel_runs(self, repo):
        """The ORDER is the property, so the order is what is asserted.

        Our own semantic read moves the .db mtime the probe compares: the
        embedding read opens a read-write connection, which runs PRAGMA and
        CREATE TABLE and touches the file. Sampled afterwards the probe reports
        True on every run in which the synonym channel was available, so
        ``write_justified`` -- the one verdict that REQUIRES that channel --
        could never be reached, blocked by a rewrite this module performed
        itself.

        ⚠ An end-to-end version of this test is VACUOUS with the
        ``semantic_available`` stand-in, because a stand-in that returns rows
        without opening the database never moves the mtime. It passed against
        the defect. The sibling test below closes that by moving the mtime for
        real; this one pins the order that makes moving it harmless.
        """
        import jcodemunch_mcp.investigator.reuse_audit as ra
        import jcodemunch_mcp.tools.search_symbols as ss

        events: list[str] = []
        real_probe = ra._index_was_rewritten
        real_search = ss.search_symbols

        def probe(index):
            events.append("probe")
            return real_probe(index)

        def search(*a, **kw):
            events.append("search")
            return real_search(*a, **kw)

        try:
            ra._index_was_rewritten = probe
            ss.search_symbols = search
            investigate(repo, UNRELATED_INTENT)
        finally:
            ra._index_was_rewritten = real_probe
            ss.search_symbols = real_search

        assert events.count("probe") == 1, events
        assert "search" in events, "no channel ran, so the order proves nothing"
        assert events.index("probe") < events.index("search"), events

    def test_a_channel_that_moves_the_db_mtime_does_not_block_the_verdict(
        self, repo, monkeypatch
    ):
        """The end-to-end half, with the mtime moved for real.

        The stand-in below does what the live embedding read does as a side
        effect -- it touches the database -- and the verdict must survive it.
        Reverting the sample point to after the scan turns this red.
        """
        import os

        import jcodemunch_mcp.investigator.reuse_audit as ra
        import jcodemunch_mcp.tools.search_symbols as ss

        real = ss.search_symbols
        db = next(Path(repo[1]).rglob("*.db"))

        def touches_the_db(*a, **kw):
            if kw.get("semantic_only"):
                os.utime(db, None)
                return {"results": []}
            return real(*a, **kw)

        monkeypatch.setattr(ra, "_semantic_state", lambda s, o, n: ("used", ""))
        monkeypatch.setattr(ss, "search_symbols", touches_the_db)
        r = investigate(repo, UNRELATED_INTENT)
        assert r["verdict"] == WRITE_JUSTIFIED
        assert "absence_unprovable" not in r
        assert "before the scan" in r["_meta"]["rewrite_probe"]

    def test_a_blocker_does_not_suppress_a_positive_finding(self, repo, monkeypatch):
        """An index that cannot prove ABSENCE can still show a positive hit.
        Downgrading a found symbol would be the guard eating the evidence."""
        import jcodemunch_mcp.investigator.reuse_audit as ra

        monkeypatch.setattr(ra, "_index_was_rewritten", lambda index: True)
        r = investigate(repo, "format an ISO date")
        assert r["verdict"] == REUSE_AVAILABLE
        assert r["absence_unprovable"]


# --- The intent reduces to a bag, not to the caller's phrasing ------------- #


class TestIntentTerms:
    def test_three_spellings_of_one_intent_reduce_to_the_same_bag(self):
        """If they differ, the caller's phrasing decides whether the search
        works, and the tool is a spelling quiz."""
        bags = [
            _intent_terms("renderModalDialog"),
            _intent_terms("render_modal_dialog"),
            _intent_terms("render a Modal dialog"),
        ]
        assert all(sorted(b) == sorted(bags[0]) for b in bags), bags
        assert sorted(bags[0]) == ["dialog", "modal", "render"]

    def test_stopwords_strip_the_wrapper_not_the_domain(self):
        assert _intent_terms(
            "I need a function that parses an ISO 8601 timestamp"
        ) == ["parses", "iso", "timestamp"]

    def test_identifier_forms_cover_the_spellings_a_writer_reaches_for(self):
        forms = _identifier_forms(["render", "modal", "dialog"])
        assert "RenderModalDialog" in forms
        assert "renderModalDialog" in forms
        assert "render_modal_dialog" in forms


class TestUnsearchableIntent:
    @pytest.mark.parametrize(
        "intent",
        ["", "   ", "we should do this", "I need a helper function", "make it"],
    )
    def test_an_intent_with_no_content_words_is_not_established(self, repo, intent):
        """The most expensive possible failure for a tool whose output licenses
        writing code: search nothing, find nothing, call it proof."""
        r = investigate(repo, intent)
        assert r["verdict"] == NOT_ESTABLISHED
        assert r["unresolved_obligations"] == ["intent_is_searchable"]

    def test_it_searches_nothing(self, repo, monkeypatch):
        import jcodemunch_mcp.investigator.reuse_audit as ra

        liveness_calls: list = []
        monkeypatch.setattr(
            ra,
            "_establish_liveness",
            lambda *a: liveness_calls.append(a) or 0,
        )
        r = investigate(repo, "I need a helper function")
        assert liveness_calls == []
        assert r["candidates"] == []
        assert r["_meta"].get("index_calls") in (None, 0)

    def test_it_says_what_would_fix_it(self, repo):
        r = investigate(repo, "I need a helper function")
        assert "ISO 8601" in r["recommended_next_action"]


# --- The optional structural channel --------------------------------------- #


class TestOptionalStructuralChannel:
    def test_an_unrequested_channel_is_excluded_from_the_verdict(
        self, repo, semantic_available
    ):
        """It is recorded UNESTABLISHED for the audit trail. If the verdict
        read it, ``write_justified`` would be unreachable without a signature,
        which is the difference between "could not" and "was not asked to"."""
        r = investigate(repo, UNRELATED_INTENT)
        assert _ob(r, "no_structural_twin")["status"] == UNESTABLISHED
        assert r["channels"]["structural"] == "not_requested"
        assert r["verdict"] == WRITE_JUSTIFIED
        assert "no_structural_twin" not in r["unresolved_obligations"]

    def test_it_is_still_shown_in_the_payload(self, repo, semantic_available):
        """Excluded from the verdict, never hidden from the reader."""
        r = investigate(repo, UNRELATED_INTENT)
        assert "no_structural_twin" in [o["obligation"] for o in r["obligations"]]

    def test_it_is_excluded_from_confidence_too(self, repo, semantic_available):
        """Confidence is the fraction of obligations SETTLED. Counting a
        channel nobody asked for would report a full sweep as 3 of 4."""
        r = investigate(repo, UNRELATED_INTENT)
        assert r["confidence"] == 1.0

    def test_a_supplied_signature_puts_the_channel_in_the_verdict(self, repo):
        r = investigate(
            repo,
            "render a Modal dialog",
            proposed_signature="def render_modal_dialog(title, body)",
        )
        assert r["channels"]["structural"] == "ok"
        assert _ob(r, "no_structural_twin")["status"] in (SATISFIED, REFUTED)


# --- The honesty rule, tested in isolation --------------------------------- #


class TestVerdictRule:
    def test_a_live_strong_match_outranks_everything(self):
        assert (
            _verdict(
                [Obligation("a", "?", UNESTABLISHED, channel=LEXICAL)],
                strong=["x"],
                partial=[],
                absence_blockers=["stale"],
            )
            == REUSE_AVAILABLE
        )

    def test_a_dead_only_refutation_is_not_a_reuse_instruction(self):
        assert (
            _verdict(
                [Obligation("no_name_twin", "?", REFUTED, channel=LEXICAL)],
                strong=[],
                partial=[],
                absence_blockers=[],
                dead_only_refutation=True,
            )
            == ADAPT_CANDIDATE
        )

    def test_a_dead_only_refutation_survives_an_absence_blocker(self):
        """Not an absence claim: we FOUND the thing. An index that cannot prove
        absence can still show a positive hit."""
        assert (
            _verdict(
                [Obligation("no_name_twin", "?", REFUTED, channel=LEXICAL)],
                strong=[],
                partial=[],
                absence_blockers=["stale"],
                dead_only_refutation=True,
            )
            == ADAPT_CANDIDATE
        )

    def test_a_live_refutation_is_still_reuse_available(self):
        assert (
            _verdict(
                [Obligation("no_name_twin", "?", REFUTED, channel=LEXICAL)],
                strong=[],
                partial=[],
                absence_blockers=[],
                dead_only_refutation=False,
            )
            == REUSE_AVAILABLE
        )

    def test_an_absence_blocker_outranks_a_clean_sweep(self):
        assert (
            _verdict(
                [
                    Obligation("a", "?", SATISFIED, channel=LEXICAL),
                    Obligation("s", "?", SATISFIED, channel=SEMANTIC),
                ],
                strong=[],
                partial=[],
                absence_blockers=["stale"],
            )
            == NOT_ESTABLISHED
        )

    def test_an_unestablished_lexical_obligation_never_yields_write_justified(self):
        assert (
            _verdict(
                [
                    Obligation("a", "?", UNESTABLISHED, channel=LEXICAL),
                    Obligation("s", "?", SATISFIED, channel=SEMANTIC),
                ],
                strong=[],
                partial=[],
                absence_blockers=[],
            )
            == NOT_ESTABLISHED
        )

    def test_an_unestablished_semantic_obligation_yields_lexical_only(self):
        """The distinction ``lexical_only`` exists to protect. An unanswered
        LEXICAL question is a gap in work we could have done; an unanswered
        SEMANTIC one is a gap in evidence that may not exist here at all.
        Collapsing them would let a failed sweep read as a clean one."""
        assert (
            _verdict(
                [
                    Obligation("a", "?", SATISFIED, channel=LEXICAL),
                    Obligation("s", "?", UNESTABLISHED, channel=SEMANTIC),
                ],
                strong=[],
                partial=[],
                absence_blockers=[],
            )
            == LEXICAL_ONLY
        )

    def test_every_channel_settled_yields_write_justified(self):
        assert (
            _verdict(
                [
                    Obligation("a", "?", SATISFIED, channel=LEXICAL),
                    Obligation("s", "?", SATISFIED, channel=SEMANTIC),
                    Obligation("t", "?", SATISFIED, channel=STRUCTURAL),
                ],
                strong=[],
                partial=[],
                absence_blockers=[],
            )
            == WRITE_JUSTIFIED
        )

    def test_a_partial_match_recommends_rather_than_refuses(self):
        assert (
            _verdict(
                [
                    Obligation("a", "?", SATISFIED, channel=LEXICAL),
                    Obligation("s", "?", SATISFIED, channel=SEMANTIC),
                ],
                strong=[],
                partial=["x"],
                absence_blockers=[],
            )
            == ADAPT_CANDIDATE
        )

    def test_lexical_only_does_not_become_a_back_door_to_write_justified(self):
        """A partial match plus a dark semantic channel must not report the
        stronger claim by way of the weaker one."""
        assert (
            _verdict(
                [
                    Obligation("a", "?", SATISFIED, channel=LEXICAL),
                    Obligation("s", "?", UNESTABLISHED, channel=SEMANTIC),
                ],
                strong=[],
                partial=["x"],
                absence_blockers=[],
            )
            != WRITE_JUSTIFIED
        )


# --- Charter --------------------------------------------------------------- #


class TestCharter:
    @pytest.mark.parametrize(
        "intent",
        ["format an ISO date", "render a Modal dialog", UNRELATED_INTENT],
    )
    def test_every_response_declares_read_only(self, repo, intent):
        assert investigate(repo, intent)["_meta"]["charter"] == "read_only"

    def test_the_unsearchable_early_return_declares_it_too(self, repo):
        """The one exit that returns before any obligation runs is the one most
        likely to drop the field."""
        r = investigate(repo, "I need a helper function")
        assert r["_meta"]["charter"] == "read_only"

    def test_the_fixture_tree_is_unchanged_by_an_investigation(self, repo):
        """No test may observe a write. Asserted against the bytes, not against
        the charter string that claims it."""
        root = Path(repo[1]).parent

        def snapshot() -> dict:
            return {
                p: p.read_bytes()
                for p in root.rglob("*")
                if p.is_file() and ".index" not in p.parts
            }

        before = snapshot()
        assert before, "the fixture tree must be non-empty or this is vacuous"
        investigate(repo, "render a Modal dialog")
        investigate(repo, UNRELATED_INTENT)
        assert snapshot() == before


# --- Argument validation --------------------------------------------------- #


class TestArgumentValidation:
    def test_an_inverted_threshold_pair_is_refused(self, repo):
        r = investigate(repo, "anything", strong_match=0.2, adapt_floor=0.9)
        assert "error" in r

    def test_max_candidates_must_be_positive(self, repo):
        r = investigate(repo, "anything", max_candidates=0)
        assert "error" in r
