"""A build tree is derived data in every spelling it is written.

`build` and `.build` were both listed as skip directories from early on.
`_build` was not -- and that is the spelling Elixir/Mix, Sphinx and Dune use.
We index Elixir.

⚠⚠ **This is the same defect as `backup`/`old`/`archive` (v1.108.234), not a
new one.** `mix` copies dependency SOURCES into `_build`, so an Elixir project
indexed here got every dependency symbol twice, and the copies then competed
with the originals in ranking. The v1.108.234 entry describes that outcome
exactly. The only reason this survived is that nobody wrote down the third
spelling.

⚠ The tests assert the PROPERTY -- that a build tree is skipped however it is
spelled, through both derived exports -- rather than pinning the list contents.
A rewrite that excludes build trees some other way passes; a list that quietly
drops one fails.

⚠ Found by reading a competitor's fix titles against our tree
(`fix(ingest): skip _build, the underscore spelling of a build tree`). Third
time that probe has paid, after the Gini double-count and the byte-mass basis.
"""

from __future__ import annotations

import pytest

from jcodemunch_mcp import security


# Every spelling of a build tree we claim to exclude. Kept as a property list:
# adding a spelling here is the whole cost of covering a new toolchain.
BUILD_TREE_SPELLINGS = ["build", ".build", "_build"]


@pytest.mark.parametrize("name", BUILD_TREE_SPELLINGS)
def test_build_tree_is_skipped_in_every_spelling(name):
    """The local walk (index_folder) must exclude it."""
    assert name in security.SKIP_DIRECTORIES, (
        f"'{name}' is a build tree and is not excluded from the local walk. "
        "A build tree holds derived data, and toolchains that copy dependency "
        "SOURCES into it (mix) get every dependency symbol indexed twice."
    )


@pytest.mark.parametrize("name", BUILD_TREE_SPELLINGS)
def test_both_derived_exports_carry_it(name):
    """index_repo reads SKIP_PATTERNS, index_folder reads SKIP_DIRECTORIES.

    ⚠ Both derive from `_SKIP_DIRECTORY_NAMES`, so a spelling added to the
    canonical list reaches both. This fails if someone edits a derived export
    directly -- which the module explicitly tells them not to do.
    """
    assert name + "/" in security.SKIP_PATTERNS, (
        f"'{name}/' missing from SKIP_PATTERNS: the GitHub indexer would still "
        "walk into it even though the local walk skips it."
    )


def test_the_underscore_spelling_is_the_one_that_was_missing():
    """A regression pin with its reason attached.

    Not redundant with the parametrized cases: those would keep passing if
    someone removed `_build` and this list at the same time. This names the
    specific spelling and why it matters.
    """
    assert "_build" in security.SKIP_DIRECTORIES
    assert "_build/" in security.SKIP_PATTERNS


def test_exclusion_is_still_overridable_per_project(monkeypatch):
    """⚠ These are ordinary words and CAN name a real package.

    `exclude_skip_directories` is the escape hatch the module documents for
    exactly that case, and it must keep working for the new entry -- otherwise
    a project that genuinely ships a `_build` module has no way back.

    ⚠ Patches the resolver rather than passing config: `get_skip_directories`
    reads the project's settings, and a test must never touch the developer's
    real config (Practice 8 / #411).
    """
    monkeypatch.setattr(
        security, "_excluded_skip_directories", lambda repo=None: {"_build"}
    )
    kept = security.get_skip_directories()
    assert "_build" not in kept
    assert "build" in kept, "excluding one spelling must not drop the others"
