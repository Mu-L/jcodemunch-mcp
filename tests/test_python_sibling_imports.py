"""`from . import <sibling>` is a dependency on the sibling, not on `__init__.py`.

#550 (@rknighton): the specifier for that form is a bare `.`, which names the
package. `resolve_specifier` only ever sees the specifier, so every such import
resolved to the package's `__init__.py` and the edge to the sibling module was
never built. This repo uses the form 49 times; it alone reported 20 live files
as dead.

⚠ The fix is at EXTRACTION, not resolution: a per-name specifier is emitted
ALONGSIDE the bare one, so the 26 `resolve_specifier` call sites keep their
single-target contract and the `__init__.py` edge that already worked is
untouched. `from . import x` may be a submodule OR an attribute of
`__init__.py`, and the importing file cannot say which -- offering both is the
only honest answer.
"""

import pytest

from jcodemunch_mcp.parser.imports import _extract_python_imports, resolve_specifier

_FILES = {
    "pkg/__init__.py",
    "pkg/receipts.py",
    "pkg/scip.py",
    "pkg/producers.py",
    "sibling_pkg.py",
}
_IMPORTER = "pkg/producers.py"


def _specs(source: str) -> list[str]:
    return [e["specifier"] for e in _extract_python_imports(source)]


def _resolved(source: str) -> set:
    return {
        resolve_specifier(e["specifier"], _IMPORTER, _FILES)
        for e in _extract_python_imports(source)
    } - {None}


def test_the_sibling_module_edge_is_built():
    assert "pkg/receipts.py" in _resolved("from . import receipts\n")


def test_the_package_edge_is_kept_alongside_it():
    """⚠ Not a belt-and-braces detail. `from . import helper` where `helper` is
    defined IN `__init__.py` is legal Python, and dropping the package edge to
    chase the submodule would break that case in the other direction."""
    assert _resolved("from . import receipts\n") == {"pkg/__init__.py", "pkg/receipts.py"}


def test_a_name_with_no_matching_module_costs_nothing():
    """It resolves to None, which every consumer already skips, and the
    `__init__.py` edge still stands."""
    assert _resolved("from . import a_function_defined_in_init\n") == {"pkg/__init__.py"}


def test_two_bare_dot_lines_in_one_file_both_survive():
    """⚠ The dedup keys on the specifier, and EVERY bare-dot import in a file
    shares the same one -- so the second line used to be dropped whole, names
    and all. Reported as one defect; this is the second half of it."""
    resolved = _resolved("from . import receipts\nfrom . import scip\n")
    assert {"pkg/receipts.py", "pkg/scip.py"} <= resolved


def test_multiple_names_on_one_line_each_get_an_edge():
    resolved = _resolved("from . import receipts, scip\n")
    assert {"pkg/receipts.py", "pkg/scip.py"} <= resolved


def test_an_alias_resolves_by_the_original_name():
    assert "pkg/receipts.py" in _resolved("from . import receipts as r\n")


def test_a_parent_package_sibling_resolves():
    """`from .. import x` climbs one package, so `x` is a sibling of `pkg`."""
    assert "sibling_pkg.py" in _resolved("from .. import sibling_pkg\n")


@pytest.mark.parametrize("source,unchanged", [
    ("import os\n", ["os"]),
    ("from __future__ import annotations\n", []),
])
def test_a_plain_import_gains_no_per_name_edge(source, unchanged):
    """`import os` names no package to look inside, so there is nothing to
    expand. `from __future__` is not an import edge at all."""
    assert _specs(source) == unchanged


@pytest.mark.parametrize("source,module_edge", [
    ("from .receipts import build\n", ".receipts"),
    ("from ..parser.fqn import x\n", "..parser.fqn"),
    ("from pkg.receipts import build\n", "pkg.receipts"),
])
def test_a_dotted_form_keeps_its_module_edge(source, module_edge):
    """⚠⚠ REWRITTEN AT #566, and the original is why the defect stood.

    It read `assert _specs(source) == unchanged` under the docstring "the
    expansion is gated on a specifier that is ALL dots -- a dotted relative
    import already names its module and must not gain a second edge." That
    states the MECHANISM, and its premise is false: `from ..parser.fqn import
    x` names the module `fqn` only if `x` is an attribute of it. When `fqn` is
    a package and `x` a module inside, the second edge is the real dependency
    and the first is the package.

    So the property is that the module edge SURVIVES, never that it is alone.
    An extra per-name specifier is harmless by construction -- it resolves to
    None whenever no such file exists, and every consumer skips None."""
    assert module_edge in _specs(source)


