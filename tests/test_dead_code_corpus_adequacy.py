"""#566 + #569 — what `find_dead_code`'s confidence 1.0 is allowed to mean.

Two issues, one property: an absence claim may not be published more strongly
than the corpus that produced it can support.

⚠⚠ **The non-vacuity anchor of this file is
``test_qualified_path_is_not_the_loaders_own_package``.** The first working
draft of the scanner matched any appearance of ``__path__``, which made
``pkgutil.iter_modules(schemas_pkg.__path__)`` in a TEST file declare the test
directory self-enumerating — 502 files revived, every real finding under
``tests/`` suppressed, and every assertion in this file still green. A fix for a
false positive that installs a false negative is the worse trade, and only that
test can see it.
"""

from __future__ import annotations

import pytest

from jcodemunch_mcp.tools._corpus_adequacy import (
    UNPROVEN_CEILING,
    CorpusAdequacy,
    assess_corpus,
)
from jcodemunch_mcp.tools._runtime_discovery import discover_dynamic_packages
from jcodemunch_mcp.tools.find_dead_code import find_dead_code
from jcodemunch_mcp.tools.index_folder import index_folder


# ---------------------------------------------------------------------------
# Fakes. `assess_corpus` reads an index and nothing else, so the fake is the
# index — a real one cannot be put into the `stale` or `withheld` states these
# assert without a git checkout and a 512 KB file.
# ---------------------------------------------------------------------------

class _FakeIndex:
    def __init__(self, *, source_root=None, git_head=None, coverage=None):
        self.source_root = source_root
        self.git_head = git_head
        self.indexed_at = "2026-09-01T00:00:00"
        self.coverage = coverage if coverage is not None else {"complete": True}
        self.index_version = 1


def _plain_repo(tmp_path):
    """A folder repo: real index, real store, no git and no withheld files."""
    src = tmp_path / "src"
    src.mkdir()
    store = tmp_path / "store"
    store.mkdir()
    return src, store


def _index(src, store):
    r = index_folder(str(src), use_ai_summaries=False, storage_path=str(store))
    assert r["success"] is True
    return r["repo"], str(store)


# ---------------------------------------------------------------------------
# #569 — runtime-discovered packages
# ---------------------------------------------------------------------------

_REGISTRY = (
    "import importlib\n"
    "import pkgutil\n"
    "\n"
    "def _discover():\n"
    "    from . import __path__ as pkg_path, __name__ as pkg_name\n"
    "    for m in pkgutil.iter_modules(pkg_path):\n"
    "        importlib.import_module(f'{pkg_name}.{m.name}')\n"
)


def _plugin_pkg(src, *, registry_body=_REGISTRY, extra=None):
    pkg = src / "plugins"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "registry.py").write_text(registry_body)
    (pkg / "alpha.py").write_text("ENCODING_ID = 'alpha'\n")
    (pkg / "beta.py").write_text("ENCODING_ID = 'beta'\n")
    (src / "main.py").write_text(
        "from plugins import registry\n\n"
        "if __name__ == '__main__':\n    registry._discover()\n"
    )
    if extra:
        extra(src)
    return pkg


