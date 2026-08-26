"""`.mts` / `.cts` are TypeScript's ESM and CommonJS module extensions.

They were listed in the reindex hook's watched set and in NO extension->language
map, so editing one spawned `index-file`, which mapped no language and dropped
the file as `wrong_extension`. The hook reported success; the file was invisible.

The import half is inseparable from the language half. TypeScript's ESM rules
require the SPECIFIER to name the emitted file, so a `.mts` source is imported
as `./foo.mjs` -- an extension that is never on disk. Indexing `.mts` without
that rewrite makes the file visible and its importers invisible, which reads
downstream as a file nobody imports (the #550 shape).

Properties, not spellings: each test states an outcome a user can observe.
"""

import pytest

from jcodemunch_mcp.cli.hooks._common import _CODE_EXTENSIONS
from jcodemunch_mcp.parser.extractor import parse_file
from jcodemunch_mcp.parser.imports import _candidates
from jcodemunch_mcp.parser.languages import (
    LANGUAGE_EXTENSIONS,
    get_language_for_path,
)

# The JS/TS module-extension family. Each pair is one convention: the runtime
# extension the specifier names, and the source extension on disk.
_MODULE_PAIRS = ((".mjs", ".mts"), (".cjs", ".cts"))


@pytest.mark.parametrize("ext", [".mts", ".cts"])
def test_module_extension_resolves_to_a_language(ext):
    """A watched extension that maps to no language indexes as nothing."""
    assert get_language_for_path(f"a{ext}") == "typescript"
    assert LANGUAGE_EXTENSIONS[ext] == "typescript"


@pytest.mark.parametrize("runtime_ext,source_ext", _MODULE_PAIRS)
def test_family_is_enumerated_as_a_unit_in_the_hook_set(runtime_ext, source_ext):
    """Neither half of a convention pair may be watched without the other.

    Scoped to this family deliberately: `_CODE_EXTENSIONS` diverges from the
    registry on both sides BY POLICY, so a blanket equality would be wrong.
    """
    assert (runtime_ext in _CODE_EXTENSIONS) == (source_ext in _CODE_EXTENSIONS)


@pytest.mark.parametrize("runtime_ext,source_ext", _MODULE_PAIRS)
def test_esm_specifier_offers_the_source_it_stands_in_for(runtime_ext, source_ext):
    """`import "./foo.mjs"` must offer `./foo.mts`; the emitted name is not on disk."""
    cands = _candidates(f"./foo{runtime_ext}")
    assert f"./foo{source_ext}" in cands
    # The literal specifier stays a candidate -- a real `.mjs` still resolves.
    assert f"./foo{runtime_ext}" in cands


def test_extensionless_specifier_offers_the_module_sources():
    """`import "./foo"` must reach a `.mts`/`.cts` sibling."""
    cands = _candidates("./foo")
    assert "./foo.mts" in cands
    assert "./foo.cts" in cands


def test_js_specifier_rewrite_is_unchanged():
    """The pre-existing `.js` -> `.ts`/`.tsx` rule must not have moved."""
    cands = _candidates("./foo.js")
    assert cands == ["./foo.js", "./foo.ts", "./foo.tsx"]


@pytest.mark.parametrize("ext", [".mts", ".cts"])
def test_module_extension_yields_symbols(tmp_path, ext):
    """The outcome, not the map: a real file on disk produces real symbols."""
    content = (
        "export function mount(host: string): number {\n"
        "    return host.length;\n"
        "}\n"
    )
    f = tmp_path / f"widget{ext}"
    f.write_text(content, encoding="utf-8")

    language = get_language_for_path(str(f))
    assert language, f"{ext} maps to no language"

    names = {s.name for s in parse_file(content, str(f), language)}
    assert "mount" in names, f"{ext} symbols: {names}"
