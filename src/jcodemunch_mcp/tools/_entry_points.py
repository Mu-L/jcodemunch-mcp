"""Framework-declared entry points, read from the index (#561, #562).

⚠⚠ **The authority already existed and had NO readers.** ``detect_framework``
runs at index time and ``profile_to_meta`` persists the profile's
``entry_point_patterns`` into ``context_metadata`` -- for Next.js that is
exactly ``src/app/**/route.ts``, ``page.tsx``, ``layout.tsx`` and
``middleware.ts``. A tree-wide search found the key written in one place and
read in none. Every consumer that needed to know "is this file a root?"
reproduced its own answer instead, and every one of those answers was Python:
``find_dead_code._ENTRY_POINT_FILENAMES`` is ``main.py`` / ``app.py`` /
``__main__.py`` and eleven siblings, with no JS entry in it at all.

⚠ So this module adds no knowledge. It is the read half of a write that was
already happening, which is the standing lesson in its usual costume: **ask the
authority instead of reproducing its logic.** A framework this does not cover
is fixed in ``framework_profiles.py``, once, and every consumer here inherits
it.

⚠⚠ **``matches()`` returning False is NOT "this is an ordinary module".** No
detected profile means no declaration was available, and a caller that reads
that as a negative finding is asserting something nobody measured. Callers
wanting the difference read ``profile_name`` -- ``None`` there means unknown.
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EntryPointSpec:
    """The entry-point declaration an index carries, if any."""

    profile_name: Optional[str]
    patterns: tuple[str, ...]

    @property
    def declared(self) -> bool:
        """True when a framework profile actually named some roots.

        ⚠ A detected profile with an empty pattern list is still ``False``
        here: it declared nothing, so it can exclude nothing.
        """
        return bool(self.patterns)

    def matches(self, file_path: str) -> bool:
        """True when ``file_path`` is a root the framework declares."""
        if not self.patterns:
            return False
        norm = file_path.replace("\\", "/").lstrip("./")
        base = norm.rsplit("/", 1)[-1]
        for pat in self.patterns:
            if pat.endswith("/"):
                # Directory prefix (`cmd/`, `internal/`). fnmatch never
                # matches these -- `fnmatch("cmd/main.go", "cmd/")` is False --
                # so a prefix test is the only reading under which the Gin
                # profile declares anything at all.
                if norm == pat.rstrip("/") or norm.startswith(pat):
                    return True
                continue
            if fnmatch.fnmatch(norm, pat):
                return True
            if "/" not in pat and norm == base and fnmatch.fnmatch(base, pat):
                # A bare filename declares the ROOT-LEVEL file, not every file
                # of that name anywhere in the tree: `main.py` must not make
                # `src/vendor/main.py` a root. Profiles that mean the nested
                # form spell it out (`src/middleware.ts` sits beside
                # `middleware.ts` in the Next profile for exactly this reason).
                return True
        return False


_EMPTY = EntryPointSpec(profile_name=None, patterns=())

# ⚠⚠ A pattern that matches every source file DECLARES NOTHING, and consuming
# it is far worse than the defect this module fixes. The Flask and FastAPI
# profiles shipped `"*.py"` in their entry-point lists for their whole lives,
# harmless only because nothing read the field (the NestJS profile has a
# comment saying so). Under fnmatch `*` crosses `/`, so a naive reader would
# have declared every Python file in a Flask repo a live root -- turning the
# dead-code tool into one that reports nothing, on a whole ecosystem, silently.
#
# ⚠ The catch-alls are removed at the source too. This guard stays because a
# profile is a list of literals anyone can extend, and the failure is invisible
# from the edit: adding `*.ts` to a profile looks like widening coverage and is
# actually switching a subsystem off.
_CATCH_ALL_PATTERNS = frozenset({"*", "**", "*.*", "**/*"})


def _is_catch_all(pattern: str) -> bool:
    """True for a pattern that cannot distinguish a root from an ordinary file."""
    pat = pattern.strip()
    if pat in _CATCH_ALL_PATTERNS:
        return True
    # `*.py`, `*.ts`, `**/*.tsx`: a bare extension glob over the WHOLE tree.
    # ⚠ Directory scope is what saves a pattern here: `routes/*.php` names one
    # directory and is a perfectly good declaration, while `**/*.php` names
    # every PHP file there is. Only an unscoped (or `**`-scoped) extension
    # glob is a catch-all.
    head, _, stem = pat.rpartition("/")
    if head not in ("", "**"):
        return False
    return stem.startswith("*.") and "*" not in stem[2:] and stem[2:].isalnum()


def entry_point_spec(index) -> EntryPointSpec:
    """Read the framework profile an index was built with.

    Returns ``_EMPTY`` when the index predates profile persistence, was built
    for a framework we do not profile, or carries a malformed block -- all of
    which are "we do not know", never "there are no entry points".
    """
    meta = getattr(index, "context_metadata", None) or {}
    block = meta.get("framework_profile")
    if not isinstance(block, dict):
        return _EMPTY
    raw = block.get("entry_point_patterns")
    if not isinstance(raw, (list, tuple)):
        return _EMPTY
    kept: list[str] = []
    for p in raw:
        if not isinstance(p, str) or not p:
            continue
        if _is_catch_all(p):
            logger.debug(
                "entry_point_spec: ignoring catch-all pattern %r from profile %r",
                p, block.get("name"),
            )
            continue
        kept.append(p)
    patterns = tuple(kept)
    name = block.get("name")
    return EntryPointSpec(
        profile_name=name if isinstance(name, str) and name else None,
        patterns=patterns,
    )
