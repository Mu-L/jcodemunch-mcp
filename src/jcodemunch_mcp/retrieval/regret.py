"""Retrieval-regret extraction over the ranking_events ledger.

We already collect rich retrieval telemetry but feed it to a single consumer
(``WeightTuner``, which nudges two ranking knobs). The same ledger carries a
louder, unread signal: **when retrieval failed and the agent had to re-ask.**
This module mines that regret.

Pure read over the existing ``ranking_events`` ledger via
``token_tracker.ranking_db_query`` — no new tables, no writes. The output is a
list of regret *clusters*; correction synthesis (``tools/suggest_corrections``)
turns clusters into suggested (never applied) config patches.

v1.108.290 adds an ``inflation`` block beside the clusters: how many calls one
information need actually cost, against the one call it should have. Clusters
name WHICH queries went wrong; inflation says what the wrongness cost in total.
⚠ Its basis is CALLS -- the ledger has no token column.

Ledger tuple layout (matches the SELECT in ``token_tracker.ranking_db_query``):
    0 ts            5 returned_ids (JSON)   10 identity_hit
    1 repo          6 top1_score            11 repo_is_stale
    2 tool          7 top2_score
    3 query_hash    8 confidence
    4 query         9 semantic_used
"""

from __future__ import annotations

import json as _json
from collections import defaultdict
from typing import Any, Optional

from ..storage import token_tracker as _tt
from .. import config as _config
from .ledger_trust import (
    identity_label_is_trustworthy as _identity_label_is_trustworthy,
    semantic_label_is_trustworthy as _semantic_label_is_trustworthy,
)

# Column indices into a ranking_events row tuple.
_TS, _REPO, _TOOL, _QH, _QUERY, _RETURNED = 0, 1, 2, 3, 4, 5
_TOP1, _TOP2, _CONF, _SEM, _IDHIT, _STALE = 6, 7, 8, 9, 10, 11

# --- Thresholds (starting points; conservative to avoid noisy suggestions) --- #
DEFAULT_WINDOW_DAYS = 30
REQUERY_LIFETIME = 5          # same query_hash this many times => churn
REQUERY_HIGH = 8             # ... this many => high severity
LOW_CONF = 0.30              # confidence below this on a non-empty result
LOW_CONF_RECUR = 2          # low-confidence events for one query to cluster
THIN_TOP1_FLOOR = 0.10      # top1 below this with <=1 result == thin
AMBIGUOUS_GAP = 0.05        # top1 - top2 below this == couldn't disambiguate
AMBIGUOUS_RECUR = 2
STALE_RATE = 0.20           # >20% of events stale-at-query == freshness problem
STALE_MIN_EVENTS = 5        # ... but only judge the rate over enough events
VOCAB_CONF_FLOOR = 0.30     # identity miss rescued by semantic with >= this conf
VOCAB_RECUR = 2
MAX_EXAMPLES = 3            # example queries carried per cluster
MAX_CLUSTERS_PER_SIGNAL = 5
INFLATION_MIN_NEEDS = 5     # fewer information needs than this => ratio is noise
INFLATION_WORST = 3         # worst-offending needs carried in the block


def _sev(count: int, hi: int, med: int) -> str:
    if count >= hi:
        return "high"
    if count >= med:
        return "medium"
    return "low"


def _decode_ids(raw: Any) -> list:
    if not raw:
        return []
    try:
        v = _json.loads(raw)
        return v if isinstance(v, list) else []
    except (ValueError, TypeError):
        return []


def _examples(rows: list[tuple]) -> list[str]:
    """Distinct example query strings for a cluster, capped."""
    seen: list[str] = []
    for r in rows:
        q = r[_QUERY]
        if q and q not in seen:
            seen.append(q)
        if len(seen) >= MAX_EXAMPLES:
            break
    return seen


def _by_query_hash(events: list[tuple]) -> "dict[str, list[tuple]]":
    groups: dict[str, list[tuple]] = defaultdict(list)
    for e in events:
        groups[e[_QH]].append(e)
    return groups


def _cluster(signal: str, severity: str, rows: list[tuple], **evidence) -> dict:
    tools = sorted({r[_TOOL] for r in rows if r[_TOOL]})
    return {
        "signal": signal,
        "severity": severity,
        "event_count": len(rows),
        "tools": tools,
        "query_examples": _examples(rows),
        "evidence": evidence,
    }


# --- Per-signal detectors --------------------------------------------------- #

