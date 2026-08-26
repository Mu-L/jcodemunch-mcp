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
    ("from .receipts import build\n", [".receipts"]),
    ("from ..parser.fqn import x\n", ["..parser.fqn"]),
    ("from pkg.receipts import build\n", ["pkg.receipts"]),
    ("import os\n", ["os"]),
    ("from __future__ import annotations\n", []),
])
def test_every_other_import_form_is_untouched(source, unchanged):
    """⚠ The expansion is gated on a specifier that is ALL dots. A dotted
    relative import already names its module and must not gain a second edge."""
    assert _specs(source) == unchanged


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
