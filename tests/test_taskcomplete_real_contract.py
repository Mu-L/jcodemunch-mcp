"""The taskcomplete hook against the REAL producer, with no mock (#559).

⚠⚠ **The untested diagnostic was dark for its whole life and a green test said
otherwise.** ``taskcomplete`` read ``untested.get("untested_symbols", [])``;
``get_untested_symbols`` has never emitted that key -- it emits ``symbols`` --
so the read fell through to ``[]`` on every real invocation.

⚠⚠ **The test guarding it could not see that, because its mock supplied the
invented contract**: ``lambda ...: {"untested_symbols": [...]}``. A fabricated
producer makes an absent-key defect *structurally* invisible to a test written
about that very code path. This is the standing "a mock broad enough to satisfy
an assertion can bypass what the assertion is about" lesson at its sharpest --
the mock did not merely paper over the check, it asserted a contract the
producer does not have.

⚠ So this file mocks NO producer. It indexes a real repository, runs the real
tool through the real hook, and asserts the rendered message. That is the only
shape of test that could have caught the original.

⚠⚠ **Deliberately its own file.** The same tests placed at the end of
`test_hook_steering_fixes.py` passed alone and failed after the 56 tests before
them, which install a MagicMock `IndexStore` throughout. The leak is real and
worth its own investigation, but a guard whose verdict depends on what ran
before it is not a guard -- and the thing under test here is the response
contract, not test isolation. Do not fold this back in.
"""

from __future__ import annotations

import io
import json
import sys
from unittest import mock

import pytest

from jcodemunch_mcp.cli.hooks import run_taskcomplete


def _run(func, stdin_text: str) -> tuple[int, str, str]:
    fake_in, fake_out, fake_err = (
        io.StringIO(stdin_text), io.StringIO(), io.StringIO(),
    )
    with mock.patch.object(sys, "stdin", fake_in), \
         mock.patch.object(sys, "stdout", fake_out), \
         mock.patch.object(sys, "stderr", fake_err):
        rc = func()
    return rc, fake_out.getvalue(), fake_err.getvalue()


@pytest.fixture
def real_repo(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text(
        "def session_sym():\n    return 1\n", encoding="utf-8"
    )
    storage = tmp_path / ".index"
    from jcodemunch_mcp.tools.index_folder import index_folder
    result = index_folder(
        str(tmp_path), use_ai_summaries=False, storage_path=str(storage)
    )
    monkeypatch.setenv("CODE_INDEX_PATH", str(storage))
    monkeypatch.setattr(
        "jcodemunch_mcp.tools.session_state.load_live_journal",
        lambda **kw: {"files_edited": [{"file": "src/a.py", "edits": 1}]},
    )
    return result["repo"], str(storage)


def test_the_tool_does_not_emit_the_key_the_hook_used_to_ask_for(real_repo):
    """Non-vacuity, and the whole finding in one assertion."""
    from jcodemunch_mcp.tools.get_untested_symbols import get_untested_symbols

    repo_id, storage = real_repo
    out = get_untested_symbols(repo_id, max_results=5, storage_path=storage)
    assert "symbols" in out
    assert "untested_symbols" not in out, (
        "if this key ever appears, the mocks in test_hook_steering_fixes.py "
        "stop being wrong and this file stops proving anything -- reconcile "
        "the two deliberately rather than deleting either"
    )


def test_the_fixture_really_has_an_untested_symbol(real_repo):
    """Second non-vacuity gate: an empty result renders nothing for an honest
    reason, and would pass the message assertion below for the wrong one."""
    from jcodemunch_mcp.tools.get_untested_symbols import get_untested_symbols

    repo_id, storage = real_repo
    out = get_untested_symbols(repo_id, max_results=5, storage_path=storage)
    assert out["untested_count"] == 1
    assert out["symbols"][0]["name"] == "session_sym"


def _message(out: str) -> str:
    return (json.loads(out) if out.strip() else {}).get("systemMessage", "")


def _section(msg: str, heading: str) -> str:
    """The lines under one `**Heading:**` block, up to the next block.

    ⚠⚠ Written after the first version of this test PASSED against the
    reintroduced defect. It asserted `"session_sym" in msg`, and the name
    appears in THREE sections -- so `Unreferenced:` satisfied it while the
    untested block rendered nothing. **An assertion that does not name which
    producer put the string there proves nothing about that producer.**
    """
    if heading not in msg:
        return ""
    tail = msg.split(heading, 1)[1]
    return tail.split("**", 1)[0]


def test_the_untested_symbol_reaches_the_agent_facing_message(real_repo):
    _, out, _ = _run(run_taskcomplete, '{"hook_event_name": "TaskCompleted"}')
    msg = _message(out)
    section = _section(msg, "**No test coverage:**")
    assert section, f"the untested block did not render at all: {msg!r}"
    assert "session_sym" in section, (
        f"the untested block rendered without naming the symbol: {section!r}"
    )


def test_the_orphan_block_names_the_symbol_instead_of_a_question_mark(real_repo):
    """⚠ `find_dead_code` rows carry `symbol_id` and no `name`, so this block
    printed ``- `?` (src/a.py:0)`` for every orphan -- a diagnostic naming
    nothing, with a line number that was always a lie rather than a miss."""
    _, out, _ = _run(run_taskcomplete, '{"hook_event_name": "TaskCompleted"}')
    section = _section(_message(out), "**Possibly orphaned:**")
    assert section, "the orphan block did not render at all"
    assert "`?`" not in section, f"orphan rendered with no name: {section!r}"
    assert "session_sym" in section, section
