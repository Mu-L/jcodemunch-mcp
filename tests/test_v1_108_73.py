"""v1.108.73 — Phase 2 hardening (PRD WI-2.1 + WI-2.3).

WI-2.1 (F-S01): the HTTP ingest write endpoints (runtime + org) now FAIL CLOSED
when enabled without JCODEMUNCH_HTTP_TOKEN. The BearerAuthMiddleware only checks
the token "if set", so an enabled endpoint with no token was an unauthenticated
write surface guarded only by a startup warning. The handlers now refuse (503)
when enabled-but-no-token, making the documented two-key turn real.

WI-2.3 (F-S03): redaction now covers current token formats that the existing
structural patterns missed — GitHub fine-grained PATs (github_pat_), OpenAI
project/legacy keys (sk-proj-/sk-), and Anthropic keys (sk-ant-).
"""

from __future__ import annotations

import pytest
from importlib.util import find_spec

import jcodemunch_mcp.config as cfg
from jcodemunch_mcp.redact import _redact_string

# ⚠⚠ `find_spec`, NOT `pytest.importorskip`. At module scope importorskip
# RAISES during import, so this whole file would collapse to a single
# "1 skipped" line however many tests it holds -- a CI box quietly missing
# starlette would look like a healthy run rather than one 10 tests short.
# find_spec asks the same question without raising: every test is collected
# and skipped individually. The imports below need the package present, so
# they move under the flag.
_HAS_STARLETTE = find_spec("starlette") is not None
pytestmark = pytest.mark.skipif(
    not _HAS_STARLETTE, reason="starlette not installed"
)
if _HAS_STARLETTE:
    from starlette.applications import Starlette  # noqa: E402
    from starlette.testclient import TestClient  # noqa: E402

    from jcodemunch_mcp.runtime.http_routes import make_runtime_routes  # noqa: E402
    from jcodemunch_mcp.org.http_routes import make_org_routes  # noqa: E402


# ── WI-2.1: fail closed when enabled without a token ──────────────────────


class TestIngestFailsClosedWithoutToken:
    def test_runtime_enabled_no_token_returns_503(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CODE_INDEX_PATH", str(tmp_path))
        monkeypatch.setitem(cfg._GLOBAL_CONFIG, "runtime_ingest_enabled", True)
        monkeypatch.delenv("JCODEMUNCH_HTTP_TOKEN", raising=False)
        client = TestClient(Starlette(routes=make_runtime_routes()))

        r = client.post(
            "/runtime/otel", content=b"{}",
            headers={"X-JCM-Repo": "local/whatever"},
        )
        assert r.status_code == 503, r.text
        assert "JCODEMUNCH_HTTP_TOKEN" in r.json()["error"]

    def test_org_enabled_no_token_returns_503(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CODE_INDEX_PATH", str(tmp_path))
        monkeypatch.setitem(cfg._GLOBAL_CONFIG, "org_ingest_enabled", True)
        monkeypatch.delenv("JCODEMUNCH_HTTP_TOKEN", raising=False)
        client = TestClient(Starlette(routes=make_org_routes()))

        r = client.post(
            "/org/report",
            json={"org_id": "acme", "seat_id": "s1", "tokens_saved": 1},
        )
        assert r.status_code == 503, r.text
        assert "JCODEMUNCH_HTTP_TOKEN" in r.json()["error"]

    def test_token_present_passes_the_auth_gate(self, tmp_path, monkeypatch):
        """With a token set, the auth gate is satisfied; the request proceeds
        past it (here to a 404 repo-not-found), proving the 503 is token-only."""
        monkeypatch.setenv("CODE_INDEX_PATH", str(tmp_path))
        monkeypatch.setitem(cfg._GLOBAL_CONFIG, "runtime_ingest_enabled", True)
        monkeypatch.setenv("JCODEMUNCH_HTTP_TOKEN", "test-token")
        client = TestClient(Starlette(routes=make_runtime_routes()))

        r = client.post(
            "/runtime/otel", content=b"{}",
            headers={"X-JCM-Repo": "local/not-indexed"},
        )
        assert r.status_code != 503
        # Not the token error, regardless of the exact downstream status.
        assert "JCODEMUNCH_HTTP_TOKEN" not in r.text

    def test_disabled_still_403_or_503_before_auth(self, tmp_path, monkeypatch):
        """Disabled endpoints reject on the enable check, before the auth check,
        so the disabled path is unchanged by this release."""
        monkeypatch.setenv("CODE_INDEX_PATH", str(tmp_path))
        monkeypatch.setitem(cfg._GLOBAL_CONFIG, "org_ingest_enabled", False)
        monkeypatch.delenv("JCODEMUNCH_HTTP_TOKEN", raising=False)
        client = TestClient(Starlette(routes=make_org_routes()))

        r = client.post("/org/report", json={"org_id": "acme", "seat_id": "s1"})
        assert r.status_code == 403
        assert "disabled" in r.json()["error"]


# ── WI-2.3: redaction covers current token formats ────────────────────────


class TestRedactionCoversCurrentTokenFormats:
    def test_anthropic_key_redacted(self):
        secret = "sk-ant-api03-A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0"
        out, n = _redact_string(f"export ANTHROPIC_API_KEY={secret}")
        assert secret not in out
        assert "[REDACTED:anthropic_api_key]" in out
        assert n >= 1

    def test_openai_project_key_redacted(self):
        secret = "sk-proj-A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6T7u8"
        out, _ = _redact_string(f"OPENAI_API_KEY={secret}")
        assert secret not in out
        assert "[REDACTED:openai_api_key]" in out

    def test_openai_legacy_key_redacted(self):
        secret = "sk-" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0U1v2W3x4"
        out, _ = _redact_string(f"key {secret} here")
        assert secret not in out
        assert "[REDACTED:openai_api_key]" in out

    def test_github_fine_grained_pat_redacted(self):
        secret = "github_pat_11ABCDEFG0aBcDeFgHiJ_kLmNoPqRsTuVwXyZ0123456789AbCdEf"
        out, _ = _redact_string(f"token: {secret}")
        assert secret not in out
        assert "[REDACTED:github_fine_grained_pat]" in out

    def test_classic_github_token_still_redacted(self):
        secret = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
        out, _ = _redact_string(secret)
        assert secret not in out
        assert "[REDACTED:github_token]" in out

    def test_benign_short_sk_string_not_redacted(self):
        """A short sk- fragment is not a key and must pass through untouched."""
        text = "use the sk-cli tool and sk-ant for short"
        out, n = _redact_string(text)
        assert out == text
        assert n == 0
