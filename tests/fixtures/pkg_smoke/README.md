# pkg_smoke

A ten-file repo for the packaging smoke test (docs/cicd/DESIGN.md stage 3).
`scripts/handshake.py --fixture` indexes it through an INSTALLED
jcodemunch-mcp over stdio and calls `search_symbols` + `get_symbol_source`.
Two languages, so a missing grammar wheel or package-data file shows up here
and nowhere in the unit tests (they run from source).
