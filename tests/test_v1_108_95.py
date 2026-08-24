"""v1.108.95 regression tests — externally reported findings (email, verified).

1. assemble_task_context's runtime stage called find_hot_paths with an
   invalid ``name_filter`` kwarg (TypeError, silently swallowed) and then
   read the wrong response key (``hot_paths`` vs the actual ``results``)
   and wrong row field (``hits`` vs ``runtime_count``) — the stage never
   contributed a single entry.
2. runtime/http_routes._read_body fully buffered over-cap bodies before
   rejecting, and gzip.decompress'd the whole payload before the bomb
   check. Now streams with an incremental cap and bounded decompression.
3. Nuxt auto-import edges dropped the matched symbol name (``names`` was
   always empty).
"""

from __future__ import annotations

import gzip
import inspect
import zlib
from pathlib import Path

import pytest
from importlib.util import find_spec

from jcodemunch_mcp.tools.assemble_task_context import assemble_task_context
from jcodemunch_mcp.tools.find_hot_paths import find_hot_paths as real_find_hot_paths
from jcodemunch_mcp.tools.index_folder import index_folder


# ──────────────────────────────────────────────────────────────────────
# 1. assemble_task_context runtime stage
# ──────────────────────────────────────────────────────────────────────


def _make_repo(tmp_path: Path) -> tuple[str, str]:
    (tmp_path / "core.py").write_text(
        "class IndexStore:\n"
        "    def load_index(self, owner, name):\n"
        "        return None\n",
        encoding="utf-8",
    )
    storage = str(tmp_path / ".index")
    result = index_folder(str(tmp_path), use_ai_summaries=False, storage_path=storage)
    return result.get("repo", str(tmp_path)), storage


class TestRuntimeStageCallsFindHotPaths:
    def test_call_site_kwargs_bind_to_real_signature(self):
        """The stage's exact kwargs must bind against find_hot_paths."""
        sig = inspect.signature(real_find_hot_paths)
        # Raises TypeError if the call-site shape ever drifts again.
        sig.bind("local/x", query="IndexStore", top_n=5, storage_path=None)

    def test_stage_consumes_results_key_and_runtime_count(self, tmp_path, monkeypatch):
        repo, storage = _make_repo(tmp_path)
        calls: list[dict] = []

        def fake_find_hot_paths(repo, query=None, top_n=20, *, storage_path=None):
            calls.append({"query": query, "top_n": top_n})
            return {
                "repo": repo,
                "query": query,
                "top_n": top_n,
                "results": [
                    {"symbol_id": "core.py::IndexStore#class", "name": "IndexStore",
                     "kind": "class", "file": "core.py", "line": 1,
                     "runtime_count": 7, "p50_ms": 1, "p95_ms": 3,
                     "sources": ["otel"], "first_seen": "", "last_seen": ""},
                ],
                "_meta": {"timing_ms": 0.1},
            }

        monkeypatch.setattr(
            "jcodemunch_mcp.tools.find_hot_paths.find_hot_paths", fake_find_hot_paths
        )
        result = assemble_task_context(
            repo=repo, task="debug why IndexStore fails",
            intent="debug", include=["anchor", "runtime"],
            token_budget=5000, storage_path=storage,
        )
        assert "error" not in result
        assert calls, "runtime stage never called find_hot_paths"
        assert calls[0]["top_n"] == 5
        runtime_entries = [e for e in result["entries"] if e["stage"] == "runtime"]
        assert runtime_entries, "runtime stage produced no capsule entry"
        hot = runtime_entries[0]["hot_paths"]
        assert hot[0]["hits"] == 7
        assert hot[0]["p95_ms"] == 3


# ──────────────────────────────────────────────────────────────────────
# 2. _read_body streaming cap + bounded gunzip
# ──────────────────────────────────────────────────────────────────────

# ⚠⚠ `find_spec`, NOT `pytest.importorskip`. The importorskip here RAISED
# during import and took the whole file with it -- including two tests above
# this line and the Nuxt block below, neither of which touches starlette.
_HAS_STARLETTE = find_spec("starlette") is not None

if _HAS_STARLETTE:
    from starlette.applications import Starlette  # noqa: E402
    from starlette.testclient import TestClient  # noqa: E402

    from jcodemunch_mcp.runtime.http_routes import (  # noqa: E402
        _bounded_gunzip,
        make_runtime_routes,
    )


