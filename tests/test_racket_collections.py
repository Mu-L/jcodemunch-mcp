"""Racket collection paths resolve through `info.rkt`, the way PSR-4 does.

⚠ A Racket collection path names a DIRECTORY that `info.rkt` declares, not a
path in the repo. In the layout the packaging docs prescribe --
`foo-lib/info.rkt` holding `(define collection "foo")` -- `(require foo/bar)`
means `foo-lib/bar.rkt`, and nothing in the specifier says so. Measured
before this existed on two real projects: splitflap, 0 of 70 require edges
resolved; congame, 147 own-collection specifiers unresolved. Every library
file in both read as dead, which is the #548 symptom (78% of the collects tree
dead) on every package-layout repo.

The map's edges are ADDED to `index.imports` beside the collection-path edge
(the #550 shape), so `resolve_specifier`'s 26 call sites keep their contract.
These tests go through `resolve_specifier` for the added edge, because an
edge nothing downstream can resolve is indistinguishable from no edge.
"""
from pathlib import Path

import pytest

from jcodemunch_mcp.parser.imports import (
    augment_racket_collection_edges,
    build_racket_collection_map,
    resolve_specifier,
)
from jcodemunch_mcp.storage.index_store import CodeIndex


def _layout(root: Path, files: dict[str, str]) -> frozenset:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return frozenset(files)


SPLITFLAP = {
    "splitflap/info.rkt": '#lang info\n(define deps \'("splitflap-lib"))\n',
    "splitflap-lib/info.rkt": '#lang info\n(define collection "splitflap")\n',
    "splitflap-lib/main.rkt": "#lang racket/base\n(require splitflap/constructs)\n",
    "splitflap-lib/constructs.rkt": "#lang racket/base\n(require splitflap/private/feed)\n",
    "splitflap-lib/private/feed.rkt": "#lang racket/base\n",
    "splitflap-tests/tests/feed-tests.rkt": "#lang racket/base\n(require splitflap)\n",
}


def test_collection_map_reads_the_declared_name_not_the_directory_name(tmp_path):
    files = _layout(tmp_path, SPLITFLAP)
    cmap = build_racket_collection_map(str(tmp_path), files)
    assert cmap == {"splitflap": ["splitflap-lib"]}


@pytest.mark.parametrize("importer,specifier,expected", [
    ("splitflap-lib/main.rkt", "splitflap/constructs", "splitflap-lib/constructs.rkt"),
    ("splitflap-lib/constructs.rkt", "splitflap/private/feed", "splitflap-lib/private/feed.rkt"),
    # A bare collection name is the collection's main.rkt.
    ("splitflap-tests/tests/feed-tests.rkt", "splitflap", "splitflap-lib/main.rkt"),
], ids=["lib-internal", "nested", "bare-name-is-main"])
def test_added_edge_resolves_to_the_file(tmp_path, importer, specifier, expected):
    files = _layout(tmp_path, SPLITFLAP)
    imports = {importer: [{"specifier": specifier, "names": ["x"]}]}
    assert augment_racket_collection_edges(imports, str(tmp_path), files) == 1
    original, added = imports[importer]
    assert original == {"specifier": specifier, "names": ["x"]}, "the original edge is kept"
    assert added == {"specifier": expected, "names": ["x"]}, "names ride along"
    assert resolve_specifier(added["specifier"], importer, files) == expected
    # Non-vacuity: the original still resolves to nothing, which is the gap.
    assert resolve_specifier(specifier, importer, files) is None


def test_augmentation_is_idempotent(tmp_path):
    """Runs at every CodeIndex construction -- index time and every load."""
    files = _layout(tmp_path, SPLITFLAP)
    imports = {"splitflap-lib/main.rkt": [{"specifier": "splitflap/constructs", "names": []}]}
    assert augment_racket_collection_edges(imports, str(tmp_path), files) == 1
    assert augment_racket_collection_edges(imports, str(tmp_path), files) == 0
    assert len(imports["splitflap-lib/main.rkt"]) == 2


def test_an_installed_collection_gains_no_edge(tmp_path):
    """`(require racket/list)` names an installed collection. The map does not
    know `racket`, so nothing is invented -- an edge to a file that is not
    the one Racket would load is worse than none."""
    files = _layout(tmp_path, SPLITFLAP)
    imports = {"splitflap-lib/main.rkt": [{"specifier": "racket/list", "names": []}]}
    assert augment_racket_collection_edges(imports, str(tmp_path), files) == 0


def test_a_missing_file_in_a_known_collection_gains_no_edge(tmp_path):
    files = _layout(tmp_path, SPLITFLAP)
    imports = {"splitflap-lib/main.rkt": [{"specifier": "splitflap/nope", "names": []}]}
    assert augment_racket_collection_edges(imports, str(tmp_path), files) == 0


