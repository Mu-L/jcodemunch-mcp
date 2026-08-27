"""A Racket config change re-parses unchanged files exactly once.

`racket_definition_forms` and `racket_langs` change what the Racket parser
EMITS for identical bytes, and the incremental indexer skips identical bytes
by design. So a declaration added after an index existed applied to nothing:
measured before this existed, `check-admin ABSENT` across an incremental
reindex and present only after a full one. That is the "parameter present and
doing nothing" defect (#508) wearing the config key's name.

The fix is the `PARSER_GENERATION` mechanism scoped to one project's config:
the digest of both keys is stamped on the index at save, and a mismatch at
the next index forces one full re-parse with its own `rebuild_reason`.

⚠ Every test here goes through `index_folder`, not the parser: the defect
was never in the parser.
"""
import pytest

from jcodemunch_mcp import config as _config
from jcodemunch_mcp.storage.index_store import IndexStore
from jcodemunch_mcp.tools.index_folder import index_folder

MAIN = ("#lang racket/base\n"
        "(define (plain) 1)\n"
        "(defstep (check-admin) (void))\n"
        "(provide plain)\n")


@pytest.fixture
def project(tmp_path):
    src = tmp_path / "src"
    store = tmp_path / "store"
    src.mkdir()
    store.mkdir()
    (src / "main.rkt").write_text(MAIN, encoding="utf-8")
    yield src, store
    _config.invalidate_project_config_cache(str(src))


def _index(src, store, **kw):
    r = index_folder(str(src), use_ai_summaries=False, storage_path=str(store),
                     context_providers=False, **kw)
    assert r["success"] is True, r
    return r


def _names(r, store):
    owner, name = r["repo"].split("/", 1)
    idx = IndexStore(str(store)).load_index(owner, name)
    return {s["name"] for s in idx.symbols}, idx


def _declare(src, forms: dict):
    import json
    (src / ".jcodemunch.jsonc").write_text(
        json.dumps({"racket_definition_forms": forms}), encoding="utf-8")
    _config.invalidate_project_config_cache(str(src))


def test_a_declaration_added_after_the_index_applies_on_the_next_incremental_index(project):
    """⚠ The measured defect. The file is untouched between the two runs."""
    src, store = project
    r1 = _index(src, store)
    names, idx = _names(r1, store)
    assert "plain" in names and "check-admin" not in names
    assert idx.racket_config_digest == "", "an unconfigured project carries no digest"

    _declare(src, {"defstep": "function"})
    r2 = _index(src, store)                       # incremental, default
    names, idx = _names(r2, store)
    assert "check-admin" in names
    assert r2.get("rebuild_reason") == "racket_config_changed"
    assert idx.racket_config_digest == _config.racket_config_digest(str(src)) != ""


def test_the_re_parse_happens_once_not_every_run(project):
    src, store = project
    _index(src, store)
    _declare(src, {"defstep": "function"})
    _index(src, store)
    r3 = _index(src, store)
    assert r3.get("rebuild_reason") is None, "the stamp matches; no escalation"


def test_removing_the_declaration_re_parses_too(project):
    """A stale name must leave the index the same way it arrived."""
    src, store = project
    _declare(src, {"defstep": "function"})
    r1 = _index(src, store)
    assert "check-admin" in _names(r1, store)[0]
    _declare(src, {})
    r2 = _index(src, store)
    assert r2.get("rebuild_reason") == "racket_config_changed"
    assert "check-admin" not in _names(r2, store)[0]


def test_racket_langs_is_part_of_the_digest(project):
    src, store = project
    (src / "doc.rkt").write_text("#lang mylang\n(define (from-mylang) 1)\n", encoding="utf-8")
    r1 = _index(src, store)
    assert "from-mylang" not in _names(r1, store)[0], "an unknown lang is text"
    import json
    (src / ".jcodemunch.jsonc").write_text(json.dumps({"racket_langs": {"mylang": "sexp"}}))
    _config.invalidate_project_config_cache(str(src))
    r2 = _index(src, store)
    assert r2.get("rebuild_reason") == "racket_config_changed"
    assert "from-mylang" in _names(r2, store)[0]


def test_a_project_without_racket_never_escalates(tmp_path):
    src = tmp_path / "src"
    store = tmp_path / "store"
    src.mkdir()
    store.mkdir()
    (src / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    _index(src, store)
    import json
    (src / ".jcodemunch.jsonc").write_text(json.dumps({"racket_definition_forms": {"defstep": "function"}}))
    _config.invalidate_project_config_cache(str(src))
    r2 = _index(src, store)
    assert r2.get("rebuild_reason") is None
    _config.invalidate_project_config_cache(str(src))


def test_digest_is_stable_and_order_independent():
    """The stamp must not differ between two runs over the same config."""
    import json
    a = json.loads(json.dumps({"defstep": "function", "defvar": "constant"}))
    b = {"defvar": "constant", "defstep": "function"}
    from unittest import mock
    with mock.patch.object(_config, "get", lambda key, default=None, repo=None: a if key == "racket_definition_forms" else {}):
        da = _config.racket_config_digest("/p")
    with mock.patch.object(_config, "get", lambda key, default=None, repo=None: b if key == "racket_definition_forms" else {}):
        db = _config.racket_config_digest("/p")
    assert da == db != ""
    with mock.patch.object(_config, "get", lambda key, default=None, repo=None: {}):
        assert _config.racket_config_digest("/p") == ""
