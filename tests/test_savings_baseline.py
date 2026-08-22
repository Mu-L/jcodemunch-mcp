"""The savings baseline counts each byte of source once.

``raw_bytes`` is the "what would this have cost to read by hand" side of every
tokens_saved figure we publish. Two ways of building it over-counted:

  1. ``sum(byte_length for s in symbols)`` counts nested spans once per level —
     a class's span already covers its methods. Measured at 2.85x the real size
     of the files it describes on this repo, 25.1% above the merged spans.
  2. ``file_sizes[sym["file"]]`` summed PER SYMBOL charges a file once for every
     symbol selected from it — 12.3x at 40 symbols, 32.2x at 1000.

Both inflate a number we publish about ourselves, so these are written as
properties over the whole tree rather than assertions about the seven sites the
first pass happened to find.
"""

import json
import re
from pathlib import Path

from jcodemunch_mcp.tools._utils import distinct_file_bytes, symbol_span_bytes

SRC = Path(__file__).resolve().parent.parent / "src" / "jcodemunch_mcp"


class TestSymbolSpanBytes:
    def test_nested_spans_counted_once(self):
        syms = [
            {"file": "a.py", "byte_offset": 0, "byte_length": 300},    # class
            {"file": "a.py", "byte_offset": 40, "byte_length": 100},   # method
            {"file": "a.py", "byte_offset": 150, "byte_length": 100},  # method
        ]
        assert symbol_span_bytes(syms) == 300
        # The number this replaces, on the record.
        assert sum(s["byte_length"] for s in syms) == 500

    def test_sums_across_files(self):
        syms = [
            {"file": "a.py", "byte_offset": 0, "byte_length": 100},
            {"file": "b.py", "byte_offset": 0, "byte_length": 50},
        ]
        assert symbol_span_bytes(syms) == 150

    def test_untrusted_spans_contribute_zero_not_a_guess(self):
        """Conservative by design: understating our own savings is the safe way
        to be wrong about a number we publish."""
        syms = [
            {"file": "b.py", "byte_offset": 0, "byte_length": 400},
            {"file": "b.py", "byte_offset": 0, "byte_length": 900},
        ]
        assert symbol_span_bytes(syms) == 0

    def test_empty_is_zero(self):
        assert symbol_span_bytes([]) == 0


class TestDistinctFileBytes:
    def test_file_charged_once_per_file_not_per_symbol(self):
        sizes = {"a.py": 1000, "b.py": 500}
        syms = [{"file": "a.py"}] * 8 + [{"file": "b.py"}] * 3
        assert distinct_file_bytes(sizes, syms) == 1500
        # What the per-symbol lookup produced for the same input.
        assert sum(sizes[s["file"]] for s in syms) == 9500

    def test_unknown_file_contributes_zero(self):
        assert distinct_file_bytes({"a.py": 10}, [{"file": "ghost.py"}]) == 0

    def test_separators_normalised_on_the_symbol_side(self):
        assert distinct_file_bytes({"src/a.py": 10}, [{"file": "src\\a.py"}]) == 10

    def test_separators_normalised_on_the_sizes_side(self):
        assert distinct_file_bytes({"src\\a.py": 10}, [{"file": "src/a.py"}]) == 10

    def test_empty_inputs(self):
        assert distinct_file_bytes({}, [{"file": "a.py"}]) == 0
        assert distinct_file_bytes({"a.py": 10}, []) == 0


