"""H3, the registered predicate. Committed BEFORE any case exists.

    The discriminator between `search_symbols` and `search_text` is whether the
    thing the task is asking about IS an indexed symbol name in the repository
    the task refers to.

⚠⚠ **This file must not be edited after the generator lands.** The whole value of
this directory is that `git log` shows the predicate preceding the cases. A
predicate adjusted once results exist is a fitting pass, and the corpus is small
enough that one such pass would spend it. If this predicate is wrong, the honest
move is to record that it was wrong.

⚠ **Coverage is 100% by construction** — `predict` always returns one of the two
classes. H1 (identifier shape) and H2 (imperative verb) both died on coverage:
each fired on 5–15% of queries while the decision needs answering every time. A
predicate that abstains is not a candidate for this problem.

See `PROTOCOL.md` for what a positive result may and may not be used for.
"""
from __future__ import annotations

import re

SYMBOLS = "search_symbols"
TEXT = "search_text"

# Ordinary English that carries no signal about the target. Deliberately SHORT:
# a long hand-tuned list is a place to hide fitting, and every word removed here
# is a word the predicate can no longer match a symbol name on.
_STOPWORDS = frozenset("""
a an the this that these those there here
is are was were be been being am
do does did doing done
have has had having
i we you it they he she them us our your their its
and or but not no nor so if then than as
of in on at to from by for with without into onto over under
about across after before between during through
what which who whom whose where when why how
can could should would may might must will shall
find locate show tell give get list search look check verify determine
me my mine us
any all some each every both few more most other another
does whether if
code file files function functions method methods class classes
project repo repository codebase source
""".split())

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SPLIT = re.compile(r"[_\-]+|(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

# A part shorter than this is too common to be evidence — `id`, `db`, `on`
# appear inside enormous numbers of symbol names and would match everything.
_MIN_PART = 3


def _parts(name: str) -> set[str]:
    """snake_case / camelCase / kebab-case components of an identifier, lowered."""
    out = set()
    for piece in _SPLIT.split(name or ""):
        piece = piece.strip().lower()
        if len(piece) >= _MIN_PART:
            out.add(piece)
    whole = (name or "").strip().lower()
    if len(whole) >= _MIN_PART:
        out.add(whole)
    return out


def symbol_vocabulary(symbol_names) -> set[str]:
    """Every token an indexed symbol name can be matched on.

    Built once per repository from the index; the predicate compares against
    this, never against the corpus or the labels.
    """
    vocab: set[str] = set()
    for name in symbol_names:
        vocab |= _parts(name)
    return vocab


def task_tokens(task: str) -> list[str]:
    """Content words of a task string, stopwords removed."""
    out = []
    for word in _WORD.findall(task or ""):
        low = word.lower()
        if low in _STOPWORDS or len(low) < _MIN_PART:
            continue
        out.append(word)
    return out


def predict(task: str, vocabulary: set[str]) -> str:
    """Registered H3. Returns SYMBOLS or TEXT — never abstains."""
    return SYMBOLS if matched_tokens(task, vocabulary) else TEXT


def matched_tokens(task: str, vocabulary: set[str]) -> list[str]:
    """Which task tokens matched the symbol vocabulary.

    Exposed so a result can be inspected for the leakage failure mode: if the
    matches are the target's own name, the predicate won for free and the run
    must be discarded rather than explained.
    """
    hits = []
    for word in task_tokens(task):
        if _parts(word) & vocabulary:
            hits.append(word)
    return hits
