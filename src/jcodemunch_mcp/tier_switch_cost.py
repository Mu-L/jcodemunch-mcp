"""Is a mid-session tool-list change worth what it costs?

A tier switch is not free and is not merely "fewer tokens". ``tools`` is
serialised AHEAD of system and messages, so changing the exposed tool list
invalidates the cached prefix -- the schema block AND every accumulated turn
behind it. The new block must then be cache-WRITTEN before it can be read
cheaply again.

⚠⚠ **The intuition inverts on exactly the case that applies here.** With no
cache, dropping 1,810 tokens of schema saves 1,810 tokens on every request and
pays back immediately. With the block cached -- and this repository measured
**86% of baseline input cached** (``benchmarks/codex_surface/README.md``) -- the
recurring saving is a tenth of that while the one-time write is charged at
full rate or above. ``full`` -> ``standard`` drops 6.7% of the payload and needs
**174 requests** to break even, before any history is counted.

⚠ ``CACHE_*_MULTIPLIER`` are PUBLISHED rates, not measurements: cache read is
0.1x base input price and a 5-minute cache write is 1.25x. The 1-hour write is
2.0x, which only makes a bad switch worse -- so pricing with the cheaper write
is the conservative direction, the same rule the savings multipliers follow.

⚠ Schema weights are never hardcoded here. They are passed in by the caller,
which reads them live from the built tool list, so this module cannot drift
away from the surface it prices.
"""
from __future__ import annotations

CACHE_READ_MULTIPLIER = 0.1
CACHE_WRITE_MULTIPLIER = 1.25

# ⚠ A CHOSEN threshold, not a measurement: how many further requests a switch
# is allowed to take to repay itself. It is deliberately generous -- the
# transition this exists to refuse needs 174 requests with an empty history and
# 864 with 100k of it, so no plausible horizon rescues it and the choice does
# not decide the outcome. Widening is never judged by it (see `classify`).
DEFAULT_HORIZON_REQUESTS = 100


def breakeven_requests(
    src_tokens: int,
    dst_tokens: int,
    *,
    history_tokens: int = 0,
    write: float = CACHE_WRITE_MULTIPLIER,
    read: float = CACHE_READ_MULTIPLIER,
) -> float | None:
    """Requests until a switch repays its own cache invalidation.

    ``None`` means it never repays in tokens -- the recurring delta is zero or
    negative, i.e. the switch widens the surface or changes nothing. That is a
    capability purchase, not a defect, and `classify` treats it as one.

    ``history_tokens`` is what has already accumulated behind the tool block at
    the moment of the switch; it is invalidated too, so switching late costs
    more than switching early.
    """
    recurring = (src_tokens - dst_tokens) * read
    if recurring <= 0:
        return None
    return ((dst_tokens + max(0, history_tokens)) * write) / recurring


def classify(
    src_tokens: int,
    dst_tokens: int,
    *,
    history_tokens: int = 0,
    horizon: int = DEFAULT_HORIZON_REQUESTS,
) -> tuple[str, float | None]:
    """Name what a switch is: ``widening`` / ``pays`` / ``does_not_pay`` / ``noop``.

    ⚠⚠ ``widening`` is ALLOWED and must stay allowed. Escalating to a larger
    surface after a capability-gated failure buys a capability, and refusing it
    to save tokens would trade a correct answer for a cheap one. Only a
    NARROWING that cannot repay its own invalidation is a defect, because it
    claims to save and does the opposite for the whole life of the session.
    """
    if src_tokens == dst_tokens:
        return ("noop", None)
    if dst_tokens > src_tokens:
        return ("widening", None)
    be = breakeven_requests(src_tokens, dst_tokens, history_tokens=history_tokens)
    if be is None:
        return ("widening", None)
    return ("pays" if be <= horizon else "does_not_pay", be)
