# Regenerating `tests/fixtures/rust_oracle.json`

The frozen artifact is the output of `benchmarks/rust_fidelity/oracle/` over
every `.rs` file in this directory. It is committed so `tests/test_rust_fidelity.py`
gates on a machine with **no Rust toolchain**, which is what CI is.

Regenerate after touching **either** a fixture **or** the oracle:

```bash
cd benchmarks/rust_fidelity/oracle && cargo build --release && cd -
benchmarks/rust_fidelity/oracle/target/release/rust-fidelity-oracle \
    tests/fixtures/rust > /tmp/rust_oracle.raw.json
python -c "import json,pathlib; d=json.load(open('/tmp/rust_oracle.raw.json',encoding='utf-8')); \
pathlib.Path('tests/fixtures/rust_oracle.json').write_text(json.dumps(d,indent=2,sort_keys=True)+'\n',encoding='utf-8')"
```

On Windows the binary is `rust-fidelity-oracle.exe`.

⚠ `sort_keys=True` and `indent=2` are not cosmetic. The artifact is committed,
so an unstable serialisation produces a diff on every regeneration and nobody
reads it after the second time.

⚠⚠ **A stale artifact still passes most of the suite**, which is the failure
this file exists to prevent. `test_fixture_set_matches_the_frozen_oracle`
catches a fixture added without regenerating, but it cannot catch a fixture
*edited* without regenerating — the file set still matches while the definitions
no longer do. Regenerate on every edit, not only on every addition.

⚠⚠ **The oracle emits `qual` as well as `name`, and the gates that read it are
the ones a set could not provide.** `test_no_undercount` counts qualified names,
`test_qualification_matches_the_parser` compares owners. Regenerating with an
oracle built before 2026-08-27 writes an artifact with no `qual` field and both
gates raise `KeyError` rather than passing quietly — which is the intended
failure, not a bug to work around.

## Adding a fixture

Fixtures cover **grammar shapes**, deliberately including ones real code rarely
uses. That is not redundant with the pinned corpus in
`benchmarks/rust_fidelity/corpus.json`: ripgrep contains no `union`, so a
110-file run over real code scored the `union` gap as absent. The fixtures found
it in sixty lines.

The `parametrize` roster is read off disk, so a new fixture is gated the moment
it lands. ⚠ It used to be three literal filenames — a SECOND roster beside this
artifact, and only the artifact had a test keeping it honest.

If a new fixture surfaces a gap, add its oracle **kind** to `_KNOWN_GAPS` in
`tests/test_rust_fidelity.py` with a one-line reason, or fix the extractor. Do
not widen `_KNOWN_UNEMITTED` — that set is for kinds we deliberately never
index, and moving a gap into it converts a bug into a policy.