def _detect_requery_churn(by_qh: "dict[str, list[tuple]]") -> list[dict]:
    out = []
    for qh, rows in by_qh.items():
        if len(rows) >= REQUERY_LIFETIME:
            out.append(_cluster(
                "requery_churn", _sev(len(rows), REQUERY_HIGH, REQUERY_LIFETIME),
                rows, query_hash=qh, repeats=len(rows),
            ))
    out.sort(key=lambda c: -c["event_count"])
    return out[:MAX_CLUSTERS_PER_SIGNAL]


def _detect_low_confidence(by_qh: "dict[str, list[tuple]]") -> list[dict]:
    out = []
    for qh, rows in by_qh.items():
        hits = [r for r in rows
                if r[_CONF] is not None and r[_CONF] < LOW_CONF and _decode_ids(r[_RETURNED])]
        if len(hits) >= LOW_CONF_RECUR:
            avg = sum(r[_CONF] for r in hits) / len(hits)
            out.append(_cluster(
                "low_confidence", _sev(len(hits), LOW_CONF_RECUR * 3, LOW_CONF_RECUR),
                hits, query_hash=qh, avg_confidence=round(avg, 3),
            ))
    out.sort(key=lambda c: (-c["event_count"], c["evidence"]["avg_confidence"]))
    return out[:MAX_CLUSTERS_PER_SIGNAL]


def _detect_thin_result(by_qh: "dict[str, list[tuple]]") -> list[dict]:
    out = []
    for qh, rows in by_qh.items():
        hits = []
        for r in rows:
            ids = _decode_ids(r[_RETURNED])
            top1 = r[_TOP1]
            if not ids:
                hits.append(r)
                continue
            if len(ids) > 1:
                continue
            # v1.108.187. A single result with no recorded `top1_score` counts as
            # thin, which reads a MISSING measurement as a weak one. That is fine
            # where the score was genuinely absent, but pre-v1.108.187 fusion rows
            # from get_ranked_context recorded NO features at all, so those were
            # clustered as thin on the strength of a default. Only those rows are
            # skipped; every other producer's behaviour is unchanged.
            if not _identity_label_is_trustworthy(r):
                continue
            if top1 is None or top1 < THIN_TOP1_FLOOR:
                hits.append(r)
        if len(hits) >= 2:
            out.append(_cluster(
                "thin_result", _sev(len(hits), 5, 2),
                hits, query_hash=qh, empty_or_weak=len(hits),
            ))
    out.sort(key=lambda c: -c["event_count"])
    return out[:MAX_CLUSTERS_PER_SIGNAL]


def _detect_ambiguous_top(by_qh: "dict[str, list[tuple]]") -> list[dict]:
    out = []
    for qh, rows in by_qh.items():
        hits = [r for r in rows
                if r[_TOP1] is not None and r[_TOP2] is not None
                and (r[_TOP1] - r[_TOP2]) < AMBIGUOUS_GAP]
        if len(hits) >= AMBIGUOUS_RECUR:
            out.append(_cluster(
                "ambiguous_top", _sev(len(hits), AMBIGUOUS_RECUR * 3, AMBIGUOUS_RECUR),
                hits, query_hash=qh, min_gap=round(
                    min(r[_TOP1] - r[_TOP2] for r in hits), 4),
            ))
    out.sort(key=lambda c: -c["event_count"])
    return out[:MAX_CLUSTERS_PER_SIGNAL]


def _detect_stale_at_query(events: list[tuple]) -> list[dict]:
    if len(events) < STALE_MIN_EVENTS:
        return []
    stale = [e for e in events if e[_STALE]]
    rate = len(stale) / len(events)
    if rate > STALE_RATE:
        return [_cluster(
            "stale_at_query",
            "high" if rate > STALE_RATE * 2 else "medium",
            stale, stale_rate=round(rate, 3), stale_events=len(stale),
            total_events=len(events),
        )]
    return []