@pytest.fixture
def small_cap_app(tmp_path, monkeypatch):
    monkeypatch.setenv("CODE_INDEX_PATH", str(tmp_path))
    monkeypatch.setenv("JCODEMUNCH_RUNTIME_INGEST_ENABLED", "1")
    monkeypatch.setenv("JCODEMUNCH_HTTP_TOKEN", "test-token")
    monkeypatch.setenv("JCODEMUNCH_RUNTIME_INGEST_MAX_BODY_BYTES", "1024")
    from jcodemunch_mcp import config as cfg
    cfg.load_config()
    return Starlette(routes=make_runtime_routes())


@pytest.mark.skipif(
    find_spec("starlette") is None, reason="starlette not installed"
)
class TestBoundedGunzip:
    def test_small_payload_round_trips(self):
        data = b'{"spans": []}'
        assert _bounded_gunzip(gzip.compress(data), 1024) == data

    def test_bomb_rejected_without_full_inflate(self):
        # 4 MB of zeros gzips to ~4 KB; cap of 1 KB must reject it.
        assert _bounded_gunzip(gzip.compress(b"\x00" * 4_194_304), 1024) is None

    def test_multi_member_stream_decodes_fully(self):
        data = gzip.compress(b"hello ") + gzip.compress(b"world")
        assert _bounded_gunzip(data, 1024) == b"hello world"

    def test_truncated_stream_raises(self):
        blob = gzip.compress(b"x" * 10_000)
        with pytest.raises(zlib.error):
            _bounded_gunzip(blob[: len(blob) // 2], 1_000_000)

    def test_exactly_at_cap_allowed(self):
        data = b"a" * 1024
        assert _bounded_gunzip(gzip.compress(data), 1024) == data


@pytest.mark.skipif(
    find_spec("starlette") is None, reason="starlette not installed"
)
class TestReadBodyStreamingCap:
    def test_plain_over_cap_rejected_413(self, small_cap_app):
        client = TestClient(small_cap_app)
        resp = client.post(
            "/runtime/otel",
            content=b"x" * 4096,
            headers={"X-JCM-Repo": "local/phase6"},
        )
        assert resp.status_code == 413
        assert "too large" in resp.json()["error"]

    def test_gzip_bomb_rejected_413(self, small_cap_app):
        client = TestClient(small_cap_app)
        bomb = gzip.compress(b"\x00" * 4_194_304)  # on-wire ~4 KB, inflates to 4 MB
        resp = client.post(
            "/runtime/otel",
            content=bomb,
            headers={"X-JCM-Repo": "local/phase6", "Content-Encoding": "gzip"},
        )
        assert resp.status_code == 413
        assert "too large" in resp.json()["error"]

    def test_gzip_on_wire_over_limit_rejected_413(self, small_cap_app):
        client = TestClient(small_cap_app)
        # Incompressible payload: on-wire size ≈ decompressed size, both
        # far above cap + slack.
        import os as _os
        blob = gzip.compress(_os.urandom(262_144))
        resp = client.post(
            "/runtime/otel",
            content=blob,
            headers={"X-JCM-Repo": "local/phase6", "Content-Encoding": "gzip"},
        )
        assert resp.status_code == 413
        assert "too large" in resp.json()["error"]

    def test_malformed_gzip_rejected_413(self, small_cap_app):
        client = TestClient(small_cap_app)
        resp = client.post(
            "/runtime/otel",
            content=b"not gzip at all",
            headers={"X-JCM-Repo": "local/phase6", "Content-Encoding": "gzip"},
        )
        assert resp.status_code == 413
        assert "gzip decode failed" in resp.json()["error"]


# ──────────────────────────────────────────────────────────────────────
# 3. Nuxt auto-import edges carry symbol names
# ──────────────────────────────────────────────────────────────────────

from jcodemunch_mcp.parser.context.nuxt import NuxtContextProvider  # noqa: E402


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestNuxtAutoImportNames:
    def test_edge_carries_matched_names(self, tmp_path):
        _write(tmp_path / "nuxt.config.ts", "export default defineNuxtConfig({})")
        _write(tmp_path / "package.json", '{"dependencies": {"nuxt": "^3.0.0"}}')
        _write(tmp_path / "composables" / "useAuth.ts",
               "export function useAuth() { return {} }")
        _write(tmp_path / "pages" / "index.vue",
               "<script setup>\nconst { user } = useAuth()\n</script>")

        provider = NuxtContextProvider()
        assert provider.detect(tmp_path)
        provider.load(tmp_path)

        page_imports = provider.get_extra_imports().get("pages/index.vue", [])
        edge = next(i for i in page_imports if i["specifier"] == "composables/useAuth.ts")
        assert edge["names"] == ["useAuth"]
