# Racket extraction fidelity

**The question this answers is not "what percentage did we get".** It is:
*when jCodeMunch's index differs from what Racket itself knows, is the
difference an honest gap or a false statement?*

An agent handed an incomplete index reads the file instead. An agent handed a
**wrong** index repeats the error. So the buckets are asymmetric, and so are
their bars.

| Bucket | Meaning | Bar |
|---|---|---|
| `extra` | a name we assert that Racket does not know | **0** |
| `wrong_span` | the definition is not inside the bytes we would return for that symbol | **0** |
| `missing` | a name a human wrote that we did not find | reported |
| `callable_unknowable` | we say `constant`, the value turns out to be a procedure | reported |
| `generated_only` | macro-introduced; invisible by construction | reported |
| `export_only` | reachable under a different name than we indexed (`rename-out`, `struct-out`) | reported |

`callable_unknowable` is a **ceiling, not a bar**. `racket/function.rkt` writes
`(define curry (make-curry #f))` — callable, and no syntactic test can know it.
Driving that bucket to zero needs an evaluator, so a bar there would be a wish.

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
the rename gap quantified rather than argued about. It also reports
`procedure?` on the instantiated value, which is the only honest evidence for
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

`summary` carries the totals; `per_file` carries the attribution. The useful
view is usually *how many files are clean*, not the corpus average — misses
concentrate hard in macro-heavy files rather than spreading evenly.