class TestRuntimeDiscovery:
    def test_own_package_enumeration_revives_siblings(self, tmp_path):
        src, store = _plain_repo(tmp_path)
        _plugin_pkg(src)
        repo, sp = _index(src, store)

        r = find_dead_code(repo, granularity="file", min_confidence=0.5,
                           storage_path=sp)
        dead = {d["file"] for d in r["dead_files"]}
        assert not any(f.endswith("plugins/alpha.py") for f in dead), dead
        assert not any(f.endswith("plugins/beta.py") for f in dead), dead
        assert r["runtime_discovered_count"] >= 2
        assert any(
            d.endswith("plugins") for d in r["runtime_discovered_packages"]
        )

    def test_qualified_path_is_not_the_loaders_own_package(self, tmp_path):
        """⚠⚠ The overreach guard. See this module's docstring.

        A loader that walks ANOTHER package's ``__path__`` says nothing about
        its own directory. Reviving that directory suppresses every real
        finding in it, which is a worse defect than the one being fixed.
        """
        src, store = _plain_repo(tmp_path)
        pkg = src / "plugins"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "alpha.py").write_text("X = 1\n")
        scanner_dir = src / "scanners"
        scanner_dir.mkdir()
        (scanner_dir / "__init__.py").write_text("")
        (scanner_dir / "walker.py").write_text(
            "import importlib\n"
            "import pkgutil\n"
            "import plugins as target\n"
            "\n"
            "def go():\n"
            "    for m in pkgutil.iter_modules(target.__path__):\n"
            "        importlib.import_module('plugins.' + m.name)\n"
        )
        (scanner_dir / "orphan.py").write_text("def nobody_calls_me():\n    pass\n")
        repo, sp = _index(src, store)

        from jcodemunch_mcp.storage import IndexStore
        from jcodemunch_mcp.tools._utils import resolve_repo

        owner, name = resolve_repo(repo, sp)
        st = IndexStore(base_path=sp)
        d = discover_dynamic_packages(st.load_index(owner, name), st, owner, name)

        assert not any(f.endswith("scanners/orphan.py") for f in d.roots), d.roots
        assert any(f.endswith("scanners/walker.py") for f in d.unresolved)

    def test_enumeration_without_dynamic_import_is_not_a_load_path(self, tmp_path):
        src, store = _plain_repo(tmp_path)
        _plugin_pkg(
            src,
            registry_body=(
                "import pkgutil\n"
                "\n"
                "def names():\n"
                "    from . import __path__ as pkg_path\n"
                "    return [m.name for m in pkgutil.iter_modules(pkg_path)]\n"
            ),
        )
        repo, sp = _index(src, store)
        r = find_dead_code(repo, granularity="file", min_confidence=0.5,
                           storage_path=sp)
        assert r["runtime_discovered_count"] == 0
        assert any(d["file"].endswith("plugins/alpha.py") for d in r["dead_files"])

    def test_walk_packages_reaches_subpackages_and_iter_modules_does_not(
        self, tmp_path
    ):
        def _nested(src):
            sub = src / "plugins" / "nested"
            sub.mkdir()
            (sub / "__init__.py").write_text("")
            (sub / "deep.py").write_text("Y = 1\n")

        src, store = _plain_repo(tmp_path)
        _plugin_pkg(src, extra=_nested)
        repo, sp = _index(src, store)
        flat = find_dead_code(repo, granularity="file", min_confidence=0.5,
                              storage_path=sp)
        assert any(d["file"].endswith("nested/deep.py") for d in flat["dead_files"])

        (src / "plugins" / "registry.py").write_text(
            _REGISTRY.replace("iter_modules", "walk_packages")
        )
        repo2, sp2 = _index(src, tmp_path / "store2")
        deep = find_dead_code(repo2, granularity="file", min_confidence=0.5,
                              storage_path=sp2)
        assert not any(
            d["file"].endswith("nested/deep.py") for d in deep["dead_files"]
        )


# ---------------------------------------------------------------------------
# #566 — corpus adequacy
# ---------------------------------------------------------------------------

