"""Per-tool attribution in the LOCAL savings meter.

The meter stored one lifetime scalar, so "which tools produced this total" had
no answer — the question that made a 2026-08-22 baseline correction impossible
to size. `by_tool` answers it going forward.

Two properties matter more than the accumulation itself:

  - It is LOCAL. The telemetry payload stays ``{delta, total, anon_id}``; per-tool
    data is never shared. A test pins that, because the shape of this feature is
    exactly what a wire change would look like if one were added by accident.
  - The gap is DISCLOSED. History cannot be backfilled, so sum(by_tool) is below
    total_tokens_saved by whatever predates the feature. Reported as
    ``lifetime_unattributed``, or a reader takes the shortfall for missing data.
"""

import inspect
import json
from pathlib import Path

from jcodemunch_mcp.storage import token_tracker as tt


def _fresh():
    return type(tt._state)()


def _ledger(path: Path) -> dict:
    return json.loads((path / "_savings.json").read_text(encoding="utf-8"))


class TestPerToolAccumulation:
    def test_savings_attributed_to_the_calling_tool(self, tmp_path):
        st = _fresh()
        st.add(1000, str(tmp_path), "search_symbols")
        st.add(500, str(tmp_path), "search_text")
        st.add(250, str(tmp_path), "search_symbols")
        assert st.session_stats(str(tmp_path))["lifetime_by_tool"] == {
            "search_symbols": 1250,
            "search_text": 500,
        }

    def test_persists_across_processes(self, tmp_path):
        st = _fresh()
        for _ in range(3):  # reach the flush interval
            st.add(100, str(tmp_path), "get_repo_map")
        assert _ledger(tmp_path)["by_tool"]["get_repo_map"] == 300

        reloaded = _fresh()
        reloaded._ensure_loaded(str(tmp_path))
        assert reloaded._tool_totals["get_repo_map"] == 300

    def test_accumulates_onto_existing_entries(self, tmp_path):
        (tmp_path / "_savings.json").write_text(
            json.dumps({"total_tokens_saved": 900, "by_tool": {"search_text": 900}}),
            encoding="utf-8",
        )
        st = _fresh()
        for _ in range(3):
            st.add(100, str(tmp_path), "search_text")
        assert _ledger(tmp_path)["by_tool"]["search_text"] == 1200

    def test_missing_tool_name_opens_no_key(self, tmp_path):
        st = _fresh()
        st.add(100, str(tmp_path), None)
        st.add(100, str(tmp_path), "")
        stats = st.session_stats(str(tmp_path))
        assert stats["lifetime_by_tool"] == {}
        # The savings still count toward the total; only attribution is absent.
        assert stats["total_tokens_saved"] == 200
        assert stats["lifetime_unattributed"] == 200

    def test_since_date_is_stamped_once_and_not_moved(self, tmp_path):
        (tmp_path / "_savings.json").write_text(
            json.dumps({"total_tokens_saved": 5, "by_tool": {"a": 5}, "by_tool_since": "2020-01-01"}),
            encoding="utf-8",
        )
        st = _fresh()
        for _ in range(3):
            st.add(1, str(tmp_path), "a")
        assert _ledger(tmp_path)["by_tool_since"] == "2020-01-01"


class TestUnattributedHistoryDisclosed:
    def test_pre_feature_history_is_reported_not_hidden(self, tmp_path):
        """The whole point. A ledger with history and no by_tool must say so."""
        (tmp_path / "_savings.json").write_text(
            json.dumps({"total_tokens_saved": 5_000_000}), encoding="utf-8"
        )
        st = _fresh()
        st.add(400, str(tmp_path), "get_ranked_context")
        stats = st.session_stats(str(tmp_path))
        assert stats["lifetime_by_tool"] == {"get_ranked_context": 400}
        assert stats["lifetime_unattributed"] == 5_000_000
        assert stats["total_tokens_saved"] == 5_000_400

    def test_attribution_and_unattributed_sum_to_the_total(self, tmp_path):
        (tmp_path / "_savings.json").write_text(
            json.dumps({"total_tokens_saved": 1_234}), encoding="utf-8"
        )
        st = _fresh()
        st.add(66, str(tmp_path), "search_text")
        stats = st.session_stats(str(tmp_path))
        assert (
            sum(stats["lifetime_by_tool"].values()) + stats["lifetime_unattributed"]
            == stats["total_tokens_saved"]
        )

    def test_fresh_ledger_has_nothing_unattributed(self, tmp_path):
        st = _fresh()
        st.add(120, str(tmp_path), "search_symbols")
        stats = st.session_stats(str(tmp_path))
        assert stats["lifetime_unattributed"] == 0

    def test_unattributed_never_goes_negative(self, tmp_path):
        """A hand-edited or future-written ledger must not produce a negative."""
        (tmp_path / "_savings.json").write_text(
            json.dumps({"total_tokens_saved": 10, "by_tool": {"a": 999}}), encoding="utf-8"
        )
        st = _fresh()
        assert st.session_stats(str(tmp_path))["lifetime_unattributed"] == 0


class TestAttributionStaysLocal:
    """Per-tool data is local-only. This is the property jjg approved."""

    def test_wire_payload_carries_no_per_tool_data(self):
        src = inspect.getsource(tt._telemetry_worker)
        assert 'json={"delta": delta, "total": total, "anon_id": anon_id}' in src, (
            "the telemetry payload changed; per-tool attribution must never be shared"
        )
        for banned in ("by_tool", "tool_totals", "tool_breakdown"):
            assert banned not in src, f"{banned!r} reached the telemetry payload"

    def test_share_savings_signature_takes_no_tool_data(self):
        params = list(inspect.signature(tt._share_savings).parameters)
        assert params == ["delta", "total", "anon_id"], params


class TestSinceDateIsReportedImmediately:
    """Found by calling the MCP tool rather than the internal method.

    The stamp was written at flush, so a caller reading before the third call
    saw a populated `lifetime_by_tool` beside a null `lifetime_by_tool_since`
    and could not tell what `lifetime_unattributed` covered.
    """

    def test_since_is_set_on_the_first_attributed_call(self, tmp_path):
        st = _fresh()
        st.add(10, str(tmp_path), "search_text")  # one call, no flush yet
        stats = st.session_stats(str(tmp_path))
        assert stats["lifetime_by_tool"] == {"search_text": 10}
        assert stats["lifetime_by_tool_since"], "populated map with no start date"

    def test_reported_date_is_the_one_persisted(self, tmp_path):
        st = _fresh()
        st.add(10, str(tmp_path), "search_text")
        reported = st.session_stats(str(tmp_path))["lifetime_by_tool_since"]
        for _ in range(3):
            st.add(1, str(tmp_path), "search_text")
        assert _ledger(tmp_path)["by_tool_since"] == reported

    def test_existing_since_from_disk_is_not_restamped(self, tmp_path):
        (tmp_path / "_savings.json").write_text(
            json.dumps({"total_tokens_saved": 5, "by_tool": {"a": 5}, "by_tool_since": "2020-01-01"}),
            encoding="utf-8",
        )
        st = _fresh()
        st.add(1, str(tmp_path), "a")
        assert st.session_stats(str(tmp_path))["lifetime_by_tool_since"] == "2020-01-01"
