"""Tied scores rank by symbol id, not by the order the index was walked.

Harness F-13 (2026-09-03): the same pinned corpora gave different jCodeMunch
token totals on Windows and on CI. One of the three causes was here: the
bounded ranking heap broke ties by ENCOUNTER order, which is `os.walk` order,
which is directory order on NTFS and hash order on ext4. gin's "context bind"
has five candidates at exactly 10.202, so the three fetched depended on the
filesystem. The heap now carries the (inverted) symbol id as its tiebreak and
the final sort is (-score, id).

The non-vacuity arm: run the same query over the same index with its symbol
list REVERSED. Before the fix the two calls returned different tied symbols
(verified by reverting the tiebreak: 5 of 5 ids moved).
"""

from __future__ import annotations

from jcodemunch_mcp.storage import IndexStore
from jcodemunch_mcp.tools.index_folder import index_folder
from jcodemunch_mcp.tools.search_symbols import search_symbols

N_TIED = 12


def _seed(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    # Twelve files, each with one function of the SAME name and the same body,
    # so every candidate for "widget" scores identically. Names are chosen so
    # a case-insensitive or directory-order walk disagrees with byte order.
    for i, stem in enumerate(["zeta", "Alpha", "mid", "beta", "Omega", "gamma", "kappa", "Iota", "eta", "delta", "Theta", "chi"]):
        (src / f"{stem}.py").write_text(f"def widget():\n    '''widget {i}'''\n    return {i}\n", encoding="utf-8")
    idx = index_folder(path=str(tmp_path), use_ai_summaries=False, storage_path=str(tmp_path / "idx"))
    return idx["repo"], str(tmp_path / "idx")


def _ids(repo, storage, k):
    r = search_symbols(repo=repo, query="widget", max_results=k, storage_path=storage, detail_level="compact")
    return [x["id"] for x in r["results"]]


def test_top_k_among_ties_is_the_smallest_ids_in_byte_order(tmp_path):
    repo, storage = _seed(tmp_path)
    got = _ids(repo, storage, 3)
    assert len(got) == 3
    everything = sorted(_ids(repo, storage, N_TIED))
    assert len(everything) == N_TIED, "all twelve tied candidates must be reachable"
    assert got == everything[:3], f"top-3 must be the byte-smallest ids among the tie, got {got}"


def test_reversing_the_index_walk_order_does_not_change_the_answer(tmp_path, monkeypatch):
    repo, storage = _seed(tmp_path)
    forward = _ids(repo, storage, 3)

    real = IndexStore.load_index

    def reversed_load(self, owner, name, branch=""):
        index = real(self, owner, name, branch)
        if index is not None:
            index.symbols = list(reversed(index.symbols))
        return index

    monkeypatch.setattr(IndexStore, "load_index", reversed_load)
    backward = _ids(repo, storage, 3)
    assert backward == forward, f"walk order leaked into the ranking: {forward} vs {backward}"
