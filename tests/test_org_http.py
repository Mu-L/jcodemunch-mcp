"""Tests for the org telemetry HTTP transport (POST /org/report)."""

from __future__ import annotations

import pytest
from importlib.util import find_spec

# ⚠⚠ `find_spec`, NOT `pytest.importorskip`. At module scope importorskip
# RAISES during import, so this whole file would collapse to a single
# "1 skipped" line however many tests it holds -- a CI box quietly missing
# starlette would look like a healthy run rather than one 5 tests short.
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

    from jcodemunch_mcp.org.http_routes import make_org_routes  # noqa: E402
    from jcodemunch_mcp.org.store import org_rollup  # noqa: E402
    import jcodemunch_mcp.config as cfg  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CODE_INDEX_PATH", str(tmp_path))
    # Second key of the two-key turn (v1.108.73): an enabled write endpoint with
    # no token fails closed. These tests exercise the happy path, so set it.
    monkeypatch.setenv("JCODEMUNCH_HTTP_TOKEN", "test-token")
    app = Starlette(routes=make_org_routes())
    return TestClient(app)


def _enable(monkeypatch, on=True):
    monkeypatch.setitem(cfg._GLOBAL_CONFIG, "org_ingest_enabled", on)


def test_disabled_by_default_returns_403(client, monkeypatch):
    _enable(monkeypatch, False)
    r = client.post("/org/report", json={"org_id": "acme", "seat_id": "s1", "tokens_saved": 1, "usd": 0.1, "calls": 1})
    assert r.status_code == 403


def test_enabled_records_and_rolls_up(client, tmp_path, monkeypatch):
    _enable(monkeypatch, True)
    r = client.post("/org/report", json={
        "org_id": "acme", "seat_id": "remote-seat", "tokens_saved": 900000, "usd": 13.5, "calls": 300,
    })
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    roll = org_rollup("acme", storage_path=str(tmp_path))
    assert roll["totals"]["seat_count"] == 1
    assert roll["seats"][0]["seat_id"] == "remote-seat"
    assert roll["seats"][0]["tokens_saved"] == 900000


def test_missing_ids_rejected(client, monkeypatch):
    _enable(monkeypatch, True)
    r = client.post("/org/report", json={"org_id": "acme", "tokens_saved": 1})
    assert r.status_code == 400


def test_invalid_json_rejected(client, monkeypatch):
    _enable(monkeypatch, True)
    r = client.post("/org/report", content=b"not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 400


def test_seat_reporter_posts_to_endpoint(monkeypatch):
    """run_org_report with an endpoint POSTs the payload (httpx mocked)."""
    from jcodemunch_mcp.org import report as report_mod

    captured = {}

    class _Resp:
        status_code = 200
        text = "ok"

    def _fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _Resp()

    import httpx
    monkeypatch.setattr(httpx, "post", _fake_post)
    # run_org_report imports these from cli.receipt at call time — patch there.
    import jcodemunch_mcp.cli.receipt as rcpt
    monkeypatch.setattr(rcpt, "iter_calls", lambda root, **k: [])
    monkeypatch.setattr(rcpt, "aggregate", lambda calls: {"totals": {"savings_tokens": 5, "calls": 2}})
    monkeypatch.setattr(rcpt, "dollar_savings", lambda tokens, model: 0.1)

    res = report_mod.run_org_report(org_id="acme", seat_id="s1", endpoint="http://host:9000")
    assert res["reported"] is True
    assert res["transport"] == "http"
    assert captured["url"] == "http://host:9000/org/report"
    assert captured["json"]["seat_id"] == "s1"
    assert captured["json"]["tokens_saved"] == 5
