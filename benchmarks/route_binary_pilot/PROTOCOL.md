# Route binary pilot — protocol, registered before any case exists

## The question

Emitted-task routing collapses to one decision. **87.5% of gold labels in the
emitted corpus are `search_text` or `search_symbols`, split 18/17**, and `route`
is at **12/23 = 52.2%** on it against a **51.4%** majority-class line — chance.
The objective is therefore

    P(correct | gold in {search_text, search_symbols})

and not `route@1` or `route@3` over 91 actions. See `ROADMAP.md`.

Both string-only hypotheses are refuted: identifier shape (H1) and imperative
verb (H2), each failing on **coverage** rather than purity — the predicate fired
on 5–15% of queries while the decision needs answering 100% of the time.

## Why this pilot exists, and what it may NOT conclude

The remaining hypothesis class is a signal from **outside** the query string. It
cannot be tested on the existing corpus: those rows carry no repository, and 4 of
35 pair-labelled cases name a resolvable one. Building a repo-grounded corpus of
agent-emitted tasks is a project.

**This pilot is the cheap kill-check that decides whether that project is worth
starting.** It runs on a distribution we control, which makes it strictly easier
than the real thing:

- **A negative here is decisive.** If a grounded probe cannot separate the two
  classes on tasks we constructed to be separable, it will not separate
  agent-emitted tasks, and the corpus project should not start.
- **A positive here certifies nothing.** It sizes an effect on synthetic
  paraphrase. Agent wording is a third distribution, distinct from both the
  human corpus and this one. A positive result buys the right to build the real
  corpus; it does not buy a routing change.

⚠ Stated here so the asymmetry cannot be discovered later, when a positive
result is in hand and the temptation is to spend it.

## The predicate, registered

Committed **before** any case exists — see `git log` for this directory; the
predicate commit precedes the generator commit. That ordering is the evidence of
pre-registration. Nothing else can be.

    H3: the discriminator is whether the sought thing IS an indexed symbol name
        in the repository the task refers to.

    predict(task, index):
        tokens  = content words of `task`, stopwords removed
        matched = any token that matches an indexed SYMBOL NAME, comparing
                  case-insensitively and against snake_case / camelCase parts
        return "search_symbols" if matched else "search_text"

**Coverage is 100% by construction** — the predicate always returns a class. That
is the property H1 and H2 both lacked, and the reason this is the first
hypothesis of its family worth running.

## Construction, and the circularity it must avoid

⚠⚠ **The obvious design is circular and must not be used.** If gold is "the
target is a symbol" and the predicate is "the task mentions a symbol", the test
is a tautology dressed as an experiment.

It is non-circular only because **the predicate never sees the target.** Cases
are built so the task refers to its target *obliquely* — the target's name does
not appear verbatim — so the predicate must recover the class from paraphrase
plus the index, which is a real inference and can fail.

- **Class S** — target is a real symbol in the pinned repo. Gold `search_symbols`.
- **Class T** — target is a real string literal or comment that is **not** any
  symbol's name. Gold `search_text`.

Gold is fixed by which kind of object the case was built from, which is also what
the task's answer actually requires: a symbol is retrieved by symbol search, a
literal by text search. Gold is never read by the predicate.

⚠ **Leakage is the failure mode that would fake a positive** and is measured, not
assumed. If the paraphrase carries the target's name tokens, the predicate wins
for free. The pilot reports mean name overlap on the same definition the route
harness uses, and a high-leak result must be discarded rather than explained.

## Baselines

Reported beside every figure, k-matched, for the reason `run_emitted_task.py` got
wrong: **a baseline gets as many guesses as the system it is the floor for.**

- majority class (the corpus is balanced by construction, so ~50%)
- best constant answer
- the live `route` classifier on the same tasks, as the incumbent

## Repos

`benchmarks/tasks.json` pins three, all indexed locally: `expressjs/express`,
`fastapi/fastapi`, `gin-gonic/gin`. Their SHAs are the ones already published
there. A run against a different `git_head` is measuring a different corpus and
must not be compared.

## Stopping rule

Registered so it cannot be chosen after seeing the result. The pilot is a
**screen**, and a small one:

- **n ≈ 60**, balanced. At that size only a large effect is detectable: roughly
  ≥68% accuracy clears a 50% line at p < 0.01 two-sided.
- **A null result means "not large", never "no effect."** Report the confidence
  interval, not just the point estimate.
- **One predicate, one run, nothing fitted.** If the first result is
  disappointing, the corpus is spent — a second predicate tuned against these
  cases is a fitting pass wearing an experiment's clothes.