def _detect_vocabulary_gap(by_qh: "dict[str, list[tuple]]") -> list[dict]:
    """Identity miss rescued by semantic search => the agent's term doesn't
    match a symbol name but means one. The strongest novelty signal.

    ⚠ v1.108.186. This signal is the conjunction ``not identity_hit and
    semantic_used``, which made every pre-fix ``get_ranked_context_fusion`` row a
    textbook match: that exit hardcoded ``semantic_used=1`` and passed no ledger
    features at all, so ``identity_hit`` defaulted to 0 while the identity channel
    was in fact one of the three it built. A confident fusion call therefore
    reported "the agent's term doesn't match a symbol name" on a call where
    identity matching ran, and ``suggest_corrections`` turns these clusters into
    config patches shown to the user. Rows whose semantic label is not evidence
    cannot support this signal, so they are dropped from it.

    ⚠⚠ v1.108.272 (#440). The same conjunction was satisfied by construction on the
    semantic ``search_symbols`` exit, and that one the v1.108.186 rule does NOT
    refuse. That exit passed ``semantic_used=True`` literally while its ledger input
    carried no identity key, so both halves held on every such row by defect rather
    than by measurement. The floors keep it from firing on a single row
    (``VOCAB_CONF_FLOOR``, ``VOCAB_RECUR``), but for any repeated query above the
    confidence floor the signal was reporting a vocabulary gap it had not tested,
    and ``suggest_corrections`` turned those clusters into config patches shown to
    the user.

    Producers now record a measured ``identity_hit`` at both non-fusion exits, so
    new rows test the condition for real. ⚠ Rows written before v1.108.272 are NOT
    separable — see ``ledger_trust.identity_label_is_trustworthy`` — so this signal
    stays contaminated for those until the recency window ages them out. Reported by
    @rknighton.
    """
    out = []
    for qh, rows in by_qh.items():
        # ⚠ v1.108.187 checked `identity_label_is_trustworthy` here too and it was
        # UNREACHABLE: this signal requires `r[_SEM]`, and a
        # get_ranked_context_fusion row with semantic_used=1 is already refused by
        # the v1.108.186 semantic rule. An unreachable guard reads like protection
        # and is not, so it is not here. The featureless rows are excluded from the
        # signals that CAN see them (thin_result) and disclosed on the result.
        hits = [r for r in rows
                if _semantic_label_is_trustworthy(r)
                and not r[_IDHIT] and r[_SEM]
                and r[_CONF] is not None and r[_CONF] >= VOCAB_CONF_FLOOR]
        if len(hits) >= VOCAB_RECUR:
            out.append(_cluster(
                "vocabulary_gap", _sev(len(hits), VOCAB_RECUR * 3, VOCAB_RECUR),
                hits, query_hash=qh, identity_misses=len(hits),
            ))
    out.sort(key=lambda c: -c["event_count"])
    return out[:MAX_CLUSTERS_PER_SIGNAL]


# --------------------------------------------------------------------------- #
# Retrieval inflation (v1.108.290)
# --------------------------------------------------------------------------- #
#
# arXiv:2608.13571 defines token inflation as the ratio of true workflow cost to
# single-call cost -- the gap between what one call is priced at and what the
# workflow actually spent once the failures are counted. Retrieval has the same
# gap and we have never charged ourselves for it: `_meta.tokens_saved` reports
# the saving on the call that worked and says nothing about the two before it.
#
# ⚠⚠ **THE BASIS IS CALLS, NOT TOKENS, AND THE FIELD SAYS SO.** `ranking_events`
# carries no token column -- see the schema in `token_tracker` -- so a ratio
# named after tokens would be measuring one thing and named for another. The
# paper's ratio is cost-agnostic; ours is honest about which cost it counted.
# Renaming this to tokens requires a token column, not a better adjective.
#
# ⚠ An information NEED is `(session_uid, query_hash)`, not `query_hash` alone.
# The same query asked in two sessions a week apart is two needs; collapsing
# them would charge us for the agent having a second conversation.
#
# ⚠⚠ A row with no `session_uid` is UNKNOWN and is EXCLUDED, never folded into a
# synthetic session. #456 added the column by ALTER, so pre-#456 rows carry
# NULL, and treating NULL as one shared session would fuse every historical
# query in the ledger into a single need with a spectacular fake ratio.
#
# ⚠⚠ **`repeats_after_index_change` is DISCLOSED AND NOT SUBTRACTED.** A re-ask
# after the index moved under the query is arguably a different question, so it
# is arguably not waste -- but subtracting it lowers our own inflation number,
# and a self-flattering adjustment applied silently is the one direction this
# metric must not drift. Report both and let the reader adjust.


