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
| oracle definitions | 3684 |
| jcm symbols | 3514 |
| **extra** | **0** |
| **wrong_span** | **0** |
| missing | 156 (95.8% coverage) |
| clean files | 44 |

`missing` is **entirely** the two kinds we deliberately do not emit:

- `module` (126) — `mod foo;` declares the module graph, not a callable or a
  type. The file tree already answers where a module lives.
- `macro` (30) — `macro_rules! name` defines a macro. We do not expand macros,
  so indexing the name implies a reach we do not have.

**`missing_unexplained` is `{}`.** The harness shipped with three gaps and all
three are now closed:

| gap | was | fix |
|---|---|---|
| `union Foo { .. }` yielded no symbol at all | not in `RUST_SPEC` | `union_item` added |
| a trait method with a signature and no body | a different node type, `function_signature_item` | added to `RUST_SPEC` |
| a `const`/`static` inside a function body | excluded by the locals gate | `_FUNCTION_SCOPED_CONSTANT_LANGUAGES` |

⚠ The third is the one with a judgement in it. The locals gate exists to keep
function-local names out, and it was already letting nested `fn`s through — so
the behaviour was not "locals are excluded", it was "locals are excluded unless
they are functions". A rule that splits a scope by node type is not a scope
rule. Rust is widened by name, in its own set, with the reasoning recorded; the
gate is untouched for every other language.

## ⚠⚠ The ceiling, and it is lower than Racket's

`syn` **parses**; it does not **expand**. Racket's oracle expands, so it sees
macro-introduced names and `syntax-original?` separates them from human-typed
ones. Nothing here can. An item produced by a `macro_rules!` invocation is
invisible to the oracle **and** to jCodeMunch, so it is unscored in both
directions.

**Do not read a green run as evidence about macro-generated code.** A Rust
codebase that generates much of its surface through macros is measured here only
on the part it wrote by hand.

## ⚠ Three measurement traps, all hit while building this

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

**And it must walk NESTED blocks, not just a function's top-level one.** After
the three extraction gaps were closed the gate failed with 2 fresh "extras" —
`UTF8_BOM` inside a `for` body and `HEX` inside a `match` arm. Both are real
`const` definitions; the hand-rolled walker only entered a function's outermost
block. ⚠⚠ **That is the same trap for the third time, so the walker was replaced
with `syn::visit::Visit`**, which recurses through expressions, arms and
closures by default. A hand-rolled walk only sees where its author remembered to
look, and every omission scores as an extractor fabrication. Omissions are now
overridden deliberately rather than arrived at by forgetting.

⚠ `build_oracle()` also used to return an existing binary without rebuilding,
so a failed recompile silently reused the previous oracle and reported the
numbers unchanged — which reads as "the change had no effect" rather than "the
change did not compile". It always rebuilds now.

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
