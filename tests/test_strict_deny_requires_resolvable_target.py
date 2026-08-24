"""A strict deny requires a target the hook can actually resolve (#541).

`_handle_bash` judges indexed-root overlap on `cwd` alone, and relies on
`_bash_targets_outside_roots` to stay quiet when the command names a path jcm
cannot serve. That guard reads path tokens out of the RAW command string, so it
is blind to anything the shell has not expanded yet.

⚠⚠ **The reported pair: `grep ~/x.md` was allowed and `grep $HOME/x.md` was
denied. Same destination, opposite verdicts.** Advisory mode made that a
harmless extra nudge; strict mode made it blocked work.

⚠ **This is not a regex gap to close.** `_handle_bash` deliberately does not
parse shell — the hook cannot know what `$B` holds and guessing is worse than
not looking. The caution already exists everywhere else in that function:
`find` is never deniable (`find … -delete` opens with the same word), a
pipeline is never denied (the non-search half is real work), and `../` returns
silent rather than resolving where it lands. The unexpanded-expansion case is
the same shape, and was the one place the rule was not applied.

⚠⚠ **The fix must not weaken strict mode, which is the whole reason someone
turned it on.** A trailing `$` is a regex end-anchor, and `grep -n "foo$" src/`
is idiomatic — suppressing the deny on any `$` would stop denying one of the
commonest in-repo searches. The anchor cases below are as load-bearing as the
expansion cases; a blunt `\\$` passes half this file and fails the other half.
"""

from __future__ import annotations

import json

import pytest

from jcodemunch_mcp.cli.hooks import steering


# A root the TEST owns. Nothing here touches the developer's real index --
# conftest isolates CODE_INDEX_PATH, so a fixture that needed a real indexed
# repo would skip locally AND in CI, and 11 skips is a file that reports
# success while checking nothing (the v1.108.293 defect class).
@pytest.fixture
def indexed(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    norm = steering._norm_path(str(root))
    monkeypatch.setattr(steering, "_indexed_source_roots", lambda: [norm])
    return str(root)


def _verdict(capsys, command: str, cwd: str, *, mode: str = "strict") -> str:
    """Classify what the Bash branch emits for one command."""
    capsys.readouterr()
    steering._handle_bash({"command": command}, cwd, mode)
    out = capsys.readouterr().out.strip()
    if not out:
        return "allow"
    block = json.loads(out).get("hookSpecificOutput", {})
    return "deny" if block.get("permissionDecision") == "deny" else "nudge"


# Every one of these targets a path OUTSIDE every indexed root, written so the
# hook cannot see it. None may be denied.
UNRESOLVABLE = [
    pytest.param('grep -n p "$B/x.md"', id="dollar-var"),
    pytest.param('grep -n p "${B}/x.md"', id="braced-var"),
    pytest.param("grep -n p $HOME/x.md", id="dollar-home"),
    pytest.param("grep -n p $(dirname $X)/f.md", id="command-substitution"),
    pytest.param("grep -n p `pwd`/f.md", id="backticks"),
]

# In-repo searches the hook CAN resolve. Strict mode must still deny these --
# they are the reason someone enabled it.
STILL_DENIED = [
    pytest.param("grep -rn pattern src/", id="plain-in-repo"),
    pytest.param('grep -n "foo$" src/', id="regex-end-anchor"),
    pytest.param('grep -n "^def .*$" src/', id="anchored-pattern"),
]


@pytest.mark.parametrize("command", UNRESOLVABLE)
def test_unresolvable_target_is_never_denied(capsys, command, indexed):
    assert _verdict(capsys, command, indexed) != "deny", (
        f"strict mode denied {command!r}, whose target depends on a shell "
        "expansion the hook cannot resolve. The same path written literally "
        "is allowed, so this blocks real work while claiming the search "
        "targets an indexed repo."
    )


@pytest.mark.parametrize("command", STILL_DENIED)
def test_resolvable_in_repo_search_is_still_denied(capsys, command, indexed):
    """⚠ The half that stops the fix from becoming a strict-mode regression."""
    assert _verdict(capsys, command, indexed) == "deny", (
        f"strict mode stopped denying {command!r}. A trailing `$` is a regex "
        "end-anchor, not a shell expansion -- treating it as unresolvable "
        "silently disables enforcement the user opted into."
    )


def test_a_downgraded_deny_still_steers(capsys, indexed):
    """Downgrade to a nudge, not to silence.

    A wrong nudge is a sentence of text; a wrong deny is blocked work. Going
    silent would trade one failure for a quieter one.
    """
    assert _verdict(capsys, 'grep -n p "$B/x.md"', indexed) == "nudge"


def test_advisory_mode_is_unchanged(capsys, indexed):
    """The default tier never denied, and must not start caring about this."""
    assert _verdict(capsys, 'grep -n p "$B/x.md"', indexed, mode="advisory") == "nudge"
    assert _verdict(capsys, "grep -rn pattern src/", indexed, mode="advisory") == "nudge"


def test_literal_outside_paths_still_pass_silently(capsys, indexed, tmp_path):
    """The guard that already worked keeps working -- not re-implemented."""
    outside = (tmp_path / "elsewhere" / "x.md").as_posix()
    assert _verdict(capsys, f"grep -n p {outside}", indexed) == "allow"
    assert _verdict(capsys, "grep -n p ../x.md", indexed) == "allow"


# --- the second finding, surfaced BY the test above ---------------------------
#
# ⚠⚠ A native Windows absolute path was invisible to `_BASH_PATH_TOKEN_RE`,
# which only recognised POSIX-style roots. `/c/Users/j/x.md` (git-bash) was
# seen; `C:/Users/j/x.md` was not, so strict mode denied a search whose target
# sits outside every indexed root -- on the platform most users are on.
#
# ⚠ Unlike a `$VAR` this is genuinely resolvable, so the remedy is a real fix
# (see the target) rather than the downgrade the expansion half gets. These
# cases assert the OUTCOME both ways: outside allows, inside still denies.

WINDOWS_OUTSIDE = [
    pytest.param("C:/Users/j/x.md", id="drive-forward-slash"),
    pytest.param(r"C:\Users\j\x.md", id="drive-backslash"),
    pytest.param('"C:/Program Files/x.md"', id="quoted-with-space"),
    pytest.param("D:/other/repo/src", id="other-drive"),
]


@pytest.mark.parametrize("target", WINDOWS_OUTSIDE)
def test_windows_absolute_path_outside_roots_is_not_denied(capsys, target, indexed):
    assert _verdict(capsys, f"grep -n pattern {target}", indexed) != "deny", (
        f"strict mode denied a search for {target!r}, which is outside every "
        "indexed root. The git-bash spelling of the same path was already "
        "allowed, so the verdict depended on how the user spelled the drive."
    )


def test_windows_absolute_path_inside_the_repo_is_still_denied(capsys, indexed):
    """⚠ The other half: widening the token regex must not stop it denying.

    Without this, deleting the drive-letter alternative and returning "outside"
    for everything would pass every case above.
    """
    inside = indexed.replace("\\", "/") + "/src"
    assert _verdict(capsys, f"grep -rn pattern {inside}", indexed) == "deny"
