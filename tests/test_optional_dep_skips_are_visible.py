"""A skipped module must not hide how many tests it holds.

`pytest.importorskip` at module scope raises `Skipped` during IMPORT, so the
entire file collapses to one `1 skipped` line however many tests are in it.

⚠⚠ **Measured across this suite on 2026-08-23: ten module-scope guards stood in
front of 209 tests.** Nothing was being lost, because every optional package
happened to be installed here -- which is exactly why it was worth fixing. A CI
image that quietly stopped installing `watchfiles` would have reported a clean
run 49 tests short, and `N passed` cannot show that.

⚠ **Three of the ten sat PARTWAY DOWN their file**, so the import abort also
took out tests defined above the guard that had nothing to do with the missing
package. Measured with the dependency actually removed: `test_dbt_provider.py`
now runs 15 of its 31, `test_provider_metadata_and_perf.py` 16 of 20, and
`test_v1_108_95.py` 3 of 12. All three previously reported `1 skipped` and ran
nothing.

⚠ The sibling repo found this first, the expensive way: jdatamunch's
`test_excel_parser.py` reported one skip while holding 29 tests, 19 of which
passed on an ordinary dev box and had never run. It surfaced only by comparing
TOTALS between two interpreters, never from a passed count.

⚠ This bans module scope only. Inside a fixture or a test body, `importorskip`
is correct and visible: it skips that one test and the count reflects it.
"""

from __future__ import annotations

import ast
import pathlib

TESTS_DIR = pathlib.Path(__file__).resolve().parent


def _module_scope_importorskip(tree: ast.AST) -> list[int]:
    """Line numbers of importorskip calls not nested in a function or class."""
    hits: list[int] = []

    def walk(node: ast.AST, inside_body: bool) -> None:
        for child in ast.iter_child_nodes(node):
            is_body = isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            )
            if isinstance(child, ast.Call) and not inside_body:
                fn = child.func
                name = getattr(fn, "attr", None) or getattr(fn, "id", None)
                if name == "importorskip":
                    hits.append(child.lineno)
            walk(child, inside_body or is_body)

    walk(tree, False)
    return hits


def test_no_module_scope_importorskip():
    offenders = []
    for path in sorted(TESTS_DIR.rglob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - a broken file fails elsewhere
            continue
        for line in _module_scope_importorskip(tree):
            offenders.append(f"{path.name}:{line}")

    assert not offenders, (
        "module-scope pytest.importorskip collapses a whole file to one "
        "'1 skipped' line, so the summary reads the same whether its tests ran "
        "or not:\n  "
        + "\n  ".join(offenders)
        + "\nUse `importlib.util.find_spec(...) is None` in a skipif, and move "
        "any imports that need the package under an `if _HAS_X:` guard."
    )


def test_optional_dep_modules_still_collect_their_tests():
    """The outcome, not the mechanism.

    ⚠ A rewrite that hides these files some other way fails here even if it
    passes the scan above. The counts are lower bounds, deliberately: they are
    meant to catch a file collapsing to zero, not to be re-baselined whenever
    someone adds a test.
    """
    import os
    import subprocess
    import sys

    root = TESTS_DIR.parent
    floors = {
        "test_watcher_serve.py": 40,
        "test_watcher_lock.py": 30,
        "test_dbt_provider.py": 25,
        "test_provider_metadata_and_perf.py": 15,
        "test_runtime_phase6.py": 12,
        "test_v1_108_95.py": 10,
    }
    for name, floor in floors.items():
        out = subprocess.run(
            [sys.executable, "-m", "pytest", f"tests/{name}",
             "--collect-only", "-q", "-p", "no:cacheprovider"],
            cwd=root, capture_output=True, text=True, timeout=300,
            env={**os.environ, "PYTHONPATH": "src"},
        )
        collected = out.stdout.count("::")
        assert collected >= floor, (
            f"{name} collected {collected} items, expected at least {floor}. "
            "A module whose tests vanish at import reports as one skip and "
            f"hides everything it holds.\n{out.stdout[-800:]}"
        )
