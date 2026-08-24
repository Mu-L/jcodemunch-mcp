"""Read-only investigations: bounded evidence gathering toward a stated claim.

An investigation differs from a tool call in what it returns. A tool answers the
question it was asked. An investigation decides which questions must be answered
before a claim is justified, asks them in cost order, and reports which ones it
could not settle.

That difference is the whole point. The 2026-03-18 dead-code A/B measured an
agent that had every tool it needed and still got export-level liveness wrong
64.1% of the time, because it stopped after establishing that a FILE was
imported and never asked whether the EXPORT was used. The capability was
present; the obligation was never raised. Re-measured against 1.108.213 on
2026-08-02, the tools discriminate perfectly (``check_references`` returns
``is_referenced: false`` for a dead export in a live file) and no aggregate
caller asks.

Investigations exist to raise the obligation whether or not the caller thought
of it, and to refuse a conclusion when one goes unanswered.

The charter is unchanged: nothing here writes, edits, or executes target code.
"""

from .deletion_safety import (  # noqa: F401
    DYNAMIC,
    NOT_ESTABLISHED,
    Obligation,
    REFUTED,
    SAFE,
    SATISFIED,
    STATIC,
    STATIC_CLEAR,
    UNESTABLISHED,
    UNSAFE,
    investigate_deletion_safety,
)
from .reuse_audit import (  # noqa: F401
    ADAPT_CANDIDATE,
    Candidate,
    LEXICAL,
    LEXICAL_ONLY,
    REUSE_AVAILABLE,
    SEMANTIC,
    STRUCTURAL,
    WRITE_JUSTIFIED,
    investigate_reuse_before_write,
)
from .retrieval_counterfactual import (  # noqa: F401
    CATALOG_ABSENT,
    EMPTY_QUERY,
    GATES,
    NO_LEXICAL_OVERLAP,
    RANKED_BELOW_CUTOFF,
    RETURNED,
    RULE_PREEMPTED,
    explain_misses,
    explain_route,
)

__all__ = [
    "Obligation",
    "SATISFIED",
    "REFUTED",
    "UNESTABLISHED",
    "STATIC",
    "DYNAMIC",
    "SAFE",
    "STATIC_CLEAR",
    "UNSAFE",
    "NOT_ESTABLISHED",
    "investigate_deletion_safety",
    "GATES",
    "RETURNED",
    "CATALOG_ABSENT",
    "EMPTY_QUERY",
    "RULE_PREEMPTED",
    "NO_LEXICAL_OVERLAP",
    "RANKED_BELOW_CUTOFF",
    "explain_route",
    "explain_misses",
    "Candidate",
    "LEXICAL",
    "SEMANTIC",
    "STRUCTURAL",
    "REUSE_AVAILABLE",
    "ADAPT_CANDIDATE",
    "WRITE_JUSTIFIED",
    "LEXICAL_ONLY",
    "investigate_reuse_before_write",
]
