"""Tests for get_architecture_metrics — Gini concentration, Lakos depth, DSM modularity.

Covers:
  - Gini coefficient math (even -> 0, concentrated -> high)
  - fan-in concentration surfaces the hub file as top concentrator
  - dependency depth: longest chain + max_depth over a known import chain
  - modularity: cycle detection (back-edges, cyclic_files, cluster split)
  - summary picks the most-concentrated metric
  - honest errors (unindexed, bad top_n)
  - read-only (idempotent)
"""

from pathlib import Path

from jcodemunch_mcp.tools.get_architecture_metrics import _gini, get_architecture_metrics
from jcodemunch_mcp.tools.index_folder import index_folder


# base.py is a leaf imported by mid + three consumers (fan-in 4 = the hub).
# top -> mid -> base is a depth-2 chain. cyc_a <-> cyc_b is an import cycle.
_FILES = {
    "base.py": "def base():\n    return 1\n",
    "mid.py": "from base import base\n\ndef mid():\n    return base()\n",
    "top.py": "from mid import mid\n\ndef top():\n    return mid()\n",
    "u1.py": "from base import base\n\ndef u1():\n    return base()\n",
    "u2.py": "from base import base\n\ndef u2():\n    return base()\n",
    "u3.py": "from base import base\n\ndef u3():\n    return base()\n",
    "cyc_a.py": "from cyc_b import cb\n\ndef ca():\n    return cb()\n",
    "cyc_b.py": "from cyc_a import ca\n\ndef cb():\n    return ca()\n",
}


def _make_repo(tmp_path: Path) -> tuple[str, str]:
    for rel, content in _FILES.items():
        (tmp_path / rel).write_text(content, encoding="utf-8")
    storage = str(tmp_path / ".index")
    result = index_folder(str(tmp_path), use_ai_summaries=False, storage_path=storage)
    return result.get("repo", str(tmp_path)), storage


class TestGini:
    def test_even_is_zero(self):
        assert _gini([1, 1, 1, 1]) == 0.0

    def test_concentrated_is_high(self):
        assert _gini([0, 0, 0, 10]) > 0.7

    def test_empty_and_zero(self):
        assert _gini([]) == 0.0
        assert _gini([0, 0, 0]) == 0.0


class TestConcentration:
    def test_fanin_hub_is_top_concentrator(self, tmp_path):
        repo, storage = _make_repo(tmp_path)
        out = get_architecture_metrics(repo, storage_path=storage)
        assert "error" not in out, out.get("error")
        top_in = out["concentration"]["top_concentrators"]["fan_in"]
        assert top_in, "expected fan-in concentrators"
        assert top_in[0]["file"].endswith("base.py")
        assert top_in[0]["value"] == 4  # mid + u1 + u2 + u3
        # fan-in is heavily concentrated on one file -> higher Gini than fan-out.
        g = out["concentration"]["gini"]
        assert g["fan_in"] > g["fan_out"]

    def test_summary_most_concentrated(self, tmp_path):
        repo, storage = _make_repo(tmp_path)
        out = get_architecture_metrics(repo, storage_path=storage)
        assert out["summary"]["most_concentrated_metric"] == "fan_in"


class TestDepth:
    def test_longest_chain(self, tmp_path):
        repo, storage = _make_repo(tmp_path)
        out = get_architecture_metrics(repo, storage_path=storage)
        depth = out["depth"]
        assert depth["max_depth"] == 2  # top -> mid -> base
        assert depth["longest_chain"][0].endswith("top.py")
        assert depth["longest_chain"][-1].endswith("base.py")
        assert len(depth["longest_chain"]) == 3
        assert depth["available"] is True


class TestModularity:
    def test_cycle_detected(self, tmp_path):
        repo, storage = _make_repo(tmp_path)
        out = get_architecture_metrics(repo, storage_path=storage)
        mod = out["modularity"]
        assert mod["cycle_count"] == 1
        assert mod["cyclic_files"] == 2  # cyc_a + cyc_b
        assert out["depth"]["back_edge_count"] >= 1
        # The cycle pair is a separate cluster from the base/mid/top chain.
        assert mod["clusters"] >= 2


