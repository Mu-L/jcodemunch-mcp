# Extraction fingerprint — deriving the trust stamp instead of maintaining it

Status: **spec, not implemented.** Written 2026-08-25.

## The problem, measured

`PARSER_GENERATION` is a hand-maintained integer that decides whether an
index's symbols are trusted. It was set to `1` on 2026-08-05 (v1.108.244, #414)
and has not moved since.

**Ten commits touched `src/jcodemunch_mcp/parser/` in that window.** Four of
them change which symbols exist:

| commit | date | effect on stored symbols |
|---|---|---|
| `#428` Rust/Go/Java/PHP constants | 2026-08-15 | adds symbols |
| `.267` Kotlin and Bash constants | 2026-08-08 | adds symbols |
| `.246` class field initializer no longer donates members | 2026-08-05 | changes membership and ids |
| `.254` Python package-relative import edges | 2026-08-07 | changes the graph |

These are exactly the case the counter exists for: **file content is unchanged,
so the incremental path never re-reads it, so the new constants never appear.**

Census of one developer machine, 2026-08-25:

- **113** local indexes
- **100** at generation `0` — repairable, because the stamp is below the constant
- **13** at generation `1` — **permanently exempt**, because the stamp equals the constant
- **8 of those 13** predate parser changes they are missing, including
  `MCPs-jcodemunch-mcp` itself (missing Kotlin/Bash constants since 2026-08-10)

⚠⚠ **This is why "have the watcher trigger the rebuild" is not the fix.** It
would repair the 100 once, stamp them `1`, and move them into the exempt
bucket — converting an observable problem into an unobservable one. The trigger
is not what is broken. **The stamp is a manual assertion about an automated
thing, and it has drifted from what it names.**

### The same defect, one level down, in shared infrastructure

`parser/parse_cache.py` keys entries on `(INDEX_VERSION, content_hash,
language, filename)`. `INDEX_VERSION` moves for **storage-schema** reasons and
is unrelated to extraction semantics, so a parser change does not invalidate a
cached parse.

That cache is explicitly **shared across seats** (`JCODEMUNCH_PARSE_CACHE`,
"point all seats on a multi-home-dir box at the same path"), so one seat's
stale parse is served to every seat. Any fix that repairs the index stamp and
leaves this key alone will re-populate repaired indexes from stale cache rows.
**Both keys must move together, and the cheapest way to guarantee that is for
both to read the same derived value.**

### The input nobody would have hashed

`pyproject.toml` declares `tree-sitter-language-pack>=0.7.0,<1.0.0` — a range,
not a pin. Installed here: `0.13.0`. **The grammar can change under a user with
no jcm code change at all**, and the parse trees change with it. A fingerprint
over our own source would miss this entirely and reintroduce silent drift one
level down — the failure this document exists to end.

## The proposal

Replace the hand-maintained integer with a value **derived from the things that
actually decide what a symbol is**, computed once per process.

```
EXTRACTION_FINGERPRINT = sha256(
    canonical_json([
        (module_name, sha256(module_source_bytes)) for module in EXTRACTION_INPUTS
    ] + [
        ("tree-sitter", version),
        ("tree-sitter-language-pack", version),
    ])
)[:16]
```

Stored as a new `meta` key (`extraction_fingerprint`). Additive — old readers
ignore it, so **no `INDEX_VERSION` bump is required.**

### `EXTRACTION_INPUTS` — derived from what lands on a symbol row

A stored symbol row carries `id, name, kind, signature, docstring, line,
end_line, byte_offset, byte_length, parent, qualified_name, language,
decorators, keywords, content_hash, cyclomatic, max_nesting, param_count`.
Working backwards from that:

| module | why it is in scope |
|---|---|
| `parser/extractor.py` | the extraction itself |
| `parser/languages.py` | `LANGUAGE_REGISTRY`, extension map, node kinds |
| `parser/symbols.py` | `make_symbol_id`, `compute_content_hash` — the **id format** |
| `parser/complexity.py` | `cyclomatic`, `max_nesting`, `param_count` |
| `parser/fqn.py` | `qualified_name` |
| `parser/template_shared.py`, `astro_shared.py`, `sql_preprocessor.py` | pre-parse transforms that move offsets |
| `parser/hierarchy.py` | `parent` |

