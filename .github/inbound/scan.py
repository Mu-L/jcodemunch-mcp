"""Plain-text scan of inbound text before any model sees it
(docs/inbound/POLICY.md section 1 rule 1 and section 4.3).

purpose:  find the security keywords that make an item `security` and the
          instruction patterns that make it escalate, in the RAW text:
          HTML comments, <details>, code fences, entities and zero-width
          characters are all read, never stripped away first
invokes:  nothing outside the standard library
produces: JSON {"security": [...], "injection": [...]} with the matched
          text and its offset; exit 0 always (the caller decides)
refuses:  to classify; this is a tripwire, not the classifier
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import unicodedata
from pathlib import Path

# Characters an author can hide text with. Removed BEFORE matching so
# "cred​ential" still reads as "credential".
_ZERO_WIDTH = re.compile("[​‌‍⁠﻿­͏᠎]")

# POLICY section 1 rule 1. Word-ish boundaries; case-insensitive.
SECURITY_TERMS = [
    r"vulnerab\w*",
    r"exploit\w*",
    r"\bCVE-\d{4}-\d+",
    r"\bGHSA-[\w-]+",
    r"credential\w*",
    r"\btokens?\b(?!\s*(?:saved|counts?|budget|per|cost|usage|econom|meter|window))",
    r"\bsecrets?\b",
    r"private[ -]keys?",
    r"key ?material",
    r"\bapi[_ -]?keys?\b",
    r"path (?:escape|traversal)",
    r"\btraversal\b",
    r"arbitrary (?:file )?(?:write|read|code)",
    r"cross[- ]repo\w*",
    r"(?:data|information) (?:exposure|leak\w*|disclos\w*)",
    r"redact\w* (?:fail|miss|bypass)\w*",
    r"\bRCE\b",
    r"remote code execution",
    r"privilege escalation",
    r"\bsandbox escape",
]

# POLICY section 4.3. Each is a pattern over normalised text.
INJECTION_PATTERNS = [
    r"ignore (?:all |the )?(?:previous|prior|above|earlier) (?:instructions?|prompts?|rules?)",
    r"(?:disable|skip|bypass|remove|modify|change|edit|update|turn off)\s+(?:[\w.\-/`'\"]+\s+){0,4}?(?:workflow|github action|hook|permission|secret|variable|branch protection|codeowners|ruleset)s?\b",
    r"(?:edit|change|modify|loosen|lower|raise|update|rewrite)\s+(?:the |your )?(?:standard\.md|thresholds?\.json|retired\.json|archaeology\.md|security\.md|license|policy\.md)",
    r"(?:post|send|upload|report|exfiltrate|forward|curl|wget)\b[^\n]{0,80}\b(?:https?://|webhook|@\w+\.\w+|to my server|to this url)",
    r"(?:approve|merge|close|tag|release|publish)\s+(?:this|the|your|my)\s+(?:pr|pull request|issue|release|tag|version)",
    r"(?:print|reveal|show|dump|echo|output)\s+(?:your |the )?(?:system prompt|instructions|configuration|config|secrets?|environment|env vars?|token|api key|~/\.claude)",
    r"\b(?:the maintainer|jgravelle|anthropic|github|the owner) (?:said|says|told|approved|authori[sz]ed|allows?|wants) (?:you|this|that)",
    r"you are (?:now )?(?:allowed|authori[sz]ed|permitted|cleared) to",
    r"\bnew (?:policy|instructions?|rules?)\b",
    r"(?:override|test|debug|maintenance|emergency|admin|developer) mode",
    r"(?:^|\n)\s*(?:system|assistant|developer)\s*:\s",
    r"\[INST\]|<\|im_start\|>|<\|system\|>|<<SYS>>|\[system\]",
    r"curl [^\n]*\|\s*(?:ba|z)?sh\b",
    r"pip install [^\n]*--index-url (?!https://pypi\.org)",
    r"as (?:agreed|discussed|approved|instructed) (?:with|by|earlier|before)",
]

_SEC = [re.compile(p, re.IGNORECASE) for p in SECURITY_TERMS]
_INJ = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def normalise(text: str) -> str:
    """Unescape entities, drop zero-width characters, fold compatibility
    forms (full-width letters, ligatures) to ASCII-ish. HTML comments,
    <details> and code fences are NOT removed: the point is to read them."""
    t = html.unescape(text or "")
    t = _ZERO_WIDTH.sub("", t)
    t = unicodedata.normalize("NFKC", t)
    return t


def scan(text: str) -> dict:
    t = normalise(text)
    out = {"security": [], "injection": []}
    for rx in _SEC:
        for m in rx.finditer(t):
            out["security"].append({"match": m.group(0), "at": m.start()})
    for rx in _INJ:
        for m in rx.finditer(t):
            out["injection"].append(
                {"match": m.group(0)[:120], "at": m.start(), "pattern": rx.pattern[:60]}
            )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "path", nargs="?", type=Path, help="file to scan; stdin when omitted"
    )
    args = ap.parse_args(argv)
    text = args.path.read_text(encoding="utf-8") if args.path else sys.stdin.read()
    res = scan(text)
    res["security_hit"] = bool(res["security"])
    res["injection_hit"] = bool(res["injection"])
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
