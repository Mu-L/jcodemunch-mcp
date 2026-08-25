# Racket extraction fidelity

This compares what jCodeMunch's index says about a Racket file against what
Racket itself says the file defines. The point is not to produce a score. It is
to separate two very different kinds of difference:

- **We missed something.** An agent falls back to reading the file. Annoying,
  survivable.
- **We said something false.** An agent believes it and acts on it.

Those deserve different treatment, so they get different bars.

## What each number means

| Bucket | Meaning | Required |
|---|---|---|
| `extra` | A name in our index that Racket says does not exist. An agent would trust it and chase something that is not there. | **0** |
| `wrong_span` | We have the name, but the line range we report does not contain the definition — so "show me the source of X" returns the wrong code. | **0** |
| `missing` | A definition a human wrote in the source that our index does not contain. You search for it, you do not find it. | reported |
| `callable_unknowable` | We labelled it a constant, but it is a function you can call. | reported |
| `generated_only` | A name a macro introduced. No static parser can reach it. | reported |
| `export_only` | Reachable under a different name than we indexed, because of `rename-out` or `struct-out`. | reported |

`callable_unknowable` is reported rather than required to be zero because it
cannot be fixed by parsing more carefully. `racket/function.rkt` writes
`(define curry (make-curry #f))` — `curry` is callable, and nothing in the
source text says so. Knowing would take running the program.

`missing` is reported rather than required to be zero for the same reason: the
bulk of it is names created by invoking a macro, which are not in the file's
text at all.

## Reading the result

The corpus average is the least useful view. On the committed run — 3,526
definitions across 211 files — 485 were not found, but **152 of the 211 files
have nothing missing at all**, and the 10 worst files account for 311 of the
485. The gap sits in a handful of heavily macro-driven files rather than
spreading evenly, so "86.2%" understates how most files behave.

## The oracle

`oracle.rkt` uses **Racket's own expander**. It `expand`s each module and walks
the fully-expanded form, so it sees every binding the module really defines —
including the ones no static parser can reach, because a macro introduced them.

`syntax-original?` is what makes the comparison meaningful: it separates names a
**human typed** from names a **macro introduced**. Only the first group is
something a static parser could reasonably have found, so only the first group
belongs in a coverage number. Counting macro output as a miss would make the gap
look several times worse than it is.

`module->exports` answers the second, different question — what a *consumer*
can call, post-`rename-out`. On a file exporting
`(rename-out [greet say-hello])` it returns `say-hello`, not `greet`, which is
how the rename gap gets measured instead of estimated. It also reports
`procedure?` on the instantiated value — the only way to tell for certain
whether a binding is callable.

## What this harness does NOT measure

- **Class members.** `(define/public (area) 4)` binds a member of a class
  *value*, not a module-level name, so neither the expanded module body nor
  `module->exports` mentions it. The oracle has nothing to say, and scoring it
  would be a category error. `methods_unscored` in `results.json` keeps the size
  of that unmeasured set visible; class-member extraction is covered by unit
  tests in `tests/test_racket_language.py` instead.
- **Anything the oracle could not expand.** Counted in `files_oracle_failed` and
  listed in `oracle_errors`, never dropped — a shrinking denominator flatters
  every ratio.

## Running it

Requires `racket` on PATH. Racket is a **dev prerequisite, not a package
dependency**, which is why this is a benchmark and not a test.

```bash
python benchmarks/racket_fidelity/run_fidelity.py            # writes results.json
python benchmarks/racket_fidelity/run_fidelity.py --limit 40 # quick pilot
```

⚠ `oracle.rkt` calls `dynamic-require`, which **instantiates** each module.
Point it at libraries, never at scripts with side effects.

## Corpus and pinning

`corpus.json` targets the `collects` tree that ships with the Racket install.
That tree is pinned by the **Racket version** rather than a git SHA — the
interpreter identifies the corpus — and `results.json` records the version it
was measured against. A run under a different Racket is measuring a different
corpus and its numbers are not comparable.

## Gated in CI without Racket

`tests/test_racket_fidelity.py` checks the two must-be-zero buckets against a
frozen copy of the oracle's answer for `tests/fixtures/racket/*.rkt`, so the
fabrication guards run everywhere. See `tests/fixtures/racket/REGENERATE.md`.

## Reading `results.json`

`summary` carries the totals. `per_file` carries the attribution — which file
each miss came from, which is what tells you whether a gap is one macro-heavy
file or a systematic problem.
