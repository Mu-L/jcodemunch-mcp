"""The integrity check must not enumerate every distribution to clear itself.

``importlib.metadata.packages_distributions()`` builds a top-level-name ->
distribution map for EVERY distribution on ``sys.path``. Measured on a Windows
dev box carrying 894 top-level names it costs **3.35 s, uncached, on every CLI
invocation** — and on that box it then returned nothing, because the code was
running from source and no distribution described it.

⚠ That was invisible for as long as the CLI was something a human typed. It
stops being invisible when hooks spawn it per tool call: end-to-end, one
``hook-pretooluse`` spawn went 4.0 s -> 0.94 s on the same box from this change
alone, and the rest of what remains is the server import.

⚠⚠ **These tests assert the COST, not the implementation.** The property is
"the common paths settle without the full map", so any rewrite that reaches the
same verdict some other cheap way passes, and any rewrite that quietly goes
back to enumerating fails. Asserting the call order or the helper names instead
would pin the current shape and check nothing anyone cares about.

⚠ The expensive map must stay REACHABLE — it is the only thing that can name
the offending distribution, which is the whole content of the warning. A test
that simply banned the call would be satisfied by deleting the security check.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from jcodemunch_mcp import security


class _Dist:
    """Minimal importlib.metadata.Distribution stand-in."""

    def __init__(self, owned_dir: Path):
        self._owned = owned_dir

    def locate_file(self, name):
        return self._owned


@pytest.fixture
def spy(monkeypatch):
    """Count packages_distributions() calls without changing what it returns."""
    calls = {"n": 0, "returns": {}}

    def fake_packages_distributions():
        calls["n"] += 1
        return calls["returns"]

    fake_meta = types.ModuleType("importlib.metadata")
    fake_meta.packages_distributions = fake_packages_distributions
    fake_meta.PackageNotFoundError = LookupError

    def set_official(dist_or_exc):
        def distribution(name):
            if isinstance(dist_or_exc, Exception):
                raise dist_or_exc
            return dist_or_exc
        fake_meta.distribution = distribution

    set_official(LookupError("not installed"))
    calls["set_official"] = set_official
    monkeypatch.setitem(sys.modules, "importlib.metadata", fake_meta)
    return calls


def _pretend_installed(monkeypatch, tmp_path: Path) -> Path:
    """Make security.__file__ look like it lives in a real site-packages."""
    pkg = tmp_path / "site-packages" / "jcodemunch_mcp"
    pkg.mkdir(parents=True)
    target = pkg / "security.py"
    target.write_text("", encoding="utf-8")
    monkeypatch.setattr(security, "__file__", str(target))
    return pkg


def test_source_checkout_does_not_enumerate_distributions(spy, monkeypatch, tmp_path):
    """A source tree has no distribution describing it — and cannot pay 3 s to
    be told so."""
    pkg = tmp_path / "src" / "jcodemunch_mcp"
    pkg.mkdir(parents=True)
    target = pkg / "security.py"
    target.write_text("", encoding="utf-8")
    monkeypatch.setattr(security, "__file__", str(target))

    security.verify_package_integrity()

    assert spy["n"] == 0, (
        "running from a source checkout enumerated every distribution on the "
        "box to reach a verdict that needed none"
    )


def test_official_install_does_not_enumerate_distributions(spy, monkeypatch, tmp_path):
    """The overwhelmingly common case: installed from PyPI, nothing wrong."""
    pkg = _pretend_installed(monkeypatch, tmp_path)
    spy["set_official"](_Dist(pkg))

    security.verify_package_integrity()

    assert spy["n"] == 0, (
        "a clean official install still paid for the full distribution map"
    )


def test_renamed_fork_is_still_named(spy, monkeypatch, tmp_path, capsys):
    """The map is reached when it is the only thing that can answer.

    ⚠ This is the test that stops the cheap paths from being 'optimised' into
    a check that never warns about anything.
    """
    _pretend_installed(monkeypatch, tmp_path)
    spy["set_official"](LookupError("official dist absent"))
    spy["returns"] = {"jcodemunch_mcp": ["jcodemunch-mcp-fork"]}

    security.verify_package_integrity()

    assert spy["n"] == 1, "the fork case must still consult the full map"
    err = capsys.readouterr().err
    assert "SECURITY WARNING" in err
    assert "jcodemunch-mcp-fork" in err


def test_official_present_but_not_the_running_code_is_named(
    spy, monkeypatch, tmp_path, capsys
):
    """Installed-and-correctly-named is not sufficient.

    The official distribution can sit on the box while the imported code came
    from somewhere else. A check that stopped at the name would clear exactly
    the arrangement it exists to catch.
    """
    _pretend_installed(monkeypatch, tmp_path)
    elsewhere = tmp_path / "elsewhere" / "jcodemunch_mcp"
    elsewhere.mkdir(parents=True)
    spy["set_official"](_Dist(elsewhere))
    spy["returns"] = {"jcodemunch_mcp": ["jcodemunch-mcp-evil"]}

    security.verify_package_integrity()

    assert spy["n"] == 1
    assert "jcodemunch-mcp-evil" in capsys.readouterr().err


def test_check_never_raises_on_hostile_metadata(spy, monkeypatch, tmp_path):
    """Startup must survive a metadata layer that misbehaves."""
    _pretend_installed(monkeypatch, tmp_path)

    def exploding(name):
        raise RuntimeError("metadata backend is on fire")

    sys.modules["importlib.metadata"].distribution = exploding

    def exploding_map():
        raise RuntimeError("still on fire")

    sys.modules["importlib.metadata"].packages_distributions = exploding_map

    security.verify_package_integrity()  # must not raise