def test_string_and_relative_requires_are_left_alone(tmp_path):
    files = _layout(tmp_path, SPLITFLAP)
    imports = {"splitflap-lib/main.rkt": [
        {"specifier": "constructs.rkt", "names": []},
        {"specifier": "../splitflap-lib/constructs.rkt", "names": []},
    ]}
    assert augment_racket_collection_edges(imports, str(tmp_path), files) == 0


def test_several_directories_may_declare_one_collection(tmp_path):
    """⚠ Racket SPLICES them: congame-cli, congame-core and congame-doc all
    declare "congame", and `congame/components/study` lives in one of them.
    A name -> dir map would keep one and lose the rest."""
    files = _layout(tmp_path, {
        "congame-cli/info.rkt": '(define collection "congame")\n',
        "congame-cli/main.rkt": "#lang racket/base\n",
        "congame-core/info.rkt": '(define collection "congame")\n',
        "congame-core/components/study.rkt": "#lang racket/base\n",
        "congame-web/info.rkt": '(define collection "congame-web")\n',
        "congame-web/pages.rkt": "#lang racket/base\n(require congame/components/study)\n",
    })
    cmap = build_racket_collection_map(str(tmp_path), files)
    assert cmap["congame"] == ["congame-cli", "congame-core"]
    imports = {"congame-web/pages.rkt": [{"specifier": "congame/components/study", "names": []}]}
    assert augment_racket_collection_edges(imports, str(tmp_path), files) == 1
    assert imports["congame-web/pages.rkt"][1]["specifier"] == "congame-core/components/study.rkt"


def test_a_multi_package_makes_every_subdirectory_a_collection(tmp_path):
    files = _layout(tmp_path, {
        "info.rkt": "#lang info\n(define collection 'multi)\n",
        "foo/a.rkt": "#lang racket/base\n(require bar/b)\n",
        "bar/b.rkt": "#lang racket/base\n",
        "README.md": "",
    })
    cmap = build_racket_collection_map(str(tmp_path), files)
    assert cmap == {"foo": ["foo"], "bar": ["bar"]}
    imports = {"foo/a.rkt": [{"specifier": "bar/b", "names": []}]}
    assert augment_racket_collection_edges(imports, str(tmp_path), files) == 1
    assert imports["foo/a.rkt"][1]["specifier"] == "bar/b.rkt"


def test_quote_multi_spelling_is_read_too(tmp_path):
    files = _layout(tmp_path, {
        "info.rkt": "(define collection (quote multi))\n",
        "foo/a.rkt": "#lang racket/base\n",
    })
    assert build_racket_collection_map(str(tmp_path), files) == {"foo": ["foo"]}


def test_the_map_is_rebuilt_when_an_info_rkt_appears(tmp_path):
    """The cache key includes the info.rkt set, so adding a package is seen
    without a restart -- `build_psr4_map` caches by root alone."""
    files = _layout(tmp_path, {"a/x.rkt": "#lang racket/base\n"})
    assert build_racket_collection_map(str(tmp_path), files) == {}
    files = _layout(tmp_path, {"a/info.rkt": '(define collection "a")\n', "a/x.rkt": ""})
    assert build_racket_collection_map(str(tmp_path), files) == {"a": ["a"]}


# ── wiring: the index carries the edges without any consumer changing ──────

def _index(tmp_path, files, imports, languages):
    return CodeIndex(
        repo="local/t", owner="local", name="t", indexed_at="", symbols=[], source_files=sorted(files),
        source_root=str(tmp_path), imports=imports, languages=languages,
    )


def test_code_index_construction_adds_the_edges(tmp_path):
    """Runs in `__post_init__`, so an index built by the indexer carries the
    edges into its save and an older index gains them on load."""
    files = _layout(tmp_path, SPLITFLAP)
    idx = _index(tmp_path, files,
                 {"splitflap-lib/main.rkt": [{"specifier": "splitflap/constructs", "names": []}]},
                 {"racket": 5})
    specs = [e["specifier"] for e in idx.imports["splitflap-lib/main.rkt"]]
    assert specs == ["splitflap/constructs", "splitflap-lib/constructs.rkt"]


def test_code_index_without_racket_does_not_read_info_files(tmp_path):
    files = _layout(tmp_path, SPLITFLAP)
    idx = _index(tmp_path, files,
                 {"splitflap-lib/main.rkt": [{"specifier": "splitflap/constructs", "names": []}]},
                 {"python": 5})
    assert len(idx.imports["splitflap-lib/main.rkt"]) == 1


def test_code_index_without_a_source_root_is_untouched(tmp_path):
    """A remote (GitHub) index has no source_root and no disk to read."""
    files = _layout(tmp_path, SPLITFLAP)
    idx = CodeIndex(
        repo="o/r", owner="o", name="r", indexed_at="", symbols=[], source_files=sorted(files),
        imports={"splitflap-lib/main.rkt": [{"specifier": "splitflap/constructs", "names": []}]},
        languages={"racket": 5},
    )
    assert len(idx.imports["splitflap-lib/main.rkt"]) == 1
