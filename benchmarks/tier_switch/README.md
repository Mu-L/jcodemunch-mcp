# Pricing a mid-session tier switch

Regenerate: `PYTHONPATH=src python benchmarks/tier_switch/price_tier_switch.py [--json]`
Artifact: `results.json`, rewritten by the same command.

⚠ **Never hand-type a figure from here.** Schema weights are read live from
`server._build_tools_list`, so they move with the catalog; the table below is a
snapshot for reading, and `results.json` is what a consumer quotes.

## What is being priced

A tier switch changes the published tool list. `tools` is serialised **ahead of**
system and messages, so the change invalidates the cached prefix — the schema
block **and every accumulated turn behind it** — and the new block must be
cache-*written* before it reads cheaply again.

Rates are **published** (Anthropic prompt caching), as multiples of base input
price: cache read `0.1x`, 5-minute cache write `1.25x`, 1-hour write `2.0x`.
Pricing with the cheaper write is the conservative direction, the same rule the
receipt's savings multipliers follow.

## The result

| tier | tools | schema tokens |
|---|---:|---:|
| core | 20 | 6,824 |
| standard | 82 | 25,133 |
| full | 91 | 26,943 |

| switch | one-time | saved/req | break-even | verdict |
|---|---:|---:|---:|---|
| full → core | 8,530 | 2,012 | **4 reqs** | pays |
| full → standard | 31,416 | 181 | **174 reqs** | does_not_pay |
| standard → core | 8,530 | 1,831 | 5 reqs | pays |
| core → full | 33,679 | −2,012 | never | widening |
| standard → full | 33,679 | −181 | never | widening |

Including the history the switch also invalidates:

| history at switch | full → core | full → standard |
|---:|---:|---:|
| 0 | 4 req | 174 req |
| 25,000 | 20 req | 346 req |
| 100,000 | 66 req | **864 req** |

## Why it was invisible

⚠⚠ **The intuition inverts on exactly the case that applies.** With no cache,
`full → standard` saves 1,810 tokens on *every* request at no one-time cost and
pays back immediately. It is wrong only because the block is **cached**, which
`benchmarks/codex_surface/README.md` measured at **86% of baseline input**.
"Fewer tokens is better" holds right up until the block is stable — which is
precisely when it stops holding.

⚠ This extends the codex_surface finding rather than repeating it. That one says
`standard` is **not a lever** (9 of 91 tools, 6.7% of the payload). The addition
here is that as a *transition* it is not a weak lever but a **negative** one, for
longer than any session lasts.

## What shipped with it

`tier_switch_cost.classify` refuses a **narrowing** that cannot repay itself,
at both switch sites (`set_tool_tier`, and `_apply_model_announcement` behind
`plan_turn(model=)` / `announce_model`). A **widening** is never refused —
escalating after a capability-gated failure buys a capability, and trading a
correct answer for a cheap one is the worse error.

⚠ `standard` remains a perfectly good **startup** `tool_profile`. There is no
switch to pay for at startup. The refusal names that route.