class TestErrorsAndReadOnly:
    def test_unindexed_repo(self, tmp_path):
        _, storage = _make_repo(tmp_path)
        assert "error" in get_architecture_metrics("local/nope-xyz", storage_path=storage)

    def test_bad_top_n(self, tmp_path):
        repo, storage = _make_repo(tmp_path)
        assert "error" in get_architecture_metrics(repo, top_n=0, storage_path=storage)

    def test_idempotent(self, tmp_path):
        repo, storage = _make_repo(tmp_path)
        a = get_architecture_metrics(repo, storage_path=storage)
        b = get_architecture_metrics(repo, storage_path=storage)
        assert a["concentration"]["gini"] == b["concentration"]["gini"]
        assert a["depth"] == b["depth"]
        assert a["modularity"] == b["modularity"]


# ---------------------------------------------------------------------------
# Byte-mass double counting (competitor probe, 2026-08-22).
#
# Summing byte_length over every symbol in a file counts nesting twice: a
# class's span already covers its methods. The inflation tracks how class-heavy
# a file is, so the Gini computed ACROSS files is biased, not merely scaled
# (measured 33.4% overall / up to 2.28x per file on this repo).
#
# These assert the OUTCOME, never the mechanism: a file's reported byte mass is
# bytes of real source, so it cannot exceed the file, and two files holding the
# same amount of source cannot be ranked apart by how they organise it.
# ---------------------------------------------------------------------------

_METHOD_BODY = "        return {n}\n"

# Same source volume, opposite nesting. flat.py has no containment; nested.py
# wraps identical bodies in a class, so only the naive sum sees it as bigger.
_NESTING_FILES = {
    "flat.py": "".join(
        f"def f{n}(self):\n    return {n}\n\n\n" for n in range(12)
    ),
    "nested.py": "class Holder:\n" + "".join(
        f"    def f{n}(self):\n        return {n}\n\n" for n in range(12)
    ),
}


def _make_nesting_repo(tmp_path: Path) -> tuple[str, str]:
    for rel, content in _NESTING_FILES.items():
        (tmp_path / rel).write_text(content, encoding="utf-8")
    storage = str(tmp_path / ".index")
    result = index_folder(str(tmp_path), use_ai_summaries=False, storage_path=storage)
    return result.get("repo", str(tmp_path)), storage


class TestFileByteMass:
    """Unit contract for the shared helper."""

    def test_nested_span_counted_once(self):
        from jcodemunch_mcp.tools._utils import file_byte_mass

        mass, unmeasurable = file_byte_mass([
            {"file": "a.py", "byte_offset": 0, "byte_length": 100},   # class
            {"file": "a.py", "byte_offset": 20, "byte_length": 30},   # method inside it
            {"file": "a.py", "byte_offset": 60, "byte_length": 30},   # sibling method
        ])
        assert mass == {"a.py": 100}
        assert unmeasurable == []

    def test_disjoint_spans_add_up(self):
        from jcodemunch_mcp.tools._utils import file_byte_mass

        mass, _ = file_byte_mass([
            {"file": "a.py", "byte_offset": 0, "byte_length": 10},
            {"file": "a.py", "byte_offset": 40, "byte_length": 10},
        ])
        assert mass == {"a.py": 20}

    def test_adjacent_spans_are_not_merged_away(self):
        from jcodemunch_mcp.tools._utils import file_byte_mass

        mass, _ = file_byte_mass([
            {"file": "a.py", "byte_offset": 0, "byte_length": 10},
            {"file": "a.py", "byte_offset": 10, "byte_length": 10},
        ])
        assert mass == {"a.py": 20}

    def test_untrusted_offsets_are_unknown_not_zero(self):
        """A parser that never set byte_offset leaves every symbol at 0.

        The file must be absent from the mass map. Reporting 0 would say "this
        file holds no source", which is a confident wrong answer.
        """
        from jcodemunch_mcp.tools._utils import file_byte_mass

        mass, unmeasurable = file_byte_mass([
            {"file": "b.py", "byte_offset": 0, "byte_length": 50},
            {"file": "b.py", "byte_offset": 0, "byte_length": 90},
        ])
        assert unmeasurable == ["b.py"]
        assert "b.py" not in mass

    def test_single_symbol_at_offset_zero_is_trusted(self):
        """One symbol at byte 0 is an ordinary first symbol, not a broken parser."""
        from jcodemunch_mcp.tools._utils import file_byte_mass

        mass, unmeasurable = file_byte_mass([
            {"file": "c.py", "byte_offset": 0, "byte_length": 50},
            {"file": "c.py", "byte_offset": 80, "byte_length": 20},
        ])
        assert unmeasurable == []
        assert mass == {"c.py": 70}