class TestCorpusAdequacy:
    def test_stale_index_caps_and_names_the_cause(self):
        a = assess_corpus(_FakeIndex(source_root=".", git_head="a" * 40))
        # `.` is a real directory, so the probe runs; this tree's HEAD is not
        # forty 'a's, so the comparison is made and fails.
        assert a.index_freshness in ("stale", "unknown")
        assert not a.adequate
        assert a.ceiling == UNPROVEN_CEILING
        assert "capped" in a.warning()

    def test_withheld_files_cap(self):
        a = assess_corpus(_FakeIndex(coverage={
            "complete": False, "withheld": {"too_large": 1},
        }))
        assert "withheld_files" in a.blockers
        assert a.ceiling == UNPROVEN_CEILING
        assert "too_large" in a.warning()

    def test_incomplete_without_withheld_still_caps(self):
        a = assess_corpus(_FakeIndex(coverage={"complete": False}))
        assert "corpus_incomplete" in a.blockers

    def test_unknown_completeness_is_not_incompleteness(self):
        """Tri-state. An index predating the coverage contract is not a defect."""
        a = assess_corpus(_FakeIndex(coverage={"files_indexed": 3}))
        assert "corpus_incomplete" not in a.blockers
        assert "withheld_files" not in a.blockers

    def test_no_local_source_root_does_not_cap(self):
        """An `index_repo` snapshot has no tree to compare and is not suspect."""
        a = assess_corpus(_FakeIndex(source_root=None))
        assert a.index_freshness == "no_source_root"
        assert a.adequate
        assert a.ceiling == 1.0
        assert a.warning() is None

    def test_extra_blockers_reach_the_verdict(self):
        a = assess_corpus(
            _FakeIndex(), extra_blockers=["runtime_discovery_unresolved"]
        )
        assert not a.adequate
        assert "enumerates a package at import time" in a.warning()

    def test_clean_corpus_publishes_a_proof(self, tmp_path):
        src, store = _plain_repo(tmp_path)
        (src / "main.py").write_text("if __name__ == '__main__':\n    pass\n")
        (src / "orphan.py").write_text("def f():\n    return 1\n")
        repo, sp = _index(src, store)

        r = find_dead_code(repo, granularity="file", min_confidence=0.8,
                           storage_path=sp)
        assert r["corpus_adequacy"]["adequate"] is True
        assert "signal_warning" not in r
        orphan = [d for d in r["dead_files"] if d["file"].endswith("orphan.py")]
        assert orphan and orphan[0]["confidence"] == 1.0
        assert "confidence_capped_by" not in orphan[0]


class TestCappedResponseShape:
    def test_cap_keeps_both_numbers_and_warns(self, tmp_path, monkeypatch):
        src, store = _plain_repo(tmp_path)
        (src / "main.py").write_text("if __name__ == '__main__':\n    pass\n")
        (src / "orphan.py").write_text("def f():\n    return 1\n")
        repo, sp = _index(src, store)

        monkeypatch.setattr(
            "jcodemunch_mcp.tools.find_dead_code.assess_corpus",
            lambda index, **kw: CorpusAdequacy(
                "stale", {}, True, ["stale_index"]
            ),
        )
        r = find_dead_code(repo, granularity="file", min_confidence=0.5,
                           storage_path=sp)
        orphan = [d for d in r["dead_files"] if d["file"].endswith("orphan.py")]
        assert orphan, r["dead_files"]
        assert orphan[0]["confidence"] == UNPROVEN_CEILING
        assert orphan[0]["uncapped_confidence"] == 1.0
        assert orphan[0]["confidence_capped_by"] == ["stale_index"]
        assert "signal_warning" in r
        assert r["corpus_adequacy"]["adequate"] is False

    def test_default_threshold_refuses_rather_than_publishing(
        self, tmp_path, monkeypatch
    ):
        """⚠ A capped run returns fewer findings, so the WARNING is the answer.

        An empty list read alone is the `dead_code_pct: 0.0` shape of #559 seen
        from the other side: an admission that nothing was established, rendered
        as a clean bill of health.
        """
        src, store = _plain_repo(tmp_path)
        (src / "main.py").write_text("if __name__ == '__main__':\n    pass\n")
        (src / "orphan.py").write_text("def f():\n    return 1\n")
        repo, sp = _index(src, store)

        monkeypatch.setattr(
            "jcodemunch_mcp.tools.find_dead_code.assess_corpus",
            lambda index, **kw: CorpusAdequacy(
                "stale", {}, True, ["stale_index"]
            ),
        )
        r = find_dead_code(repo, granularity="file", storage_path=sp)
        assert r["dead_files"] == []
        assert r["signal_warning"]


