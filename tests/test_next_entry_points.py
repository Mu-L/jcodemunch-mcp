"""Framework-declared entry points reach the dead-code and coupling tools (#561, #562).

⚠⚠ **The declaration existed and had no reader.** ``detect_framework`` runs at
index time and ``profile_to_meta`` persists ``entry_point_patterns`` into
``context_metadata``; for Next.js that is exactly ``src/app/**/route.ts``,
``page.tsx``, ``layout.tsx`` and ``middleware.ts``. A tree-wide search found the
key written in one place and read in none, so every consumer answered "is this
a root?" from ``find_dead_code._ENTRY_POINT_FILENAMES`` -- which is ``main.py``,
``app.py``, ``__main__.py`` and eleven other Python names, with no JS entry at
all. On @lilubot's Next.js repo that meant zero entry points detected, signal 1
firing on every symbol, and ``get_dead_code_v2`` returning ``dead_symbols: []``
alongside 203 of 366 "unstable" files that were route handlers.

⚠ Every assertion here is written against a **Next.js layout on disk**, not
against the profile constant. Asserting the constant would test the fix instead
of the site -- Practice 9's shape, and two of the tests it names did exactly
that.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jcodemunch_mcp.tools.index_folder import index_folder

# ⚠ The handler IMPORTS: without an edge the import graph is empty, coupling
# refuses outright, and instability is undefined rather than the 1.0 the report
# describes. Ce=1, Ca=0 is exactly the shape #561 measured 126 times.
_HANDLER = (
    "import { query } from '../../../lib/db';" + chr(10) +
    "export async function GET() { return Response.json({ n: query() }) }" + chr(10)
)


@pytest.fixture(scope="module")
def next_repo(tmp_path_factory) -> tuple[str, str, Path]:
    root: Path = tmp_path_factory.mktemp("next_app")
    # Markers detect_framework looks for.
    (root / "package.json").write_text(
        '{"name":"app","dependencies":{"next":"14.2.0","react":"18.3.0"}}\n',
        encoding="utf-8",
    )
    (root / "next.config.js").write_text("module.exports = {}\n", encoding="utf-8")

    # Six route handlers nothing imports -- Ca=0 by construction.
    for name in ("users", "orders", "health", "auth", "billing", "search"):
        d = root / "src" / "app" / "api" / name
        d.mkdir(parents=True)
        (d / "route.ts").write_text(_HANDLER, encoding="utf-8")

    (root / "src" / "app" / "page.tsx").write_text(
        "export default function Page() { return null }\n", encoding="utf-8"
    )
    (root / "src" / "lib").mkdir(parents=True)
    (root / "src" / "lib" / "db.ts").write_text(
        "export function query() { return 1 }\n", encoding="utf-8"
    )

    storage = str(root / ".index")
    result = index_folder(str(root), use_ai_summaries=False, storage_path=storage)
    return result["repo"], storage, root


def test_the_fixture_is_actually_detected_as_next(next_repo):
    """Non-vacuity. Without detection every assertion below passes trivially."""
    repo_id, storage, _ = next_repo
    from jcodemunch_mcp.storage import IndexStore
    from jcodemunch_mcp.tools._utils import resolve_repo

    owner, name = resolve_repo(repo_id, storage)
    index = IndexStore(base_path=storage).load_index(owner, name)
    block = (getattr(index, "context_metadata", None) or {}).get("framework_profile")
    assert block, "no framework profile persisted -- the fixture is not a Next.js repo"
    assert block["name"] == "next"


def test_route_handlers_are_live_roots(next_repo):
    from jcodemunch_mcp.tools.find_dead_code import find_dead_code

    repo_id, storage, _ = next_repo
    out = find_dead_code(repo_id, storage_path=storage)
    assert out.get("framework_profile") == "next"
    assert out["live_root_count"] >= 6, (
        f"route handlers were not treated as roots: {out.get('analysis_notes')}"
    )
    dead_files = [
        d.get("file", "") if isinstance(d, dict) else str(d)
        for d in out.get("dead_files", [])
    ]
    assert not [f for f in dead_files if f.endswith("route.ts")], (
        f"route handlers reported dead: {sorted(dead_files)}"
    )


def test_v2_detects_entry_points_instead_of_degenerating(next_repo):
    from jcodemunch_mcp.tools.get_dead_code_v2 import get_dead_code_v2

    repo_id, storage, _ = next_repo
    out = get_dead_code_v2(repo_id, storage_path=storage)
    diag = out.get("_meta", {}).get("signal_diagnostics", {})
    assert diag.get("entry_points_detected", 0) > 0, (
        "v2 found no entry point on a Next.js repo, so signal 1 fires on "
        f"everything: {out.get('framework_warning')}"
    )
    assert not out.get("framework_warning"), out.get("framework_warning")


def test_route_handlers_leave_both_sides_of_the_coupling_ratio(next_repo):
    """⚠ BOTH sides. Numerator-only would be a silent, flattering adjustment."""
    from jcodemunch_mcp.storage import IndexStore
    from jcodemunch_mcp.tools._utils import resolve_repo
    from jcodemunch_mcp.tools.get_repo_health import _count_unstable_modules

    repo_id, storage, _ = next_repo
    owner, name = resolve_repo(repo_id, storage)
    index = IndexStore(base_path=storage).load_index(owner, name)

    unstable, total, excluded, profile = _count_unstable_modules(index)
    assert profile == "next"
    assert excluded >= 6, f"expected the route handlers excluded, got {excluded}"
    production = [f for f in index.source_files if f.endswith("db.ts")]
    assert production, "fixture lost its ordinary production file"
    assert total < len(index.source_files), (
        "denominator did not shrink -- entry points were dropped from the "
        "numerator only, which raises the score without measuring anything"
    )


def test_single_module_verdict_says_entry_point_not_unstable(next_repo):
    from jcodemunch_mcp.tools.get_coupling_metrics import get_coupling_metrics

    repo_id, storage, _ = next_repo
    out = get_coupling_metrics(repo_id, "src/app/api/users/route.ts",
                               storage_path=storage)
    assert out.get("is_framework_entry_point") is True
    assert out.get("assessment") != "unstable", (
        "a route handler with Ca=0 by construction was graded as a coupling "
        "problem"
    )


def test_an_ordinary_module_is_untouched(next_repo):
    """The exemption must not leak onto normal files."""
    from jcodemunch_mcp.tools.get_coupling_metrics import get_coupling_metrics

    repo_id, storage, _ = next_repo
    out = get_coupling_metrics(repo_id, "src/lib/db.ts", storage_path=storage)
    assert out.get("is_framework_entry_point") is False


# ---------------------------------------------------------------------------
# The catch-all guard — the part that keeps this fix from being worse than
# the defect it repairs.
# ---------------------------------------------------------------------------

class TestNoProfileDeclaresTheWholeTree:
    """⚠⚠ A pattern matching every source file DECLARES NOTHING.

    The Flask and FastAPI profiles shipped ``"*.py"`` in their entry-point
    lists for their whole lives. That was harmless only while the field had no
    reader -- the NestJS profile carries a comment saying so. Under ``fnmatch``
    a ``*`` crosses ``/``, so the first reader to consume the field naively
    would have declared **every Python file in a Flask repo a live root**,
    switching dead-code detection off across a whole ecosystem, silently, and
    raising every such repo's coupling score by emptying its denominator.

    ⚠ The catch-alls are removed at the source AND refused by the reader. Both,
    because a profile is a list of literals anyone can extend and the failure
    is invisible from the edit: adding ``"*.ts"`` looks like widening coverage
    and is actually turning a subsystem off.
    """

    @staticmethod
    def _all_profiles():
        from jcodemunch_mcp.parser.context import framework_profiles as fp
        return [
            v for k, v in vars(fp).items()
            if isinstance(v, fp.FrameworkProfile)
        ]

    def test_the_sweep_actually_finds_profiles(self):
        assert len(self._all_profiles()) >= 8

    def test_no_shipped_profile_carries_a_catch_all(self):
        from jcodemunch_mcp.tools._entry_points import _is_catch_all

        offenders = [
            (p.name, pat)
            for p in self._all_profiles()
            for pat in p.entry_point_patterns
            if _is_catch_all(pat)
        ]
        assert not offenders, (
            f"entry-point patterns that match every file: {offenders}. "
            f"A declaration that cannot exclude anything declares nothing."
        )

    def test_the_reader_refuses_one_anyway(self):
        """Defence in depth: the guard must hold for a profile added later."""
        from types import SimpleNamespace
        from jcodemunch_mcp.tools._entry_points import entry_point_spec

        index = SimpleNamespace(context_metadata={
            "framework_profile": {
                "name": "hypothetical",
                "entry_point_patterns": ["src/app/**/route.ts", "*.ts"],
            }
        })
        spec = entry_point_spec(index)
        assert spec.matches("src/app/api/x/route.ts")
        assert not spec.matches("src/lib/db.ts"), (
            "the catch-all survived and now declares every .ts file a root"
        )

    def test_an_unprofiled_index_knows_it_does_not_know(self):
        """⚠ False from `matches` is not a finding. `profile_name` is the tell."""
        from types import SimpleNamespace
        from jcodemunch_mcp.tools._entry_points import entry_point_spec

        spec = entry_point_spec(SimpleNamespace(context_metadata={}))
        assert spec.profile_name is None
        assert spec.declared is False
        assert spec.matches("anything.ts") is False

    def test_a_bare_filename_does_not_claim_nested_namesakes(self):
        from types import SimpleNamespace
        from jcodemunch_mcp.tools._entry_points import entry_point_spec

        index = SimpleNamespace(context_metadata={
            "framework_profile": {
                "name": "flask", "entry_point_patterns": ["main.py"],
            }
        })
        spec = entry_point_spec(index)
        assert spec.matches("main.py")
        assert not spec.matches("src/vendor/main.py")

    def test_a_directory_prefix_is_honoured(self):
        """⚠ `fnmatch("cmd/main.go", "cmd/")` is False -- the Gin profile
        declares directories, and under fnmatch alone it declared nothing."""
        from types import SimpleNamespace
        from jcodemunch_mcp.tools._entry_points import entry_point_spec

        index = SimpleNamespace(context_metadata={
            "framework_profile": {
                "name": "gin", "entry_point_patterns": ["cmd/", "main.go"],
            }
        })
        spec = entry_point_spec(index)
        assert spec.matches("cmd/server/main.go")
        assert not spec.matches("internal/db/conn.go")


# ---------------------------------------------------------------------------
# #562 — a manifest cannot be dead, and a refusal is not a zero
# ---------------------------------------------------------------------------

class TestToolchainManifestsAreNotDeadCode:
    """⚠⚠ Nothing imports a lockfile BY DESIGN, so `zero_importers` is a
    tautology there rather than a finding. JSON/YAML/TOML are indexed as real
    languages here, so ``find_dead_code`` reported ``pnpm-lock.yaml``,
    ``tsconfig.json`` and -- sharpest of all -- ``package.json`` as dead, in
    the same run that READ ``package.json`` to discover the repo's entry
    points (#562, @lilubot).

    ⚠ Names, never an extension rule. An orphaned ``data/fixtures.json`` is a
    real finding and ``test_a_genuinely_orphaned_data_file_is_still_reported``
    is what stops the fix from swallowing it -- without that assertion this
    could be "passed" by excluding every data file.
    """

    @pytest.fixture(scope="class")
    def repo(self, tmp_path_factory):
        root: Path = tmp_path_factory.mktemp("manifests")
        (root / "src").mkdir()
        (root / "data").mkdir()
        (root / "src" / "a.ts").write_text(
            "export function orphan(){ return 1 }\n", encoding="utf-8"
        )
        (root / "package.json").write_text(
            '{"name":"x","main":"src/a.ts"}\n', encoding="utf-8"
        )
        (root / "pnpm-lock.yaml").write_text(
            "lockfileVersion: '9.0'\nimporters:\n  .:\n    dependencies:\n"
            "      next:\n        specifier: ^14\n        version: 14.2.0\n",
            encoding="utf-8",
        )
        (root / "tsconfig.json").write_text(
            '{"compilerOptions":{"strict":true}}\n', encoding="utf-8"
        )
        (root / "data" / "fixtures.json").write_text(
            '{"rows":[1,2,3]}\n', encoding="utf-8"
        )
        storage = str(root / ".index")
        out = index_folder(str(root), use_ai_summaries=False, storage_path=storage)
        return out["repo"], storage

    @staticmethod
    def _dead_files(repo_id, storage):
        from jcodemunch_mcp.tools.find_dead_code import find_dead_code
        out = find_dead_code(repo_id, granularity="file", min_confidence=0.8,
                             storage_path=storage)
        return {
            d.get("file", "") if isinstance(d, dict) else str(d)
            for d in out.get("dead_files", [])
        }

    @pytest.mark.parametrize(
        "manifest", ["package.json", "pnpm-lock.yaml", "tsconfig.json"]
    )
    def test_manifest_is_not_reported_dead(self, repo, manifest):
        repo_id, storage = repo
        assert manifest not in self._dead_files(repo_id, storage)

    def test_a_genuinely_orphaned_data_file_is_still_reported(self, repo):
        """⚠ The signal this fix must NOT swallow."""
        repo_id, storage = repo
        assert "data/fixtures.json" in self._dead_files(repo_id, storage)


class TestARefusalIsNotAZero:
    """⚠⚠ ``get_dead_code_v2`` returns ``dead_symbols: []`` **with a
    `signal_warning`** when too few signals discriminate -- an honest refusal.
    Reading only the list turned that into ``dead_code_pct: 0.0`` and a
    dead_code axis of 100: the strongest possible claim, built from an explicit
    admission that nothing was established (#562).

    ⚠ Same shape as v1.108.305's `churn_surface` on a shallow clone, and it
    reuses that release's mechanism rather than adding a second one.
    """

    @pytest.fixture(scope="class")
    def degenerate_repo(self, tmp_path_factory):
        """No entry point at all, so every signal fires on every symbol."""
        root: Path = tmp_path_factory.mktemp("degenerate")
        (root / "src").mkdir()
        (root / "src" / "hub.py").write_text(
            "def hub():\n    return 1\n", encoding="utf-8"
        )
        for i in range(6):
            (root / "src" / f"m{i}.py").write_text(
                f"from src.hub import hub\n\n\ndef f{i}():\n    return hub()\n",
                encoding="utf-8",
            )
        storage = str(root / ".index")
        out = index_folder(str(root), use_ai_summaries=False, storage_path=storage)
        return out["repo"], storage

    def test_the_fixture_actually_degenerates(self, degenerate_repo):
        """Non-vacuity: without a refusal there is nothing to withhold."""
        from jcodemunch_mcp.tools.get_dead_code_v2 import get_dead_code_v2

        repo_id, storage = degenerate_repo
        out = get_dead_code_v2(repo_id, min_confidence=0.67, storage_path=storage)
        assert out.get("signal_warning"), "fixture did not trigger the refusal"
        assert out.get("dead_symbols") == []

    def test_health_withholds_the_grade_instead_of_publishing_zero(
        self, degenerate_repo
    ):
        from jcodemunch_mcp.tools.get_repo_health import get_repo_health

        repo_id, storage = degenerate_repo
        health = get_repo_health(repo_id, storage_path=storage)

        assert health["dead_code_measurable"] is False
        assert health["dead_code_signal_warning"]
        radar = health["radar"]
        assert "dead_code" in radar.get("unmeasurable_axes", [])
        assert radar["composite"] is None, (
            "a composite was published over an axis that refused to measure"
        )
        assert radar["grade"] is None

    def test_the_axes_that_WERE_measured_still_stand(self, degenerate_repo):
        """⚠ Withholding the grade must not blank the real measurements."""
        from jcodemunch_mcp.tools.get_repo_health import get_repo_health

        repo_id, storage = degenerate_repo
        axes = get_repo_health(repo_id, storage_path=storage)["radar"]["axes"]
        assert axes["complexity"]["score"] is not None
        assert axes["cycles"]["score"] is not None
