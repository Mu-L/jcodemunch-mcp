"""Tests for watch-all: registry discovery + service installer path generation."""
from __future__ import annotations

import os
import platform
from pathlib import Path
from unittest.mock import patch

import pytest

from jcodemunch_mcp import service_installer, watch_all


# ── discover_local_repos ────────────────────────────────────────────────────


def _mk_entry(source_root: str) -> dict:
    return {"repo": f"repo-{hash(source_root) & 0xffff}", "source_root": source_root}


def test_discover_filters_remote_and_missing(tmp_path, monkeypatch):
    real = tmp_path / "live_repo"
    real.mkdir()
    ghost = tmp_path / "vanished"

    class FakeStore:
        def __init__(self, *_a, **_kw): pass
        def list_repos(self):
            return [
                _mk_entry(str(real)),
                _mk_entry(str(ghost)),   # missing — filtered
                _mk_entry(""),            # GitHub repo (no source_root) — filtered
            ]

    monkeypatch.setattr(watch_all, "IndexStore", FakeStore)
    out = watch_all.discover_local_repos(storage_path=str(tmp_path))
    assert out == [str(real.resolve())]


def test_discover_deduplicates(tmp_path, monkeypatch):
    real = tmp_path / "r"
    real.mkdir()

    class FakeStore:
        def __init__(self, *_a, **_kw): pass
        def list_repos(self):
            return [_mk_entry(str(real)), _mk_entry(str(real))]

    monkeypatch.setattr(watch_all, "IndexStore", FakeStore)
    out = watch_all.discover_local_repos(storage_path=str(tmp_path))
    assert len(out) == 1


# ── service_installer path generation ───────────────────────────────────────


def test_exec_cmd_uses_current_interpreter():
    cmd = service_installer._exec_cmd()
    assert cmd[0].endswith("python") or cmd[0].endswith("python.exe") or "python" in cmd[0].lower()
    assert cmd[1:] == ["-m", "jcodemunch_mcp", "watch-all"]


def test_systemd_unit_path_under_home():
    p = service_installer._systemd_unit_path()
    assert ".config/systemd/user" in str(p).replace("\\", "/")
    assert p.name == "jcodemunch-watch.service"


def test_launchd_plist_path_under_home():
    p = service_installer._launchd_plist_path()
    assert "LaunchAgents" in str(p)
    assert p.name.endswith(".plist")


def test_install_service_unsupported_platform(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Plan9")
    with pytest.raises(service_installer.InstallerError):
        service_installer.install_service()


def test_xml_escape_covers_specials():
    assert service_installer._xml_escape('a&b<c>"d"') == "a&amp;b&lt;c&gt;&quot;d&quot;"


def test_shell_quote_roundtrip():
    assert service_installer._shell_quote("simple") == "simple"
    assert service_installer._shell_quote("has space") == "'has space'"
    assert "'\\''" in service_installer._shell_quote("it's")


# ── get_watch_status ────────────────────────────────────────────────────────


def test_get_watch_status_shape(tmp_path, monkeypatch):
    from jcodemunch_mcp.tools import get_watch_status as mod

    real = tmp_path / "r"
    real.mkdir()

    monkeypatch.setattr(mod, "discover_local_repo_entries",
                        lambda storage_path=None: {str(real): {}})
    monkeypatch.setattr(mod, "service_status", lambda: {"active": False, "platform": "test"})
    monkeypatch.setattr(mod, "get_reindex_status", lambda repo: {
        "index_stale": False, "reindex_in_progress": False, "stale_since_ms": None,
    })

    out = mod.get_watch_status()
    assert out["repo_count"] == 1
    assert out["any_stale"] is False
    assert out["repos"][0]["source_root"] == str(real)
    assert out["service"]["active"] is False