def test_a_per_name_edge_never_invents_a_file():
    """The other half: offering the specifier must not create an edge to
    something that is not there. `build` is a function in `receipts.py`."""
    assert resolve_specifier(".receipts.build", _IMPORTER, _FILES) is None
    assert _resolved("from .receipts import build\n") == {"pkg/receipts.py"}


def test_the_defect_is_reachable_from_the_repos_own_source():
    """⚠ A synthetic fixture proves the rule; this proves the rule matters here.
    Measured on `src/` at the fix: 87 sibling edges that did not exist, 30
    distinct modules made reachable, across 62 importing files."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "src"
    if not root.is_dir():
        pytest.skip("no src tree (installed package checkout)")
    files = {p.relative_to(root.parent).as_posix() for p in root.rglob("*.py")}
    built = 0
    for path in root.rglob("*.py"):
        rel = path.relative_to(root.parent).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for edge in _extract_python_imports(text):
            spec = edge["specifier"]
            if not spec.startswith(".") or set(spec) == {"."}:
                continue
            if spec.lstrip(".") not in edge["names"]:
                continue  # a hand-written dotted import, not a synthesised one
            target = resolve_specifier(spec, rel, files)
            if target and not target.endswith("__init__.py"):
                built += 1
    assert built > 50, (
        f"only {built} sibling edges resolve from this repo's own source; the "
        f"measurement at the fix was 87. Either the expansion regressed or the "
        f"tree stopped using `from . import`."
    )


def test_the_named_package_defect_is_reachable_from_the_repos_own_source():
    """The #566 half of the scan above, which counts only the bare-dot family.

    Measured on `src/`: 21 synthesised edges that resolve, from 18 importer
    files, reaching 12 modules -- `evidence/producers.py`, `receipts.py`,
    `retrieval/embed_drift.py`, `storage/embedding_matrix.py`,
    `storage/token_tracker.py` among them. Every one reported zero importers
    while its importer sat at module scope in an indexed, live file.

    ⚠⚠ A SYNTHESISED edge is told apart by consulting the raw source, never by
    the specifier's spelling. The first version of this guard filtered on
    "last segment appears in `names`", which also matches the hand-written
    `from .tools.index_repo import index_repo` -- a module and its chief export
    sharing a name. This repo has 113 of those, so the guard scored 134 and
    PASSED with the defect reintroduced. It is the reason the non-vacuity pass
    is run against the broken tree and not only the fixed one."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "src"
    if not root.is_dir():
        pytest.skip("no src tree (installed package checkout)")
    written_re = re.compile(r"^\s*from\s+([.\w]+)\s+import\s", re.M)
    files = {p.relative_to(root.parent).as_posix() for p in root.rglob("*.py")}
    built = 0
    for path in root.rglob("*.py"):
        rel = path.relative_to(root.parent).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        written = set(written_re.findall(text))
        for edge in _extract_python_imports(text):
            spec = edge["specifier"]
            if spec in written:
                continue  # hand-written, and it already resolved
            if not spec.rpartition(".")[0].lstrip("."):
                continue  # bare-dot family (#550), counted by the scan above
            target = resolve_specifier(spec, rel, files)
            if target and not target.endswith("__init__.py"):
                built += 1
    assert built >= 15, (
        f"only {built} synthesised named-package edges resolve from this "
        f"repo's own source; the measurement at the fix was 21. Either the "
        f"expansion regressed to the bare-dot guard or the tree stopped using "
        f"`from ..pkg import module`."
    )


def test_a_prose_line_starting_with_import_does_not_erase_the_file(caplog):
    """⚠⚠ Found by the scan above, not by the report. `_PY_IMPORT` matches ANY
    line starting `import `, docstrings included, and a trailing comma left an
    empty final part that `[0]` raised on. `extract_imports` swallows the
    exception and returns `[]`, so one wrapped sentence cost `watcher.py` every
    import edge it had -- indistinguishable, downstream, from a file that
    imports nothing.
    """
    from jcodemunch_mcp.parser.imports import extract_imports

    source = (
        '"""Docstring.\n\n'
        "    import keeps the core watcher free of a hard dependency on the CLI,\n"
        '    which is the point.\n"""\n'
        "import os\n"
        "from . import receipts\n"
    )
    specs = [e["specifier"] for e in extract_imports(source, "pkg/watcher.py", "python")]
    assert "os" in specs, "the real imports were lost to a prose line"
    assert ".receipts" in specs