def _detect_inflation(rows: "Optional[list[tuple]]") -> dict:
    """Retrieval inflation over `(session_uid, query_hash)` information needs.

    ``rows`` are ``token_tracker.ranking_db_inflation_rows`` output: ``None``
    means the ledger could not answer, which is NOT the same as no inflation.
    """
    _SID, _QHASH, _TL, _Q, _TIME, _STL = 0, 1, 2, 3, 4, 5

    if rows is None:
        return {
            "basis": "calls",
            "measurable": False,
            "reason": "ledger_has_no_session_column",
            "hint": (
                "This telemetry.db predates the session correlation keys (#456). "
                "Inflation needs them to tell a re-ask apart from a later "
                "session asking the same thing; events recorded from now on "
                "will carry them."
            ),
        }

    without_session = sum(1 for r in rows if not r[_SID])
    needs: "dict[tuple, list[tuple]]" = defaultdict(list)
    for r in rows:
        if r[_SID]:
            needs[(r[_SID], r[_QHASH])].append(r)

    out: dict = {"basis": "calls"}
    if without_session:
        out["events_without_session"] = without_session

    if len(needs) < INFLATION_MIN_NEEDS:
        out["measurable"] = False
        out["reason"] = "too_few_needs"
        out["needs"] = len(needs)
        out["hint"] = (
            f"A ratio over {len(needs)} information need(s) is noise; "
            f"{INFLATION_MIN_NEEDS} is the floor. Widen the window with "
            f"all_time, or run more searches."
        )
        return out

    calls = sum(len(v) for v in needs.values())
    changed = 0
    worst: list[dict] = []
    for (_sid, _qh), evs in needs.items():
        evs = sorted(evs, key=lambda e: e[_TIME])
        for prev, cur in zip(evs, evs[1:]):
            if prev[_STL] != cur[_STL]:
                changed += 1
        if len(evs) > 1:
            worst.append({
                "query": evs[0][_Q],
                "tool": evs[0][_TL],
                "calls": len(evs),
                "excess_calls": len(evs) - 1,
            })
    worst.sort(key=lambda w: -w["calls"])

    out.update({
        "measurable": True,
        "needs": len(needs),
        "calls": calls,
        "ratio": round(calls / len(needs), 3),
        "excess_calls": calls - len(needs),
        "repeats_after_index_change": changed,
        "worst": worst[:INFLATION_WORST],
    })
    return out


def analyze_regret(
    repo: str,
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    storage_path: Optional[str] = None,
    all_time: bool = False,
) -> dict:
    """Mine the ranking_events ledger for retrieval regret for ``repo``.

    Returns a dict with ``telemetry_present``, ``events_analyzed``,
    ``clusters`` (a flat list of regret clusters across all six signals,
    severity-ranked) and ``inflation`` (the calls-per-information-need ratio;
    see ``_detect_inflation``). Honest no-telemetry / no-events shapes are
    returned rather than fabricated regret. Pure read — never writes.
    """
    telemetry_on = bool(_config.get("perf_telemetry_enabled", False))
    window = None if all_time else float(window_days) * 86_400
    events = _tt.ranking_db_query(
        base_path=storage_path, repo=repo, window_seconds=window, limit=10_000,
    )

    base = {
        "repo": repo,
        "telemetry_present": telemetry_on,
        "window_days": None if all_time else window_days,
        "events_analyzed": len(events),
    }
    if not events:
        base["clusters"] = []
        base["inflation"] = {
            "basis": "calls", "measurable": False, "reason": "no_events",
        }
        base["hint"] = (
            "No ranking telemetry for this repo. Enable it with "
            "`perf_telemetry_enabled: true` (or JCODEMUNCH_PERF_TELEMETRY=1) and "
            "run some searches; regret analysis needs a ledger to read."
            if not telemetry_on else
            "Telemetry is on but no ranking events recorded for this repo yet in "
            "the window. Run some searches, or widen the window with all_time."
        )
        return base

    # v1.108.186. Disclosed rather than silently dropped: the vocabulary_gap signal
    # ignores these rows, and a reader comparing `events_analyzed` against the
    # clusters found deserves to know some rows could not support one of the six.
    _untrusted = sum(1 for r in events if not _semantic_label_is_trustworthy(r))
    if _untrusted:
        base["events_semantic_label_unknown"] = _untrusted
    # v1.108.187. Rows that recorded no ledger features at all: three of the six
    # signals read those columns, so say how many rows could not support them.
    _featureless = sum(1 for r in events if not _identity_label_is_trustworthy(r))
    if _featureless:
        base["events_without_ledger_features"] = _featureless

    by_qh = _by_query_hash(events)
    clusters: list[dict] = []
    clusters += _detect_requery_churn(by_qh)
    clusters += _detect_low_confidence(by_qh)
    clusters += _detect_thin_result(by_qh)
    clusters += _detect_ambiguous_top(by_qh)
    clusters += _detect_stale_at_query(events)
    clusters += _detect_vocabulary_gap(by_qh)

    _rank = {"high": 0, "medium": 1, "low": 2}
    clusters.sort(key=lambda c: (_rank.get(c["severity"], 9), -c["event_count"]))
    base["clusters"] = clusters
    # Read over the same window the clusters were read over, so the two halves
    # of the response describe the same slice of the ledger.
    base["inflation"] = _detect_inflation(
        _tt.ranking_db_inflation_rows(
            base_path=storage_path, repo=repo, window_seconds=window, limit=10_000,
        )
    )
    return base
