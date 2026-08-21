# Route binary pilot — H3 is REFUTED

One predicate, one run, nothing fitted. Registered in `PROTOCOL.md` and in
`predicate.py`, both committed before a single case existed — see `git log` for
this directory.

## The numbers

60 cases, balanced 30/30, across `expressjs/express`, `fastapi/fastapi` and
`gin-gonic/gin` at the SHAs published in `benchmarks/tasks.json`.

| | accuracy | vs 50% floor | Wilson 95% | p vs chance |
|---|---|---|---|---|
| full vocabulary | **53.3%** | +3.3 | [40.9, 65.4] | **0.699** |
| own name ablated | **50.0%** | 0.0 | [37.7, 62.3] | **1.000** |

**Indistinguishable from a coin.** The confidence interval spans the floor in
both conditions, and ablating each target's own name parts takes what little
there was straight back to 50.0%.

⚠ Leakage existed and bought nothing: 12 of 30 class-S tasks matched their own
target's name, and the full-vocabulary result is still inside chance.

## The mechanism, which is the part worth keeping

Per class:

| | gold `search_symbols` | gold `search_text` |
|---|---|---|
| accuracy | **100%** | **6.7%** |

**The predicate is a constant classifier wearing a probe's clothing.** It
answered `search_symbols` on **58 of 60** tasks — 30/30 of class S and **28/30 of
class T**. It scores 100% on one class for the same reason it scores 6.7% on the
other: it never says anything else.

Why: in a real repository the symbol vocabulary absorbs ordinary English.

| repo | symbols | matchable name parts |
|---|---|---|
| expressjs/express | 200 | 164 |
| gin-gonic/gin | 1,179 | 1,347 |
| fastapi/fastapi | 6,841 | **4,303** |

Of sixteen common English words tested against fastapi, **fourteen are symbol
name parts**: `message`, `from`, `path`, `string`, `file`, `text`, `status`,
`value`, `error`, `name`, `body`, `type`, `data`, `request`. A predicate that
asks "does any task token match a symbol name" fires on nearly any English
sentence.

## What this refutes, precisely

**H3 as specified.** It does not refute the whole outside-the-string class — but
the mechanism generalises to any probe keyed on *vocabulary membership*, because
membership is what the size of a real index destroys.

⚠⚠ **The generalisable finding is that COVERAGE WAS NEVER THE PROPERTY THAT
MATTERED, and this pilot exists because we thought it was.**

| hypothesis | fires on | fails because |
|---|---|---|
| H1 identifier shape | ~15% | decides too few cases |
| H2 imperative verb | ~5% | decides too few cases |
| H3 symbol-vocabulary probe | **~97%** | decides them all the same way |

H3 was argued for *on the grounds that* its coverage was 100% by construction.
That was **necessary and not sufficient** — the same shape as moratorium
conditions 1 and 2 being met and not clearing the freeze. The property all three
lack is **separation**: a predicate must fire differently on the two classes, and
firing often is not firing differently.

## The decision this was built to make

`PROTOCOL.md` registered the asymmetry in advance: *a negative is decisive and
kills the corpus project.*

**So: do not build the full repo-grounded corpus for this hypothesis family.**
The pilot cost an afternoon and three clones. Building the real corpus — cases
bound to real repositories, tasks generated against them, labels assigned by
someone who can see them — would have cost a project and reached the same wall,
because the wall is not the corpus. It is that vocabulary membership does not
separate these two classes in any repository large enough to matter.

## What is NOT ruled out, and must not be run on this corpus

A probe keyed on **retrieval outcome** rather than vocabulary membership: does
`search_symbols` actually outrank `search_text` for this query against this
index? That is a different quantity — a comparison of two scores rather than a
set-membership test — and the size of the vocabulary does not trivially defeat
it.

⚠⚠ **That is H4, and running it against these 60 cases would be a fitting pass
wearing an experiment's clothes.** The corpus is spent. A new hypothesis needs
new cases, and the same registration discipline: predicate committed first, one
run, the stopping rule chosen before the result.