**Open question, deliberately not decided here: `parser/imports.py`.** It does
not write the symbol row; it builds the import graph, which is what
`find_importers`, `get_blast_radius` and dead-code answers read. A change there
makes an unchanged index answer differently — the same defect — but the repair
cost and the invalidation scope differ. Two options: fold it in (one
fingerprint, one re-parse, simpler, more re-parses), or give the graph its own
fingerprint. **Deciding this by accident is how the next drift starts.**

### Failure behaviour

⚠⚠ An unreadable input must **not** silently produce a partial hash, and must
**not** produce "always re-parse" either — the first is the bug we are fixing,
the second thrashes every index on every run.

Include the literal pair `(module_name, "UNREADABLE")` in the hash. It is
deterministic, so it is stable while the condition persists: **one** re-parse,
not an infinite loop, and the fingerprint still differs from the readable case
so nothing is silently trusted. A frozen or zipapp install therefore degrades
to a stable distinct fingerprint rather than to a false match.

Whether the degraded state is *disclosed* to the caller is a separate decision
from whether it is *counted*, and it should be disclosed.

### Migration

An index with no `extraction_fingerprint` key mismatches by construction, so
every existing index — **both** the 100 at generation 0 and the 13 exempt at
generation 1 — takes exactly one re-parse. That is the point: the 13 are
currently unreachable and this is what reaches them.

⚠ **Cost is real and must be paced, not hidden.** 113 indexes on this machine;
NestJS alone was 46.7 s. `tools/refresh.py` already exists for bounded,
resumable, cursor-persisted re-parsing and is the right vehicle — it was built
for a `PARSER_GENERATION` bump and this is one, just an automatic one.

⚠ **Known cost for jcm developers specifically:** editing `extractor.py` now
changes the fingerprint, so every local index wants a re-parse. That is
*correct* — the parser did change — but it is a real ergonomic tax on this
repo's own contributors and should be acknowledged rather than discovered.

## What this must NOT cover

Configuration that changes **which files were indexed** — `max_file_size`,
`max_folder_files`, skip patterns, `CACHEDIR.TAG` — is a **coverage** question,
already answered by the coverage contract and the withheld-reason machinery.
Folding it in would force a full re-parse every time someone edits a config key
and would conflate "we extracted differently" with "we looked at a different
set of files". Two different claims, two different repairs.

## Verification the spec requires

1. **The ratchet must be over the property, not the list.** A test that
   enumerates `parser/*.py` and fails when a module is present in the package
   but absent from `EXTRACTION_INPUTS`. Without it, the next parser module
   added is silently outside the fingerprint — which is this same bug, wearing
   the fix as a costume.
2. **Non-vacuity, run against the reintroduced defect.** Mutate one byte in
   each declared input in turn and assert the fingerprint moves for every one.
   A fingerprint that ignores an input it claims to cover is indistinguishable
   from a correct one until it matters.
3. **Grammar sensitivity, proven not assumed.** Monkeypatch the reported
   `tree-sitter-language-pack` version and assert the fingerprint changes.
4. **Stability.** Two calls in one process, and two processes on the same tree,
   produce identical values — otherwise every index re-parses on every run.
5. **The parse cache moves with it.** Assert `parse_cache._key` incorporates
   the fingerprint, so a repaired index cannot be re-populated from stale
   shared rows.

## What is NOT proposed here

Pinning `tree-sitter-language-pack` to an exact version. That is a separate
supply-chain decision with its own trade-offs; the fingerprint makes a grammar
change *visible and self-repairing* whether or not the range is later narrowed.

## Sizing the actual damage

⚠ The headline "178,013 symbols from a distrusted parser" is **not** 178,013
wrong symbols, and quoting it that way overstates this by a wide margin.
Measured on NestJS (clean tree, same commit, so the parser is the only
variable): **0.5%** id churn — 58 ids gone, 61 new, 10,652 identical. The
sampled churn is in a file with **zero non-ASCII bytes**, so it is *not* #414
at all; it is ordinary parser evolution. #414's own trigger appears in **1.1%**
of that repo's files.

**The case for this work is the drift mechanism and the exempt bucket, not a
corruption emergency.** Anyone citing it should cite the mechanism.
