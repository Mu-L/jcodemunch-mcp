r"""TypeScript type-only imports are indexed like value imports (#560).

⚠ Written as an ANSWER to a question, not a fix for a defect: @lilubot asked
whether `import type` / `import { type X }` specifiers reach the import graph
with the same fidelity as value imports, after a prior audit appeared to show
missed cross-file type references. All four spellings resolve, so nothing was
changed -- and that is exactly why this file exists. **The claim "type-only
imports work" previously rested on nothing**: no test named the syntax, so a
regex change could have removed the `(?:type\s+)?` group or the `^type\s+`
strip in `_clean_names` and every suite would still have been green.

⚠⚠ `Ambient` is the deliberate negative. A global `declare type` in a `.d.ts`
used with NO import statement is correctly invisible to `find_references`,
whose documented scope is import sites -- not every textual usage. Asserting
0 here keeps someone from "fixing" that into a text scan, and it is the most
likely explanation for a real audit seeing a type reference it expected.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jcodemunch_mcp.tools.find_references import find_references
from jcodemunch_mcp.tools.index_folder import index_folder

_PROVIDER = """\
export interface DraftHistoryEntry { id: string }
export type LayoutGestureBinding = { key: string }
export interface CreoJobBuild { n: number }
export function provider() { return 1 }
"""


@pytest.fixture(scope="module")
def repo(tmp_path_factory) -> tuple[str, str]:
    root: Path = tmp_path_factory.mktemp("ts_type_only")
    (root / "src" / "hooks").mkdir(parents=True)
    (root / "src" / "hooks" / "FrameLayoutDraftProvider.tsx").write_text(
        _PROVIDER, encoding="utf-8"
    )
    # 1. `import type { X } from`
    (root / "src" / "hooks" / "useFrameLayoutDraft.ts").write_text(
        "import type { DraftHistoryEntry } from './FrameLayoutDraftProvider';\n"
        "export function useDraft(e: DraftHistoryEntry) { return e.id }\n",
        encoding="utf-8",
    )
    # 2. inline `import { type X, value }` -- mixed clause
    (root / "src" / "inline.ts").write_text(
        "import { type LayoutGestureBinding, provider }"
        " from './hooks/FrameLayoutDraftProvider';\n"
        "export function b(x: LayoutGestureBinding) { return x.key + provider() }\n",
        encoding="utf-8",
    )
    # 3. multi-line `import type {\n X,\n } from`
    (root / "src" / "multiline.ts").write_text(
        "import type {\n  CreoJobBuild,\n}"
        " from './hooks/FrameLayoutDraftProvider';\n"
        "export function c(x: CreoJobBuild) { return x.n }\n",
        encoding="utf-8",
    )
    # 4. barrel: `export type { X } from` re-exported, then type-imported
    (root / "src" / "types").mkdir()
    (root / "src" / "types" / "models.ts").write_text(
        "export interface Order { id: string }\n", encoding="utf-8"
    )
    (root / "src" / "types" / "index.ts").write_text(
        "export type { Order } from './models';\n", encoding="utf-8"
    )
    (root / "src" / "consumer.ts").write_text(
        "import type { Order } from './types';\n"
        "export const f = (o: Order) => o.id;\n",
        encoding="utf-8",
    )
    # Negative: an ambient global type, used with no import at all.
    (root / "src" / "globals.d.ts").write_text(
        "declare type Ambient = { z: number }\n", encoding="utf-8"
    )
    (root / "src" / "amb.ts").write_text(
        "export const g = (a: Ambient) => a.z;\n", encoding="utf-8"
    )

    storage = str(root / ".index")
    result = index_folder(str(root), use_ai_summaries=False, storage_path=storage)
    return result["repo"], storage


@pytest.mark.parametrize(
    "identifier,expected_file",
    [
        ("DraftHistoryEntry", "src/hooks/useFrameLayoutDraft.ts"),
        ("LayoutGestureBinding", "src/inline.ts"),
        ("CreoJobBuild", "src/multiline.ts"),
    ],
    ids=["import-type-braces", "inline-type-specifier", "multiline-import-type"],
)
def test_type_only_import_is_a_reference(repo, identifier, expected_file):
    repo_id, storage = repo
    out = find_references(repo_id, identifier=identifier, storage_path=storage)
    files = [r["file"] for r in out.get("references", [])]
    assert expected_file in files, f"{identifier} not found in {files}"


def test_value_import_in_a_mixed_clause_is_not_lost(repo):
    """`import { type X, value }` must yield BOTH names, not just the type."""
    repo_id, storage = repo
    out = find_references(repo_id, identifier="provider", storage_path=storage)
    assert "src/inline.ts" in [r["file"] for r in out.get("references", [])]


def test_type_only_barrel_reexport_resolves_both_hops(repo):
    repo_id, storage = repo
    out = find_references(repo_id, identifier="Order", storage_path=storage)
    files = [r["file"] for r in out.get("references", [])]
    assert "src/consumer.ts" in files, f"consumer missing from {files}"
    assert "src/types/index.ts" in files, f"barrel missing from {files}"


def test_ambient_type_with_no_import_is_correctly_absent(repo):
    """⚠ The documented scope is import sites, not every textual usage."""
    repo_id, storage = repo
    out = find_references(repo_id, identifier="Ambient", storage_path=storage)
    assert out.get("reference_count") == 0
