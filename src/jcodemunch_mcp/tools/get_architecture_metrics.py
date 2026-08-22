"""get_architecture_metrics — structural concentration & dependency depth in one call.

Three architecture lenses the AST call graph doesn't surface, computed over the
file-level import graph the index already builds:

  concentration (Gini)  How EVENLY is the codebase's mass distributed? The Gini
                        coefficient (0 = perfectly even, ->1 = hoarded in a few
                        files) over per-file symbol count, byte mass (the source
                        each file's symbol spans MERGED, so a class and its
                        methods are not counted twice), fan-in (importers), and
                        fan-out (imports), plus the top
                        concentrators. Answers "is complexity/coupling piling up
                        in a handful of files?" — which a hotspot list (the peaks)
                        can't tell you.
  depth (Lakos)         How DEEP is the dependency stack? Longest dependency chain
                        and the level distribution over the cycle-condensed
                        dependency DAG (Lakos levelization).
  modularity (DSM)      The insight a Design Structure Matrix highlights, without
                        the N*N matrix: how many independent clusters the graph
                        splits into, and the "back-edges" (cycle-participating
                        import edges) that are the hidden coupling a clean layering
                        wouldn't have.

One read-only tool — the compact composite of what a Gini tool + a dependency-depth
tool + a DSM tool report separately. Layering-VIOLATION detail is not duplicated
here (use get_layer_violations); the cycles themselves come from
get_dependency_cycles; per-module Ca/Ce from get_coupling_metrics. Does NOT touch
the health-radar composite, so observatory scores stay comparable.
"""

from __future__ import annotations

import logging
import time
from collections import Counter, deque
from typing import Optional

from ..storage import IndexStore
from ._utils import file_byte_mass, index_status_to_tool_error, resolve_repo
from .get_dependency_cycles import _find_cycles
from .get_dependency_graph import _build_adjacency

logger = logging.getLogger(__name__)


def _gini(values: list[float]) -> float:
    """Gini coefficient of a list of non-negative values, in [0, 1).

    0.0 = perfectly even; higher = more concentrated. Empty or all-zero -> 0.0.
    Standard sorted-rank formula: G = (2*sum(i*x_i))/(n*sum(x)) - (n+1)/n.
    """
    xs = sorted(float(v) for v in values if v is not None and v >= 0)
    n = len(xs)
    if n == 0:
        return 0.0
    total = sum(xs)
    if total <= 0:
        return 0.0
    cum = sum(i * x for i, x in enumerate(xs, start=1))
    return round((2.0 * cum) / (n * total) - (n + 1.0) / n, 4)


def _top(counter: dict, files: list[str], n: int) -> list[dict]:
    ranked = sorted(files, key=lambda f: (-int(counter.get(f, 0)), f))
    return [{"file": f, "value": int(counter.get(f, 0))} for f in ranked[:n] if counter.get(f, 0)]


def _weakly_connected(nodes: set[str], adj: dict[str, list[str]]) -> tuple[int, int]:
    """Return (cluster_count, largest_cluster_size) over the undirected graph."""
    undirected: dict[str, set[str]] = {}
    for u, tgts in adj.items():
        for v in tgts:
            undirected.setdefault(u, set()).add(v)
            undirected.setdefault(v, set()).add(u)
    seen: set[str] = set()
    clusters = 0
    largest = 0
    for start in nodes:
        if start in seen or start not in undirected:
            continue
        clusters += 1
        size = 0
        stack = [start]
        seen.add(start)
        while stack:
            node = stack.pop()
            size += 1
            for nb in undirected.get(node, ()):
                if nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        largest = max(largest, size)
    return clusters, largest


