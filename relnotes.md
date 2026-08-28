### Fixed - the fast path hydrated the whole index to read six metadata fields (#557)

`index_folder`'s watcher fast path opened with an unconditional
`store.load_index(owner, repo_name)  # always load base for branch check` --
inside the block whose entire purpose is to skip loading the index, and three
lines above the `use_memory_hash_cache` flag that exists to make the store's
hashes unnecessary. The saving that flag describes was never realised on a cold
read, because this ran first regardless.

Everything the path asks of that index is metadata: `branch`, `git_head`,
`file_hashes`, `has_source_file`, and the two re-parse stamps
`parser_generation` / `racket_config_digest`. It now takes a
`SelectiveIndexView`, which answers all six from the `meta` and `files` rows and
reads **zero symbol rows**. Measured cold on this repo's own index (13,906
symbols): **0.172 s -> under 1 ms**.

⚠ `parser_generation` and `racket_config_digest` had to JOIN `EXACT_FIELDS`.
Absent from it they fall through `__getattr__`, which promotes -- so the
per-event upgrade check would have loaded every symbol in the repository to read
one integer, and the change would have moved the cost rather than removed it.
`racket_config_digest` is None-meaningful (absent means "built before the
gate"); copying it exactly preserves that, where promoting to answer it only
ever changed the price.

⚠⚠ **The test asserts the OUTCOME, not the mechanism.** A test that checked
"`open_selective` is called" would stay green while a newly added
`existing_index.symbols` quietly hydrated the corpus behind it -- which is the
only regression worth catching. `SelectiveIndexView.promoted` is the witness: it
flips the moment anything on that path reaches for a corpus-wide attribute.
4 of the 5 new tests fail against the pre-fix tree; the fifth guards a future
regression and is honestly vacuous today.

⚠ **Not shown to be @Ticki84's 10 s, and said so on the thread.** Their index is
6,352 symbols, where the same load costs well under a tenth of a second here.
This matters on large indexes -- #370 clocked a cold 665k-symbol hydration at
7.5-11.4 minutes -- and theirs is small. Shipped because it is wrong, not
because it explains their number.

### Added - the watcher's re-index line splits its own duration (#557)

`Re-indexed <path>: changed=1 new=0 deleted=0 (10.31s)` said the time was inside
`index_folder` and stopped there. The line now carries a per-phase breakdown:

```
... (10.31s) [base_index=0.02s classify=0.01s read_hash=0.14s parse=0.09s git_head=0.01s save=10.04s]
```

Resolving the base index, classifying the change set, reading and hashing the
changed files, parsing, and the store write. Also on the result as
`phase_seconds`, and logged at DEBUG.

⚠⚠ **Written because three rounds of hypotheses were each measured and each
wrong** -- an old version, the hash-cache reload, `JCODEMUNCH_INDEX_CACHE_TTL`,
context providers. A maintainer who cannot reproduce a report has nothing to
work from but the reporter's patience, and spending it on guesses is the
avoidable part. One line from one log now names the subsystem.

⚠ **Absence is a signal, so it is a real absence.** The full walk emits no
breakdown at all rather than an empty or zeroed one, which would read as "the
fast path ran and cost nothing" -- the opposite of what happened. A missing
bracket means the fast path was not taken, which is the first thing worth
knowing.

### Added - `--no-context-providers` on `watch`, `watch-all` and `watch-claude` (#558)

`index_folder` has taken a `context_providers: bool` for its whole life and the
watcher could not reach it: no CLI flag, and not a parameter of `watch_folders`,
`sync_folders`, `watch_claude_worktrees`, `WatcherManager`, `_watch_single`,
`_initial_index` or `watch_all`. Its three neighbours — `use_ai_summaries`,
`follow_symlinks`, `extra_ignore_patterns` — were threaded end to end, so
nothing looked wrong at any single site.

Surfaced by **@Ticki84** in #557: they disabled providers to isolate a
performance problem, the argument reached `index_file` and could not reach the
watcher, and their two timings were taken under two different configurations
with nothing saying so. **A reporter holding a variable fixed across a
comparison should not be silently unable to.**

⚠ **Scope, stated plainly: this is a control gap, not a performance fix.**
Provider discovery is cached per folder, so on the fast path it is paid once per
process. Measured here: providers ON 0.52 s mean / **0.36 s min**, OFF 0.37 s
mean — the difference is the first iteration and nothing after. What is real is
that discovery re-runs on the first event after a watcher restart and is bounded
at 30 s per provider (`JCODEMUNCH_PROVIDER_BUDGET_SECONDS`), and that
`_attach_provider_skips` already advises "set `context_providers=false` to stop
paying for it" — advice the watcher structurally could not take.

⚠⚠ **The guard is worth more than the flag, and writing it found the real
weakness.** `tests/test_watcher_knob_parity.py` asserts the correspondence as a
PROPERTY over signatures rather than a list of four names. The first version
compared layers against each other and **six of its seven tests passed against
the broken tree** — parity across layers only catches a knob that stops PART
WAY, and this one was missing from every layer at once, so the shared set was
simply smaller and nothing looked uneven. It is anchored to what `index_folder`
OFFERS now, with per-parameter exclusions that each state a reason
(`changed_paths` is computed, `force_reparse` belongs to `refresh`, and so on),
so adding one is a decision someone writes down.

⚠⚠ **The first attempt broke six existing tests and they were RIGHT.** Adding
`context_providers` as a REQUIRED parameter mid-signature on `_watch_single` and
`_initial_index` broke every caller that did not know about it, and a defaulted
parameter cannot precede the required ones that follow — so it is defaulted and
placed at the end of both signatures. **The inverse of Practice 9: when a change
turns old tests red, check whether the change is wrong before the tests are.**

⚠ Two false positives the property surfaced and both were the TEST being wrong:
`paths` means "explicit file list" to `index_folder` and "folders to watch" to
the watcher — a name collision, not a knob — and flag names are derived loosely,
because the shipped flag for `use_ai_summaries` is `--no-ai-summaries`, not
`--no-use-ai-summaries`. Pinning one spelling would have failed against a flag
that has worked for a year.


### Fixed - the watcher reloaded the whole index to learn one file's hash (#557)

Reported by **@Ticki84**: on Windows a single-file edit took ~10s to reach the
index while `index_file` on the same file took ~0.2s.

After each successful reindex the watcher called `_build_hash_cache()`, a full
`load_index` that hydrates **every symbol** in order to refresh a dict of file
hashes -- hashes `index_folder` had just computed and stored. It now returns
them (`file_hashes_delta` / `file_hashes_removed`) and the watcher applies the
delta.

⚠⚠ **The first version of this entry, and the first comment on the issue, said
the reload cost 0.36 s per event. That was WRONG and the correction is the more
useful half.** `incremental_save` keeps the LRU entry coherent, so re-loading
straight after saving measures **0.001 s**. The 0.36 s was a cold load in a
fresh process -- a startup cost, paid once. **Measured only after asserting the
opposite in public.**

⚠⚠ **What this removes is a CLIFF, and a setting we ship reaches it.**
`JCODEMUNCH_INDEX_CACHE_TTL` evicts an index that has sat unused, and **a
watcher is idle between edits by definition** -- so with the TTL set, every edit
pays a cold hydration. Measured at `TTL=1` with a 1.5 s gap between edits:
**0.001 s -> 0.19 s per event on 15,075 symbols**, and #370 clocked a cold
665k-symbol hydration at **7.5-11.4 minutes**. Anything else that moves the .db
mtime between the save and the read does the same: a second server instance, the
embedding store, `refresh`. Reading what we already computed depends on none of
it. ⚠ That interaction was undocumented; the env var is recommended for hosts
that leak stdio processes, which is exactly where a watcher also runs.

⚠ **Re-reading the changed file is NOT the alternative** and the full reload was
there to prevent it: the file can change again between `index_folder`'s read and
the watcher's, so the cache records a hash for content nobody indexed and the
next edit is skipped as unchanged (T6). A delta has no second read to race with.

⚠ **ABSENT is not EMPTY.** A run that reports no delta (older code, a full walk,
an exit added later) falls back to the full reload; only an explicit empty delta
means "nothing moved". Treating a missing key as "no changes" would freeze the
cache and stop reindexing silently -- the failure the cache exists to prevent.
The type check, not a truth check, is what keeps those apart, and
`tests/test_watcher_hash_delta.py` pins it. All 8 tests fail against the
pre-fix tree.

⚠ **Withheld unless `changed_paths` was supplied.** `index_folder` is an MCP
tool and the delta is unbounded in the size of the change set; a full walk would
put every hash in the repo on the wire against a response cap that refuses
rather than truncates. Only the watcher passes `changed_paths`, so the tool
response is unchanged.

⚠ **This is not @Ticki84's 10 s.** They answered on the thread: version
1.108.303, `JCODEMUNCH_INDEX_CACHE_TTL` unset, providers confirmed off from the
log's own silence, and the DEBUG line's `(10.31s)` is `index_folder`'s OWN
duration -- so the time is inside indexing, not in this reload. Every hypothesis
offered here has now been measured and none of them explains it. The defect
above is real and worth fixing either way; the phase breakdown below is what
replaces the guessing.
