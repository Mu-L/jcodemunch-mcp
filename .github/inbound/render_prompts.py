"""Render the policy's fixed blocks into every headless prompt file
(docs/inbound/DESIGN.md D5 and section 8).

purpose:  the untrusted-input preamble (POLICY 4.2) and the never-touch
          list (POLICY 4.4) reach each prompt by GENERATION, never retyped;
          a prompt edit needs a version bump before it can be re-rendered
invokes:  nothing outside the standard library
produces: `--write` rewrites the marked regions and VERSIONS.json;
          `--check` exits 1 naming every prompt whose rendered blocks, or
          whose recorded sha, differ from what is on disk
refuses:  `--write` when a prompt's content changed and its `version:` did
          not (DESIGN section 8)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
POLICY = ROOT / "docs" / "inbound" / "POLICY.md"
PROMPTS = HERE / "prompts"
VERSIONS = PROMPTS / "VERSIONS.json"

BEGIN = "<!-- BEGIN policy:{name} -->"
END = "<!-- END policy:{name} -->"

CRLF = "\r\n"
LF = "\n"


def _read(p: Path) -> str:
    """Newline-normalised: a CRLF checkout must read like the LF tree it was
    rendered from, or the check fails on Windows and passes on CI."""
    return p.read_text(encoding="utf-8").replace(CRLF, LF)


def sha_of(text: str) -> str:
    return hashlib.sha256(text.replace(CRLF, LF).encode("utf-8")).hexdigest()


def _fenced_block_after(text: str, heading: str) -> str:
    """The first ``` fenced block after ``heading``, without the fences."""
    i = text.index(heading)
    m = re.search(r"```[^\n]*\n(.*?)\n```", text[i:], re.S)
    if not m:
        raise ValueError(f"no fenced block after {heading!r}")
    return m.group(1)


def policy_blocks(policy_text: str) -> dict[str, str]:
    return {
        "preamble": _fenced_block_after(policy_text, "### 4.2 The preamble"),
        "never-touch": _fenced_block_after(policy_text, "### 4.4 The never-touch list"),
    }


def policy_sha(policy_text: str) -> str:
    return sha_of(policy_text)


def render(prompt_text: str, blocks: dict[str, str], psha: str) -> str:
    out = prompt_text
    for name, body in blocks.items():
        b, e = BEGIN.format(name=name), END.format(name=name)
        if b not in out or e not in out:
            raise ValueError(f"prompt lacks markers for {name}")
        pre, rest = out.split(b, 1)
        _, post = rest.split(e, 1)
        out = f"{pre}{b}\n{body}\n{e}{post}"
    out = re.sub(
        r"^policy_sha256:.*$", f"policy_sha256: {psha}", out, count=1, flags=re.M
    )
    return out


def front_matter(prompt_text: str) -> dict:
    m = re.match(r"---\n(.*?)\n---\n", prompt_text, re.S)
    if not m:
        raise ValueError("prompt has no front matter")
    fm = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    for k in ("version", "model", "job", "policy_sha256"):
        if k not in fm:
            raise ValueError(f"front matter lacks {k}")
    int(fm["version"])
    return fm


def prompt_files() -> list[Path]:
    return sorted(p for p in PROMPTS.glob("*.md"))


def _versions(path: Path) -> dict:
    return json.loads(_read(path)) if path.exists() else {}


def check(
    policy_path: Path = POLICY,
    prompts: list[Path] | None = None,
    versions_path: Path = VERSIONS,
) -> list[str]:
    ptext = _read(policy_path)
    blocks, psha = policy_blocks(ptext), policy_sha(ptext)
    versions = _versions(versions_path)
    problems = []
    for p in prompts or prompt_files():
        text = _read(p)
        try:
            fm = front_matter(text)
        except ValueError as e:
            problems.append(f"{p.name}: {e}")
            continue
        if render(text, blocks, psha) != text:
            problems.append(
                f"{p.name}: rendered blocks or policy sha differ from POLICY.md; run render_prompts.py --write"
            )
        rec = versions.get(p.stem)
        if not rec:
            problems.append(f"{p.name}: no VERSIONS.json entry")
        elif (
            rec.get("sha256") != sha_of(text)
            or str(rec.get("version")) != fm["version"]
        ):
            problems.append(
                f"{p.name}: content or version differs from VERSIONS.json (edited without --write, or --write refused)"
            )
    return problems


def write(
    policy_path: Path = POLICY,
    prompts: list[Path] | None = None,
    versions_path: Path = VERSIONS,
) -> list[str]:
    ptext = _read(policy_path)
    blocks, psha = policy_blocks(ptext), policy_sha(ptext)
    versions = _versions(versions_path)
    refused = []
    for p in prompts or prompt_files():
        text = _read(p)
        fm = front_matter(text)
        new = render(text, blocks, psha)
        rec = versions.get(p.stem, {})
        if (
            rec
            and rec.get("sha256") != sha_of(new)
            and str(rec.get("version")) == fm["version"]
        ):
            refused.append(
                f"{p.name}: content changed but version is still {fm['version']}; bump `version:` first"
            )
            continue
        p.write_text(new, encoding="utf-8", newline=LF)
        versions[p.stem] = {
            "version": int(fm["version"]),
            "model": fm["model"],
            "sha256": sha_of(new),
            "policy_sha256": psha,
        }
    versions_path.write_text(
        json.dumps(versions, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline=LF,
    )
    return refused


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    problems = write() if args.write else check()
    for line in problems:
        print(line)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