class TestSavingsBaselineRatchet:
    """One definition each. An eighth site cannot reintroduce either shape.

    Written over the property because the reported list was four sites and the
    property found seven.
    """

    def _files(self):
        for path in SRC.rglob("*.py"):
            yield path.relative_to(SRC), path.read_text(encoding="utf-8")

    @staticmethod
    def _sum_call_bodies(text: str):
        """Yield the body of every ``sum(...)`` call, matched by paren depth.

        A depth-limited regex is not enough and the non-vacuity pass proved it:
        the real defect is ``sum(int(s.get("byte_length", 0) or 0) for ...)``,
        two levels deep, and a one-level pattern walked straight past it.
        """
        for m in re.finditer(r"\bsum\(", text):
            depth, i = 1, m.end()
            while i < len(text) and depth:
                if text[i] == "(":
                    depth += 1
                elif text[i] == ")":
                    depth -= 1
                i += 1
            yield text[m.end():i - 1]

    def test_no_byte_length_summed_over_symbols(self):
        """Shape 1. Scanned over full file text so a multi-line call cannot hide,
        and scoped to the defect rather than to ``sum(`` — summing distinct FILE
        sizes is the correct shape and must keep passing."""
        offenders = [
            f"{rel}: sum({body.strip()[:70]}"
            for rel, text in self._files()
            for body in self._sum_call_bodies(text)
            if "byte_length" in body and rel.name != "_utils.py"
        ]
        assert not offenders, (
            "summing byte_length over a symbol collection counts nested spans "
            f"once per level; use tools._utils.symbol_span_bytes: {offenders}"
        )

    def test_no_per_symbol_file_size_lookup(self):
        """Shape 2. A file charged once per symbol selected from it.

        ⚠ KNOWN LIMIT, recorded so this is not read as full coverage: a text
        scan cannot see ``raw_bytes += index.file_sizes.get(f, 0)`` accumulated
        inside a loop, which is correct ONLY when the loop dedupes by file.
        search_symbols, search_text and get_symbol all take that shape and all
        guard it with a ``seen_files`` set (search_text iterates unique paths by
        construction). A new site doing it WITHOUT the guard passes this test.
        Reviewing an accumulate-in-loop baseline means reading for the dedupe.
        """
        pattern = re.compile(r"file_sizes\s*(?:\.get\(|\[)\s*(?:sym|s)\b")
        offenders = [
            f"{rel}: {m.group(0).strip()}"
            for rel, text in self._files()
            for m in pattern.finditer(text)
        ]
        assert not offenders, (
            "file_sizes looked up per symbol charges a file once per symbol; "
            f"use tools._utils.distinct_file_bytes: {offenders}"
        )

    def test_summing_distinct_file_sizes_is_still_allowed(self):
        """Non-vacuity guard on the scoping above.

        get_repo_map and get_symbol_importance sum file_sizes over source_files
        — distinct files, the correct shape. A ratchet that flagged those would
        be standing pressure to "fix" two correct sites.
        """
        pattern = re.compile(r"sum\(index\.file_sizes\.get\(f, 0\) for f in source_files\)")
        hits = [str(rel) for rel, text in self._files() if pattern.search(text)]
        assert len(hits) >= 2, f"expected the correct shape to survive, found {hits}"


class TestBasisGenerationDisclosed:
    """A lifetime total spanning a basis change is not one measurement."""

    def _fresh_state(self):
        # ⚠ NOT named `_state`: the replay fixture pins `_State` as a query, and a
        # private test helper by that name outranked the real class in
        # token_tracker.py (mrr 1.0 -> 0.5). A test that degrades the corpus it is
        # measured against is the test's problem, not the baseline's.
        from jcodemunch_mcp.storage import token_tracker as tt

        return type(tt._state)()

    def test_ledger_with_history_but_no_stamp_is_generation_one(self, tmp_path):
        (tmp_path / "_savings.json").write_text(
            json.dumps({"total_tokens_saved": 5_000_000}), encoding="utf-8"
        )
        state = self._fresh_state()
        state._ensure_loaded(str(tmp_path))
        assert state._basis_first == 1, "pre-stamp history must not claim the corrected basis"

    def test_fresh_ledger_is_not_mixed(self, tmp_path):
        from jcodemunch_mcp.storage import token_tracker as tt

        state = self._fresh_state()
        state._ensure_loaded(str(tmp_path))
        assert state._basis_first == tt.SAVINGS_BASIS_GENERATION
        basis = state.session_stats(str(tmp_path))["total_tokens_saved_basis"]
        assert basis["mixed_basis"] is False

    def test_mixed_basis_is_surfaced(self, tmp_path):
        from jcodemunch_mcp.storage import token_tracker as tt

        (tmp_path / "_savings.json").write_text(
            json.dumps({"total_tokens_saved": 5_000_000}), encoding="utf-8"
        )
        state = self._fresh_state()
        state._ensure_loaded(str(tmp_path))
        basis = state.session_stats(str(tmp_path))["total_tokens_saved_basis"]
        assert basis["mixed_basis"] is True
        assert basis["generation"] == tt.SAVINGS_BASIS_GENERATION
        assert basis["first_generation"] == 1

    def test_an_id_only_ledger_is_not_treated_as_history(self, tmp_path):
        """A file holding an anon_id but no counts has nothing taken wrongly."""
        from jcodemunch_mcp.storage import token_tracker as tt

        (tmp_path / "_savings.json").write_text(
            json.dumps({"anon_id": "abc", "total_tokens_saved": 0}), encoding="utf-8"
        )
        state = self._fresh_state()
        state._ensure_loaded(str(tmp_path))
        assert state._basis_first == tt.SAVINGS_BASIS_GENERATION
