"""The JS/TS framework build trees are derived data, like every other one.

⚠⚠ `build`, `.build` and `_build` were all listed and the framework spellings
were not, which is the v1.108.234 duplicate-source-tree defect for the FOURTH
time. `.next/server/**` holds a TRANSPILED copy of the pages the user wrote, so
a Next.js project indexed here got its own source twice -- with the
machine-generated copy competing against the original in ranking.

⚠ Found by reading GitNexus's fix titles against our tree
(`fix(ingestion): ignore emitted Next.js build output`, 2026-08-27).
"""

from __future__ import annotations

import pytest

from jcodemunch_mcp.security import (
    SKIP_DIRECTORIES,
    SKIP_PATTERNS,
    _SKIP_DIRECTORY_NAMES,
)

_FRAMEWORK_TREES = [
    ".next",
    ".nuxt",
    ".output",
    ".svelte-kit",
    ".angular",
    ".turbo",
    ".parcel-cache",
    ".dart_tool",
]


@pytest.mark.parametrize("name", _FRAMEWORK_TREES)
def test_framework_build_tree_reaches_both_walkers(name):
    """⚠⚠ BOTH derived exports, never one.

    `SKIP_DIRECTORIES` is the local walk and `SKIP_PATTERNS` is the GitHub
    indexer. They derive from `_SKIP_DIRECTORY_NAMES`, and the rule recorded
    at that list is that editing a derived export reaches half the product.
    This is the property, so a future entry added to the wrong place fails
    here rather than shipping half-applied.
    """
    assert name in _SKIP_DIRECTORY_NAMES
    assert name in SKIP_DIRECTORIES
    assert f"{name}/" in SKIP_PATTERNS


def test_only_dotted_spellings_were_added():
    """⚠ `out`, `bin`, `obj` and `coverage` are NOT skipped, deliberately.

    Every one of them names a real source directory in real projects. The
    list already carries that risk for `backup` / `old` / `archive` and it
    does not need a fourth instance -- a project that ships `out/` would lose
    it silently, and the whole point of the dotted spellings is that nobody
    ships a package directory called `.next`.
    """
    for risky in ("out", "bin", "obj", "coverage", "public"):
        assert risky not in _SKIP_DIRECTORY_NAMES, (
            f"{risky!r} is an ordinary directory name; skipping it drops real "
            "source. Only unambiguous dotted build trees belong here."
        )
    for name in _FRAMEWORK_TREES:
        assert name.startswith("."), f"{name} is not a dotted spelling"
