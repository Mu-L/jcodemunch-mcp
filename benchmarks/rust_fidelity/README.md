# Rust extraction fidelity

Scores jCodeMunch's Rust extractor against **Rust's own parser**, the way
`benchmarks/racket_fidelity/` scores the Racket one against Racket's expander.

The question is not "what percentage did we get". It is: **when our index
differs from what Rust knows, is the difference an honest gap or a false
statement?** An LLM handed an incomplete index reads the file. An LLM handed a
wrong one repeats the error. So the buckets are asymmetric and so are their
bars.

| Bucket | Meaning | Bar |
|---|---|---|
| `extra` | a name we assert that `syn` does not know | **must be 0** |
| `wrong_span` | the definition is not inside the bytes `get_symbol_source` would return | **must be 0** |
| `missing` | a name a human wrote that we did not find | reported, broken out by kind |

## Current measurement

Target `ripgrep` at `3fce3b5bb0236da2df6d99672afb8a719642eca7`, 110 files,
0 parse failures on either side.

| | |
|---|---|
| oracle definitions | 3682 |
| jcm symbols | 3474 |
| **extra** | **0** |
| **wrong_span** | **0** |
| missing | 185 (95.0% coverage) |
| clean files | 41 |

`missing` decomposes into two **deliberate** kinds and two **gaps**:

- `module` (126) — `mod foo;` declares the module graph, not a callable or a
  type. The file tree already answers where a module lives.
- `macro` (30) — `macro_rules! name` defines a macro. We do not expand macros,
  so indexing the name implies a reach we do not have.
- `constant` (23) — **gap.** A `const` / `static` declared inside a function
  body is missed. `ripgrep`'s `decompress.rs` declares eight that way.
- `method` (6) — **gap.** A trait method with a signature and no default body
  (`fn doc_category(&self) -> Category;`) is missed.

A third gap, `union`, is not visible in this table because **ripgrep contains no
`union`**. It was found by the hand-written fixtures instead, which is the
argument for keeping both.

## ⚠⚠ The ceiling, and it is lower than Racket's

`syn` **parses**; it does not **expand**. Racket's oracle expands, so it sees
macro-introduced names and `syntax-original?` separates them from human-typed
ones. Nothing here can. An item produced by a `macro_rules!` invocation is
invisible to the oracle **and** to jCodeMunch, so it is unscored in both
directions.

**Do not read a green run as evidence about macro-generated code.** A Rust
codebase that generates much of its surface through macros is measured here only
on the part it wrote by hand.

## ⚠ Two measurement traps, both hit while building this

**The oracle must read the IDENTIFIER's span, not the item's.** `syn`'s
`Item::span()` starts at the first doc comment or outer attribute, so an item's
span line is where its *documentation* begins. Measuring against that scored
jCodeMunch at **40.4%** when the real figure was **95.4%**. The tell was that
every delta was one-sided — jcm was never *earlier*, which is the signature of
an oracle artifact rather than an extractor bug. A real span defect scatters
both ways.

**The oracle must walk function bodies.** Rust allows items inside function
bodies and real code leans on it: the `#[cfg(windows)] fn imp` /
`#[cfg(not(windows))] fn imp` pattern appears eight times in one ripgrep file.
An oracle that stops at the item level reports every one as a **fabrication by
the extractor**, which inverts the `extra` gate — correct code would fail the
build. Before the fix: 35 "extras". After: 0.

## Running it

```bash
git clone https://github.com/BurntSushi/ripgrep.git /tmp/ripgrep
git -C /tmp/ripgrep checkout 3fce3b5bb0236da2df6d99672afb8a719642eca7
python benchmarks/rust_fidelity/run_fidelity.py --target ripgrep --checkout /tmp/ripgrep
```

Add `--write` to publish `results.json`. ⚠ It **refuses** to publish when the
checkout has drifted from the SHA in `corpus.json`, because a number measured
against a different tree is a number about a different corpus. Same rule as
`benchmarks/tasks.json`.

⚠ Every SHA is validated as 40 lowercase hex before use. The first draft of
`corpus.json` was written through a shell heredoc and one digit arrived as
**U+096B DEVANAGARI DIGIT FIVE** — visually identical at this size, and it would
have pinned nothing.

## CI

CI does not run this. It runs `tests/test_rust_fidelity.py`, which gates the
same two buckets against **frozen** oracle data over `tests/fixtures/rust/`, so
it needs no Rust toolchain and no network. See
`tests/fixtures/rust/REGENERATE.md`.
