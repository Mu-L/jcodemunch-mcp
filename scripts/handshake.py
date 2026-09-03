"""Real stdio `initialize` against an INSTALLED jcodemunch-mcp.  `python scripts/handshake.py --expect-version X.Y.Z`

Exit 0 only when the wire carries `serverInfo.version == --expect-version`
and a non-empty `instructions` string. Prints the JSON it saw either way.

Why this is a separate probe (ENFORCEMENT-PLAN item 5, #536): `__version__`
is `"unknown"` under `PYTHONPATH=src`, so every test in this suite and every
CI leg runs from source and cannot see what the published artifact puts on
the wire. The 1.108.293 handshake was done by hand once and never since.
This script is meant to run from a FRESH venv holding only
`jcodemunch-mcp==X.Y.Z` from PyPI (see .github/workflows/handshake.yml); it
imports nothing from the repository and refuses if the server it spawns is
being served out of a source tree.

⚠ Never run this through bare `uvx`: it served a cached 1.108.275 once and
reproduced the pre-fix symptoms exactly (ISSUE-HISTORY 2026-08-24).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile


async def probe(command: str, timeout: float) -> dict:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = dict(os.environ)
    # A scratch index root: the server must not write into a runner's home
    # and a first-ever install here must not be mistaken for the maintainer's.
    env.setdefault("CODE_INDEX_PATH", tempfile.mkdtemp(prefix="jcm-handshake-"))
    env.setdefault("JCODEMUNCH_NO_VERSION_HINT", "1")
    params = StdioServerParameters(command=command, args=[], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await asyncio.wait_for(session.initialize(), timeout)
            tools = await asyncio.wait_for(session.list_tools(), timeout)
    return {
        "serverInfo": {"name": init.serverInfo.name, "version": init.serverInfo.version},
        "instructions": init.instructions or "",
        "protocolVersion": init.protocolVersion,
        "tool_count": len(tools.tools),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect-version", required=True)
    ap.add_argument("--command", default="jcodemunch-mcp", help="server executable on PATH (the installed console script)")
    ap.add_argument("--timeout", type=float, default=60.0)
    a = ap.parse_args(argv)

    exe = shutil.which(a.command)
    if not exe:
        print(f"FAIL: {a.command!r} not on PATH; install jcodemunch-mcp=={a.expect_version} into this venv first")
        return 1
    print(f"server: {exe}")

    try:
        seen = asyncio.run(probe(exe, a.timeout))
    except Exception as e:  # a hung or crashed handshake is the defect this exists to see
        print(f"FAIL: handshake did not complete: {type(e).__name__}: {e}")
        return 1
    print(json.dumps({**seen, "instructions": seen["instructions"][:200] + ("..." if len(seen["instructions"]) > 200 else "")}, indent=2))

    ok = True
    if seen["serverInfo"]["name"] != "jcodemunch-mcp":
        print(f"FAIL: serverInfo.name is {seen['serverInfo']['name']!r}")
        ok = False
    if seen["serverInfo"]["version"] != a.expect_version:
        # The SDK's own version here (e.g. 1.26.0) means `Server(..., version=)` was dropped.
        print(f"FAIL: serverInfo.version is {seen['serverInfo']['version']!r}, expected {a.expect_version!r}")
        ok = False
    if not seen["instructions"].strip():
        print("FAIL: instructions is empty (the only prose that survives tool deferral)")
        ok = False
    if seen["tool_count"] == 0:
        print("FAIL: list_tools returned nothing")
        ok = False
    print("HANDSHAKE", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
