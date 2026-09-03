"""SECURITY.md's limits table must state the code's defaults.

Found 2026-09-03 (docs/standard/DISCOVERY.md section 6): the table says
"File count limit ... 500 files" while `security.DEFAULT_MAX_INDEX_FILES` is
10,000 and `DEFAULT_MAX_FOLDER_FILES` 2,000. A security document that
understates a limit by 20x is a defect in the document. Per the build rules
this test is NOT weakened to pass: it is a strict xfail that names the
finding, and it turns into a hard pass the moment the doc is corrected
(strict=True fails if it unexpectedly passes, so the marker must be removed
with the fix).
"""

from __future__ import annotations

import re

import pytest

from harness import thresholds as T

REPO = T.REPO_ROOT


def _table_row(label: str) -> str:
    text = (REPO / "SECURITY.md").read_text(encoding="utf-8")
    m = re.search(rf"^\|\s*{re.escape(label)}\s*\|[^|]*\|\s*([^|]+?)\s*\|", text, re.M)
    assert m, f"SECURITY.md has no limits-table row {label!r}"
    return m.group(1)


def test_file_size_limit_row_matches_code():
    from jcodemunch_mcp import security
    cell = _table_row("File size limit")
    kb = int(re.search(r"(\d+)\s*KB", cell).group(1))
    assert kb * 1024 == security.DEFAULT_MAX_FILE_SIZE, f"SECURITY.md says {cell}; code default is {security.DEFAULT_MAX_FILE_SIZE} bytes"


@pytest.mark.xfail(strict=True, reason="FINDINGS.md F-01: SECURITY.md says 500 files; security.DEFAULT_MAX_INDEX_FILES is 10,000 and DEFAULT_MAX_FOLDER_FILES 2,000. Doc fix pending; remove this marker with it.")
def test_file_count_limit_row_matches_code():
    from jcodemunch_mcp import security
    cell = _table_row("File count limit")
    nums = [int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", cell)]
    assert security.DEFAULT_MAX_INDEX_FILES in nums or security.DEFAULT_MAX_FOLDER_FILES in nums, (
        f"SECURITY.md says {cell!r}; code defaults are {security.DEFAULT_MAX_INDEX_FILES} / {security.DEFAULT_MAX_FOLDER_FILES}"
    )