class TestByteMassNotDoubleCounted:
    def test_reported_mass_never_exceeds_the_file(self, tmp_path):
        """The headline property. Bytes of source cannot exceed bytes on disk."""
        repo, storage = _make_nesting_repo(tmp_path)
        res = get_architecture_metrics(repo, top_n=10, storage_path=storage)
        reported = {
            e["file"]: e["value"]
            for e in res["concentration"]["top_concentrators"]["bytes_per_file"]
        }
        assert reported, "no byte concentrators reported; the assertion would be vacuous"
        for rel, value in reported.items():
            on_disk = (tmp_path / rel).stat().st_size
            assert value <= on_disk, f"{rel}: reported {value} bytes of a {on_disk}-byte file"

    def test_nesting_does_not_change_a_files_mass(self, tmp_path):
        """Same source volume, opposite nesting -> comparable mass."""
        repo, storage = _make_nesting_repo(tmp_path)
        res = get_architecture_metrics(repo, top_n=10, storage_path=storage)
        reported = {
            e["file"]: e["value"]
            for e in res["concentration"]["top_concentrators"]["bytes_per_file"]
        }
        flat, nested = reported["flat.py"], reported["nested.py"]
        # Both files hold the same 12 bodies; the wrapper is the only real delta.
        assert abs(flat - nested) < 0.35 * max(flat, nested), (
            f"nesting shifted reported mass: flat={flat} nested={nested}"
        )

    def test_unmeasurable_count_is_disclosed(self, tmp_path):
        repo, storage = _make_nesting_repo(tmp_path)
        conc = get_architecture_metrics(repo, top_n=5, storage_path=storage)["concentration"]
        assert "bytes_files_measured" in conc
        assert "bytes_unmeasurable_files" in conc
        # bytes_per_file is measured over its own file set, which may be smaller
        # than files_measured; a caller must be able to see the difference.
        assert conc["bytes_files_measured"] <= conc["files_measured"]


class TestByteMassRatchet:
    """One definition of per-file byte mass. A fourth spelling fails here.

    Written before concluding the reported site was the only site: the naive
    sum appeared in one tool, and the property is what is guarded, not the line.
    """

    def test_no_per_file_byte_length_accumulation(self):
        import re

        src = Path(__file__).resolve().parent.parent / "src" / "jcodemunch_mcp"
        # `something[<file key>] += ... byte_length ...` — accumulating byte
        # length into a per-file bucket is the defect, whatever it is named.
        pattern = re.compile(r"\[\s*f\w*\s*\]\s*\+=[^\n]*byte_length")
        offenders = [
            f"{path.relative_to(src)}:{i}"
            for path in src.rglob("*.py")
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if pattern.search(line)
        ]
        assert not offenders, (
            "per-file byte_length accumulation double-counts nested symbols; "
            f"call tools._utils.file_byte_mass instead: {offenders}"
        )