def get_architecture_metrics(
    repo: str,
    top_n: int = 10,
    storage_path: Optional[str] = None,
) -> dict:
    """Structural concentration (Gini), dependency depth (Lakos), and modularity.

    Args:
        repo:         Repository identifier.
        top_n:        Number of top concentrators to list per Gini metric (default 10).
        storage_path: Optional index storage override.

    Returns:
        ``{repo, concentration, depth, modularity, summary, _meta}`` or ``{error}``.
    """
    t0 = time.perf_counter()
    if top_n < 1:
        return {"error": "top_n must be >= 1"}

    try:
        owner, name = resolve_repo(repo, storage_path)
    except ValueError as e:
        return {"error": str(e)}

    store = IndexStore(base_path=storage_path)
    index = store.load_index(owner, name)
    if not index:
        return index_status_to_tool_error(store.inspect_index(owner, name))

    # Per-file mass from the symbol table.
    sym_count: Counter = Counter()
    for sym in index.symbols:
        f = (sym.get("file", "") or "").replace("\\", "/")
        if not f:
            continue
        sym_count[f] += 1

    # Byte mass merges each file's symbol spans: a class and its methods cover
    # the same source, so summing byte_length counts those bytes twice and the
    # inflation tracks how class-heavy a file is. Files whose spans cannot be
    # trusted are unmeasurable, not zero, and are excluded + disclosed.
    byte_mass, bytes_unmeasurable = file_byte_mass(index.symbols)

    code_files = sorted(sym_count.keys())
    if not code_files:
        return {"error": f"No symbols in {repo!r}. Nothing to measure."}

    # File-level import graph (forward = dependencies, reverse = importers).
    have_imports = bool(getattr(index, "imports", None))
    adj: dict[str, list[str]] = {}
    if have_imports:
        source_files = frozenset(index.source_files)
        adj = _build_adjacency(
            index.imports, source_files,
            getattr(index, "alias_map", None), getattr(index, "psr4_map", None),
        )
    rev: dict[str, list[str]] = {}
    for src, targets in adj.items():
        for tgt in targets:
            rev.setdefault(tgt, []).append(src)

    fan_out = {f: len(adj.get(f, [])) for f in code_files}
    fan_in = {f: len(rev.get(f, [])) for f in code_files}

    # bytes_per_file is measured over a possibly smaller file set than the other
    # three axes; None (never 0.0) when no file has a trustworthy span, because
    # 0.0 reads as "perfectly even" rather than "could not measure".
    byte_files = [f for f in code_files if f in byte_mass]

    concentration = {
        "gini": {
            "symbols_per_file": _gini([sym_count[f] for f in code_files]),
            "bytes_per_file": _gini([byte_mass[f] for f in byte_files]) if byte_files else None,
            "fan_in": _gini([fan_in[f] for f in code_files]),
            "fan_out": _gini([fan_out[f] for f in code_files]),
        },
        "top_concentrators": {
            "symbols_per_file": _top(sym_count, code_files, top_n),
            "bytes_per_file": _top(byte_mass, byte_files, top_n),
            "fan_in": _top(fan_in, code_files, top_n),
            "fan_out": _top(fan_out, code_files, top_n),
        },
        "files_measured": len(code_files),
        "bytes_files_measured": len(byte_files),
        "bytes_unmeasurable_files": len(bytes_unmeasurable),
    }

    # ---- Dependency depth (Lakos) + modularity (DSM insight) ----------------
    # Condense strongly-connected components so a cycle can't inflate depth.
    sccs = _find_cycles(adj)  # components of size > 1
    comp_of: dict[str, int] = {}
    for i, comp in enumerate(sccs):
        for member in comp:
            comp_of[member] = i
    next_id = len(sccs)
    graph_nodes: set[str] = set(adj.keys())
    for tgts in adj.values():
        graph_nodes.update(tgts)
    for f in graph_nodes:
        if f not in comp_of:
            comp_of[f] = next_id
            next_id += 1

    # Condensed DAG: comp -> set(dependency comps); and reverse.
    comp_deps: dict[int, set[int]] = {}
    back_edges = 0
    for u, tgts in adj.items():
        cu = comp_of[u]
        for v in tgts:
            cv = comp_of[v]
            if cu == cv:
                back_edges += 1  # intra-component = cycle-participating (hidden coupling)
            else:
                comp_deps.setdefault(cu, set()).add(cv)
    all_comps = set(comp_of.values())
    comp_rev: dict[int, set[int]] = {}
    for c, deps in comp_deps.items():
        for d in deps:
            comp_rev.setdefault(d, set()).add(c)

    # Longest dependency chain via topological levelization (deps before dependents).
    level: dict[int, int] = {}
    remaining = {c: len(comp_deps.get(c, ())) for c in all_comps}
    q = deque(c for c in all_comps if remaining[c] == 0)
    for c in q:
        level[c] = 0
    while q:
        d = q.popleft()
        for p in comp_rev.get(d, ()):
            remaining[p] -= 1
            if remaining[p] == 0:
                level[p] = 1 + max(level[x] for x in comp_deps[p])
                q.append(p)
    max_depth = max(level.values(), default=0)

    # Reconstruct one longest chain (representative file per component).
    longest_chain: list[str] = []
    if level:
        cur = max(level, key=lambda c: level[c])
        while True:
            members = sorted(f for f, ci in comp_of.items() if ci == cur)
            longest_chain.append(members[0] if members else f"scc{cur}")
            deps = comp_deps.get(cur, set())
            nxt = [d for d in deps if level.get(d, -1) == level[cur] - 1]
            if not nxt:
                break
            cur = sorted(nxt)[0]

    level_hist = Counter(level.values())
    depth = {
        "max_depth": max_depth,
        "longest_chain": longest_chain,
        "level_histogram": {str(k): level_hist[k] for k in sorted(level_hist)},
        "back_edge_count": back_edges,
        "available": have_imports,
    }

    clusters, largest = _weakly_connected(graph_nodes, adj)
    cyclic_files = sum(len(c) for c in sccs)
    modularity = {
        "clusters": clusters,
        "largest_cluster": largest,
        "isolated_files": max(0, len(code_files) - len(graph_nodes)),
        "cyclic_files": cyclic_files,
        "cycle_count": len(sccs),
        "available": have_imports,
    }

    note = (
        "Gini: 0 even, ->1 concentrated (a few files hold the mass). depth: longest "
        "dependency chain over the cycle-condensed graph. back_edges/cyclic_files = "
        "the hidden coupling a DSM highlights; see get_layer_violations for the "
        "specific violations and get_dependency_cycles for the cycles. Read-only estimate."
    )
    if not have_imports:
        note = (
            "No import data (GitHub-indexed or pre-1.3.0 index): concentration covers "
            "symbols/bytes only; fan-in/out, depth, and modularity are unavailable. "
        ) + note

    return {
        "repo": f"{owner}/{name}",
        "concentration": concentration,
        "depth": depth,
        "modularity": modularity,
        "summary": {
            "files": len(code_files),
            "max_depth": max_depth,
            "cycle_count": len(sccs),
            "most_concentrated_metric": max(
                concentration["gini"], key=lambda k: concentration["gini"][k]
            ),
        },
        "_meta": {
            "timing_ms": round((time.perf_counter() - t0) * 1000, 1),
            "top_n": top_n,
            "note": note,
        },
    }