def test_an_extractor_that_raises_is_not_silent(caplog):
    """Practice 2. The caller cannot tell `[]` from a file with no imports, so
    the only signal that the edges were lost is the log line."""
    import logging

    from jcodemunch_mcp.parser import imports as imports_module

    def _boom(_content):
        raise RuntimeError("grammar exploded")

    original = imports_module._LANGUAGE_EXTRACTORS.get("python")
    imports_module._LANGUAGE_EXTRACTORS["python"] = _boom
    try:
        with caplog.at_level(logging.WARNING, logger=imports_module.__name__):
            assert imports_module.extract_imports("import os\n", "a.py", "python") == []
    finally:
        if original is not None:
            imports_module._LANGUAGE_EXTRACTORS["python"] = original
    assert any("no import edges" in r.message or "no import edges" in r.getMessage()
               for r in caplog.records), "the swallowed extractor failure logged nothing"


# ---------------------------------------------------------------------------
# #566: the same defect, written with the package named.
#
# The #550 fix guarded on `set(specifier) == {"."}` -- BARE dots -- so
# `from ..retrieval import embed_drift` kept resolving to the package and
# never to the module. Every argument in this file's docstring applies to it
# unchanged; only the spelling differs.
# ---------------------------------------------------------------------------

_NESTED = {
    "pkg/__init__.py",
    "pkg/retrieval/__init__.py",
    "pkg/retrieval/embed_drift.py",
    "pkg/storage/__init__.py",
    "pkg/storage/embedding_matrix.py",
    "pkg/tools/__init__.py",
    "pkg/tools/check_embedding_drift.py",
}
_NESTED_IMPORTER = "pkg/tools/check_embedding_drift.py"


def _resolved_nested(source: str) -> set:
    return {
        resolve_specifier(e["specifier"], _NESTED_IMPORTER, _NESTED)
        for e in _extract_python_imports(source)
    } - {None}


def test_a_named_package_reaches_the_module_it_imports():
    """`from ..retrieval import embed_drift` depends on embed_drift.py."""
    assert "pkg/retrieval/embed_drift.py" in _resolved_nested(
        "from ..retrieval import embed_drift\n"
    )


def test_the_package_edge_survives_the_named_form_too():
    """Both edges are offered, for the reason the bare-dot case offers both:
    the imported name may be a module or an attribute of `__init__.py`, and
    the importing file cannot say which."""
    assert _resolved_nested("from ..retrieval import embed_drift\n") == {
        "pkg/retrieval/__init__.py",
        "pkg/retrieval/embed_drift.py",
    }


def test_an_alias_on_the_named_form_resolves_by_the_original_name():
    """This is the shape that shipped in `check_embedding_drift.py:14`."""
    assert "pkg/retrieval/embed_drift.py" in _resolved_nested(
        "from ..retrieval import embed_drift as _ed\n"
    )


def test_a_single_dot_package_reaches_the_module():
    """`.pkg` is a named specifier too -- it just has one dot."""
    assert "pkg/storage/embedding_matrix.py" in {
        resolve_specifier(e["specifier"], "pkg/producers.py", _NESTED)
        for e in _extract_python_imports("from .storage import embedding_matrix\n")
    }


def test_multiple_names_on_a_named_package_each_get_an_edge():
    resolved = _resolved_nested(
        "from ..retrieval import embed_drift\nfrom ..storage import embedding_matrix\n"
    )
    assert {
        "pkg/retrieval/embed_drift.py",
        "pkg/storage/embedding_matrix.py",
    } <= resolved


def test_importing_a_name_that_is_not_a_module_adds_no_edge():
    """The synthesized specifier resolves to None and is skipped, rather than
    inventing a file. `is_source_layout` is a function, not a module."""
    specs = [
        e["specifier"]
        for e in _extract_python_imports("from ..retrieval import SomeClass\n")
    ]
    assert "..retrieval.SomeClass" in specs, "the per-name edge should still be offered"
    assert resolve_specifier("..retrieval.SomeClass", _NESTED_IMPORTER, _NESTED) is None


def test_the_guard_is_not_restricted_to_bare_dots():
    """Non-vacuity: this is the assertion that fails against the pre-#566 tree.

    The old guard read `set(specifier) == {"."}`, which is true only for `.`,
    `..`, `...`. Reintroducing it makes exactly this specifier disappear while
    every bare-dot test above stays green -- which is why those tests passed
    over the defect for the whole time it stood."""
    specs = [
        e["specifier"]
        for e in _extract_python_imports("from ..retrieval import embed_drift\n")
    ]
    assert "..retrieval.embed_drift" in specs
