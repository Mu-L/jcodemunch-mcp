"""Packages that enumerate their own modules at import time (#569).

``pkgutil.iter_modules(__path__)`` + ``importlib.import_module(...)`` is the
standard Python plugin shape, and **no static import graph can see the edge it
builds**. A dead-code tool reading only the graph is therefore correct about the
graph and wrong about the program.

⚠⚠ **The tell that this is a false positive and not a finding: which modules of
such a package get reported depends on TEST-AUTHORING HABIT.** All fifteen
encoders under ``encoding/schemas/`` are loaded identically by ``registry.py``.
Three had a test that imports them by name, so they had an importer; the other
twelve were published as ``zero_importers`` at **confidence 1.0**, the value
this project documents as *provably unreachable*. ``search_symbols.py`` and
``search_text.py`` have the same role, the same shape and the same load path,
and one was called dead. Nothing about reachability separates them.

⚠ **Both halves of #569 are implemented and they are not alternatives.**
``roots`` removes the false positives where the enumerated directory RESOLVES.
``unresolved`` is the honest floor for the sites where it does not: a package is
walked by something and we could not say which, so an absence claim over that
corpus cannot be published at 1.0. A detector that only had the first half would
be silent in exactly the cases it could not handle.

⚠ Deliberately NOT an extension or directory-name exemption. A module in a
package nothing walks IS dead and must still be reported; being enumerated is
the property, ``encoding/schemas/`` is one instance of it.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

#: Import specifiers whose presence makes a file worth reading. The scan is
#: content-based and content reads are the expensive part, so the import graph
#: does the filtering first — on this repo that is 8 files of 833.
_DISCOVERY_MODULES = frozenset({"pkgutil", "importlib", "importlib.util"})

#: The enumerators. ``walk_packages`` RECURSES into subpackages and
#: ``iter_modules`` does not, and the difference decides how far the live root
#: extends — a recursive walker that only revived its top directory would leave
#: the nested modules reported dead for the same wrong reason.
_ENUMERATE_RE = re.compile(
    r"\b(?:pkgutil\.)?(?P<fn>iter_modules|walk_packages)\s*\((?P<arg>[^;\n]*)"
)

#: Enumeration alone is a directory LISTING. The package is only made reachable
#: when something in the same file also imports what it listed.
_DYNAMIC_IMPORT_RE = re.compile(
    r"\b(?:importlib\.)?import_module\s*\(|\b__import__\s*\(|\bload_module\s*\("
)

#: ``__path__`` (the package's own search path) and ``__file__`` (its own
#: location) are the two ways a loader names the directory it lives in. Anything
#: else — a config value, a caller-supplied path, another package's search path
#: — is a target we cannot resolve from text, and is reported as unresolved
#: rather than guessed at.
#:
#: ⚠⚠ **The motivating case does not name ``__path__`` at the call.**
#: ``registry.py`` writes ``from . import __path__ as pkg_path`` on one line and
#: ``pkgutil.iter_modules(pkg_path)`` on the next, so a check that reads only
#: the call argument resolves NOTHING and every module stays reported dead —
#: the first draft of this scanner did exactly that. Bind the aliases first.
#: ⚠⚠ **BARE, never qualified, and the difference was a 502-file overreach.**
#: `tests/test_v1_108_169.py` writes `pkgutil.iter_modules(schemas_pkg.__path__)`
#: — ANOTHER package's search path, reached through a local variable. A scanner
#: that only asks "does `__path__` appear here?" reads that as the test
#: directory enumerating itself and revives every file under `tests/`: a
#: false-negative machine wearing a bug fix's clothes. The first draft did
#: exactly that, and running it is what showed it. Only an UNQUALIFIED
#: `__path__` / `__file__` names this file's own package.
_BARE_OWN = r"(?<![.\w])(?:__path__|__file__)\b"

_ALIAS_RES = (
    re.compile(_BARE_OWN + r"\s+as\s+(?P<n>\w+)"),
    re.compile(r"^\s*(?P<n>\w+)\s*=(?!=)[^=\n]*" + _BARE_OWN, re.M),
)
_BARE_OWN_RE = re.compile(_BARE_OWN)


def _own_package_names(content: str) -> set[str]:
    """Names in this file that stand for the package's own location."""
    names: set[str] = set()
    for rx in _ALIAS_RES:
        for m in rx.finditer(content):
            names.add(m.group("n"))
    return names


