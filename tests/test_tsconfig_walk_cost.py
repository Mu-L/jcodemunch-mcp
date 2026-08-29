"""tsconfig discovery must not walk build trees, and must not re-walk per edit.

⚠⚠ Two independent defects on one path (#557, @Ticki84, who cloned the repo and
instrumented his own long-running `watch-all` process to find them).

1. `_TSCONFIG_SKIP_DIRS` was **the fourth copy of a skip list in this tree, and
   the only one deriving from nothing.** `security._SKIP_DIRECTORY_NAMES` is the
   authority -- CLAUDE.md says so and two other exports already derive from it --
   but this set was hand-maintained beside it and had never heard of Rust's
   `target`. So the walk descended into a Tauri project's build directory on
   EVERY watcher event: **13.58s of a 13.75s reindex, against 0.27s once
   `target` was excluded.**

2. `index_folder` evicted the alias-map cache **unconditionally**, so every
   watcher-driven single-file re-index paid the discovery walk again. **A cache
   invalidated on every write is not a cache**, and it hid behind the walk's own
   cost rather than showing up as one.

⚠⚠ **Adding `"target"` to the list was the reported fix and would have been the
wrong one** -- "fix the call site, leave the mechanism", our own standing lesson.
Deriving from the authority brings every build-tree spelling it already knows and
means the next one needs no edit here. `test_the_authority_is_the_source` is what
keeps that true: it fails if someone re-hardcodes the set.

⚠ This also corrects our own instrument. The v1.108.304 phase breakdown blamed
`save=`, and the reporter's last comment explains why: that phase includes
rebuilding the in-memory `CodeIndex` after the SQLite transaction, and the
reconstruction is what triggers the walk. **A phase boundary drawn at the wrong
place names the wrong subsystem confidently.**
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jcodemunch_mcp.parser.imports import (
    _alias_map_cache,
    _load_tsconfig_aliases,
    _tsconfig_skip_dirs,
)
from jcodemunch_mcp.tools.index_folder import _tsconfig_touched


# ---------------------------------------------------------------------------
# 1. The skip set comes from the authority
# ---------------------------------------------------------------------------

class TestSkipSetDerivesFromTheAuthority:

    def test_the_authority_is_the_source(self):
        """⚠⚠ Fails if the set is ever re-hardcoded. That is the actual fix --
        `target` being present is only its first visible consequence."""
        from jcodemunch_mcp.security import _SKIP_DIRECTORY_NAMES

        skip = _tsconfig_skip_dirs()
        missing = [n for n in _SKIP_DIRECTORY_NAMES if n not in skip]
        assert not missing, (
            f"names the authority knows but tsconfig discovery does not: {missing}"
        )

    @pytest.mark.parametrize(
        "name", ["target", "_build", ".gradle", "DerivedData", "node_modules"]
    )
    def test_build_trees_are_skipped(self, name):
        assert name in _tsconfig_skip_dirs()

    def test_the_tsconfig_specific_extras_survive_the_union(self):
        """⚠ UNION, never replacement. `out` is deliberately absent from the
        authority (CLAUDE.md: "DOTTED ONLY" -- it names a real source directory
        for the INDEXING walk) but has been skipped for tsconfig discovery for
        this function's whole life. Removing a skip is the one direction this
        change must not take."""
        skip = _tsconfig_skip_dirs()
        for extra in ("out", ".cache", ".next", ".nuxt", ".svelte-kit",
                      ".turbo", ".vercel"):
            assert extra in skip, extra

    def test_ordinary_source_dirs_are_not_skipped(self):
        """The union must not become a denial of the repo itself."""
        skip = _tsconfig_skip_dirs()
        for live in ("src", "app", "packages", "apps", "lib", "components"):
            assert live not in skip, live


# ---------------------------------------------------------------------------
# 2. The walk, end to end
# ---------------------------------------------------------------------------

def _rust_ts_repo(root: Path, *, target_dirs: int = 400) -> Path:
    (root / "src").mkdir()
    (root / "src" / "main.ts").write_text("export const x = 1\n", encoding="utf-8")
    (root / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": {"paths": {"@/*": ["src/*"]}}}),
        encoding="utf-8",
    )
    # A tsconfig buried in the build tree, with aliases that must NEVER be read.
    poisoned = root / "target" / "debug" / "build" / "crate-0001" / "out"
    poisoned.mkdir(parents=True)
    (poisoned / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": {"paths": {"@poison/*": ["nowhere/*"]}}}),
        encoding="utf-8",
    )
    for i in range(target_dirs):
        d = root / "target" / "debug" / "build" / f"crate-{i:04d}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "output").write_bytes(b"")
    return root


class TestTheWalkDoesNotEnterBuildTrees:

    @pytest.fixture
    def repo(self, tmp_path):
        _rust_ts_repo(tmp_path)
        _alias_map_cache.clear()
        yield tmp_path
        _alias_map_cache.clear()

    def test_a_tsconfig_inside_target_is_never_ingested(self, repo):
        """⚠⚠ The behavioural assertion, and it is stronger than a timing one:
        a poisoned tsconfig under `target/` would inject its aliases into the
        real map. Absent aliases prove the walk did not go there, on any machine,
        at any speed."""
        aliases = _load_tsconfig_aliases(str(repo))
        assert aliases == {"@/*": ["src/*"]}, aliases
        assert "@poison/*" not in aliases

    def test_the_real_tsconfig_is_still_found(self, repo):
        """Non-vacuity: a walk that skipped everything would also pass above."""
        assert _load_tsconfig_aliases(str(repo)) == {"@/*": ["src/*"]}


# ---------------------------------------------------------------------------
# 3. An ordinary edit must not invalidate the alias cache
# ---------------------------------------------------------------------------

class TestTheAliasCacheSurvivesAnOrdinaryEdit:
    """⚠ Asserted through `_tsconfig_touched`, the predicate `index_folder`
    actually consults, rather than by timing a re-index -- a timing test here
    would be measuring the walk we just made fast."""

    @pytest.mark.parametrize("path", [
        "src/main.ts", "src/App.tsx", "lib/util.js",
        "package.json", "Cargo.toml", "README.md",
    ])
    def test_an_ordinary_edit_does_not_evict(self, path):
        assert _tsconfig_touched([path]) is False

    @pytest.mark.parametrize("path", [
        "tsconfig.json", "jsconfig.json", "tsconfig.build.json",
        "apps/web/tsconfig.json", r"C:\repo\tsconfig.json",
    ])
    def test_a_config_edit_does_evict(self, path):
        assert _tsconfig_touched([path]) is True

    def test_a_mixed_batch_evicts(self):
        """One config in the batch is enough -- the map may now be stale."""
        assert _tsconfig_touched(["src/a.ts", "tsconfig.json"]) is True

    def test_an_unknown_batch_is_not_a_reason_to_keep(self):
        """⚠ `None` means the run did not tell us what it touched, which is
        UNKNOWN and must evict. `index_folder` treats it that way; this pins the
        helper's half of that contract."""
        assert _tsconfig_touched(None) is False