class TestSecondCallSite:
    def test_get_dead_code_v2_shares_the_runtime_roots(self, tmp_path):
        """The mechanism, not the reported call site.

        Signal 1 in v2 is `unreachable_file` off the same import graph, so a
        package enumerated at runtime votes its modules dead there for the same
        invisible-edge reason.
        """
        from jcodemunch_mcp.tools.get_dead_code_v2 import get_dead_code_v2

        src, store = _plain_repo(tmp_path)
        pkg = _plugin_pkg(src)
        (pkg / "alpha.py").write_text("def alpha_handler():\n    return 1\n")
        repo, sp = _index(src, store)

        r = get_dead_code_v2(repo=repo, min_confidence=0.33, storage_path=sp)
        dead = {s.get("file", "") for s in r["dead_symbols"]}
        assert not any(f.endswith("plugins/alpha.py") for f in dead), dead


class TestDestructiveSurface:
    """⚠⚠ `check_delete_safe` is the same defect where it can destroy work.

    Its "no refs at all" fallback reaches `safe_to_delete` REGARDLESS of
    dead-code confidence and then floors the confidence at 0.85, so capping
    `find_dead_code` alone left a delete certified over a corpus that could not
    support it. The twelve `encoding/schemas` encoders of #569 have no refs at
    all, so each one graded safe at 0.85.
    """

    @staticmethod
    def _repo(tmp_path):
        src, store = _plain_repo(tmp_path)
        (src / "main.py").write_text("if __name__ == '__main__':\n    pass\n")
        (src / "orphan.py").write_text("def lonely():\n    return 1\n")
        return _index(src, store)

    def test_inadequate_corpus_never_certifies_a_delete(self, tmp_path, monkeypatch):
        from jcodemunch_mcp.tools.check_delete_safe import check_delete_safe

        repo, sp = self._repo(tmp_path)
        clean = check_delete_safe("lonely", repo=repo, storage_path=sp) \
            if False else check_delete_safe(repo, "lonely", storage_path=sp)
        assert clean["verdict"] == "safe_to_delete"

        monkeypatch.setattr(
            "jcodemunch_mcp.tools.check_delete_safe.assess_corpus",
            lambda index, **kw: CorpusAdequacy("stale", {}, True, ["stale_index"]),
            raising=False,
        )
        capped = check_delete_safe(repo, "lonely", storage_path=sp)
        assert capped["verdict"] == "corpus_inadequate"
        assert capped["confidence"] <= UNPROVEN_CEILING
        assert capped["stop_rule"]["terminal"] is False
        assert any(
            g["action"] == "re-index this repo"
            for g in capped["stop_rule"]["would_change_verdict"]
        )
        assert capped["signal_warning"]

    def test_a_blocking_verdict_survives_an_inadequate_corpus(
        self, tmp_path, monkeypatch
    ):
        """Positive evidence is not unfound by a thin corpus."""
        src, store = _plain_repo(tmp_path)
        (src / "main.py").write_text(
            "from lib import used\n\nif __name__ == '__main__':\n    used()\n"
        )
        (src / "lib.py").write_text("def used():\n    return 1\n")
        repo, sp = _index(src, store)

        from jcodemunch_mcp.tools.check_delete_safe import check_delete_safe

        monkeypatch.setattr(
            "jcodemunch_mcp.tools.check_delete_safe.assess_corpus",
            lambda index, **kw: CorpusAdequacy("stale", {}, True, ["stale_index"]),
            raising=False,
        )
        r = check_delete_safe(repo, "used", storage_path=sp)
        assert r["verdict"] != "corpus_inadequate"
        assert r["corpus_adequacy"]["adequate"] is False


def test_corpus_inadequate_is_a_classified_verdict():
    """An unclassified verdict reaches the user as 'review manually'."""
    from jcodemunch_mcp.tools._stop_rule import known_verdicts

    assert "corpus_inadequate" in known_verdicts("check_delete_safe")


@pytest.mark.parametrize("blocker", [
    "stale_index", "index_freshness_unknown", "withheld_files",
    "corpus_incomplete", "runtime_discovery_unresolved",
])
def test_every_blocker_has_a_sentence(blocker):
    """A blocker with no prose reaches the user as a bare token."""
    a = CorpusAdequacy("stale", {"too_large": 1}, False, [blocker])
    w = a.warning()
    assert w and "; " not in w.split(": ", 1)[1].rsplit(". Confidence", 1)[0]