def _names_own_package(arg: str, own_names: set[str]) -> bool:
    """Does this call argument name the loader's OWN package directory?

    Two ways in, and both obey the qualification rule above: the argument
    mentions a bare ``__path__``/``__file__``, or it mentions a local name bound
    to one. ``schemas_pkg.__path__`` satisfies neither — attribute access is
    stripped before the alias comparison so a matching attribute NAME cannot
    stand in for the alias.
    """
    if _BARE_OWN_RE.search(arg):
        return True
    if not own_names:
        return False
    unqualified = re.sub(r"\w+\s*\.\s*", "", arg)
    return any(tok in own_names for tok in re.findall(r"\w+", unqualified))


class DynamicDiscovery:
    """What a runtime-discovery scan established, in three parts.

    ``roots``       files made reachable by a resolved enumeration.
    ``packages``    {directory: [loader files]} — the disclosure behind ``roots``.
    ``unresolved``  loader files whose enumerated directory could not be named.

    ⚠ ``unresolved`` being non-empty is not a failure of the scan; it is the
    scan's answer, and the only one that can honestly cap a confidence.
    """

    __slots__ = ("roots", "packages", "unresolved")

    def __init__(
        self,
        roots: frozenset[str],
        packages: dict[str, list[str]],
        unresolved: list[str],
    ):
        self.roots = roots
        self.packages = packages
        self.unresolved = unresolved

    def __bool__(self) -> bool:
        return bool(self.roots or self.unresolved)


_EMPTY = DynamicDiscovery(frozenset(), {}, [])


def _dirname(path: str) -> str:
    fp = path.replace("\\", "/")
    return fp.rsplit("/", 1)[0] if "/" in fp else ""


def _candidate_files(index) -> list[str]:
    """Python files that import a module capable of dynamic loading."""
    imports = getattr(index, "imports", None) or {}
    out: list[str] = []
    for src_file, file_imports in imports.items():
        if not (src_file.endswith(".py") or src_file.endswith(".pyw")):
            continue
        for imp in file_imports or ():
            spec = str(imp.get("specifier") or "")
            head = spec.split(".", 1)[0]
            if spec in _DISCOVERY_MODULES or head in _DISCOVERY_MODULES:
                out.append(src_file)
                break
    return sorted(out)


def discover_dynamic_packages(
    index, store, owner: str, name: str
) -> DynamicDiscovery:
    """Find packages loaded by enumeration, and the modules they revive.

    Never raises: a scan that cannot run returns the empty result, which leaves
    every caller exactly where it was before this existed.
    """
    try:
        candidates = _candidate_files(index)
    except Exception:  # pragma: no cover - defensive
        logger.debug("runtime-discovery prefilter failed", exc_info=True)
        return _EMPTY
    if not candidates:
        return _EMPTY

    source_files = frozenset(getattr(index, "source_files", ()) or ())
    by_dir: dict[str, list[str]] = {}
    for f in source_files:
        if f.endswith(".py") or f.endswith(".pyw"):
            by_dir.setdefault(_dirname(f), []).append(f)

    roots: set[str] = set()
    packages: dict[str, list[str]] = {}
    unresolved: list[str] = []

    for loader in candidates:
        try:
            content = store.get_file_content(owner, name, loader)
        except Exception:  # pragma: no cover - defensive
            logger.debug("could not read %s for discovery scan", loader, exc_info=True)
            continue
        if not content:
            continue
        matches = list(_ENUMERATE_RE.finditer(content))
        if not matches:
            continue
        if not _DYNAMIC_IMPORT_RE.search(content):
            # Listed but never imported: a directory scan, not a load path.
            continue

        loader_dir = _dirname(loader)
        own_names = _own_package_names(content)
        resolved_here = False
        for m in matches:
            if not _names_own_package(m.group("arg"), own_names):
                continue
            recursive = m.group("fn") == "walk_packages"
            targets = [loader_dir] if not recursive else [
                d for d in by_dir
                if d == loader_dir or d.startswith(loader_dir + "/")
            ]
            for d in targets:
                for f in by_dir.get(d, ()):
                    if f != loader:
                        roots.add(f)
                packages.setdefault(d, [])
                if loader not in packages[d]:
                    packages[d].append(loader)
            resolved_here = True
        if not resolved_here:
            unresolved.append(loader)

    return DynamicDiscovery(frozenset(roots), packages, sorted(unresolved))
