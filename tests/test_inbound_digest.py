"""Every number in the digest is computed by code from the ledger; the
model's paragraph is admitted only when every digit-run in it is in the
JSON it was given (DESIGN section 6).

Red arms: a paragraph carrying a number the JSON lacks admitted; a run
with no cost figure counted as 0 USD; an unapproved draft missing from the
awaiting list; a kill-switch flip between consecutive records missed; a
malformed ledger line aborting the digest.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INBOUND = ROOT / ".github" / "inbound"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, INBOUND / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


dg = _load("digest")


def _rec(**kw):
    base = {"job": "inbound-triage", "outcome": "acted", "item": "1", "recorded_at": "2026-09-02T10:00:00+00:00",
            "kill_switch_state": "true", "classification": {"category": "question"}, "run_id": "100", "cost_usd": None}
    base.update(kw)
    return base


def _ledger(tmp: Path, rows: list[dict], extra_line: str = "") -> Path:
    root = tmp / "led"
    (root / "ledger").mkdir(parents=True)
    text = "\n".join(json.dumps(r) for r in rows) + ("\n" + extra_line if extra_line else "") + "\n"
    (root / "ledger" / "2026-09.jsonl").write_text(text, encoding="utf-8")
    return root


def test_week_bounds_and_iso_week():
    import datetime as dt
    s, e = dg.week_bounds(dt.date(2026, 9, 3))  # a Thursday
    assert (s.isoformat(), e.isoformat()) == ("2026-08-31", "2026-09-07")
    assert dg.iso_week(dt.date(2026, 9, 3)) == "2026-W36"


def test_summarise_counts_lists_and_never_invents_a_cost(tmp_path):
    rows = [
        _rec(),
        _rec(outcome="escalated", item="2", decision="security", classification={"category": "security"}, run_id="101"),
        _rec(outcome="failed", item="3", run_id="102"),
        _rec(outcome="skipped", job="inbound-fix", item="4", decision="budget", run_id="103"),
        _rec(job="inbound-fix", outcome="drafted", item="5", cost_usd=12.5, recorded_at="2026-09-03T10:00:00+00:00", run_id="104"),
    ]
    s = dg.summarise(rows, {}, [], "o/r")
    assert s["records"] == 5
    assert s["by_job_outcome"]["inbound-triage"] == {"acted": 1, "escalated": 1, "failed": 1}
    assert [e["item"] for e in s["escalated"]] == ["2"] and s["escalated"][0]["run"].endswith("/runs/101")
    assert [f["item"] for f in s["failed"]] == ["3"] and [d["item"] for d in s["declined"]] == ["4"]
    assert s["cost_by_day_usd"] == {"2026-09-03": 12.5}
    assert s["runs_with_no_cost_recorded"] == 3, "the acted/escalated/failed rows with cost None are counted (the drafted row has a cost; the skipped row ran no model), never priced at 0"


def test_kill_switch_flips_are_seen_between_consecutive_records():
    rows = [_rec(run_id="1"), _rec(run_id="2", kill_switch_state="false", outcome="skipped", recorded_at="2026-09-02T11:00:00+00:00"),
            _rec(run_id="3", recorded_at="2026-09-02T12:00:00+00:00")]
    s = dg.summarise(rows, {}, [], "o/r")
    assert [(f["from"], f["to"]) for f in s["kill_switch_flips"]] == [("true", "false"), ("false", "true")]


def test_read_ledger_keeps_going_past_a_malformed_line(tmp_path):
    root = _ledger(tmp_path, [_rec()], extra_line="{not json")
    rows = dg.read_ledger(root / "ledger")
    assert len(rows) == 2 and "_malformed" in rows[1]
    s = dg.summarise(rows, {}, [], "o/r")
    assert s["records"] == 1 and s["malformed_ledger_lines"] == 1


def test_pending_drafts_lists_only_unapproved(tmp_path):
    root = tmp_path / "led"
    (root / "drafts" / "posted").mkdir(parents=True)
    (root / "drafts" / "1-r1.md").write_text("---\nissue: 1\napproved: false\n---\nA\n", encoding="utf-8")
    (root / "drafts" / "2-r1.md").write_text("---\nissue: 2\napproved: true\n---\nB\n", encoding="utf-8")
    (root / "drafts" / "posted" / "3-r1.md").write_text("---\nissue: 3\napproved: true\n---\nC\n", encoding="utf-8")
    assert dg.pending_drafts(root) == ["1-r1.md"]


def test_prose_is_admitted_only_when_its_numbers_are_in_the_json():
    """Review round 1, finding 1: the first gate tested each digit-run as
    a SUBSTRING of the dumped JSON, so `45` passed via a run id and `3` via
    a date, and number words were never examined. The JSON here carries
    the fields that leaked (`window`, `title`, a run URL, `recorded_at`)."""
    numbers = {
        "records": 5, "cost_by_day_usd": {"2026-09-03": 12.5}, "week": "2026-W36", "title": "inbound digest 2026-W36",
        "window": ["2026-08-31", "2026-09-07"],
        "escalated": [{"job": "inbound-triage", "item": "2", "run": "https://github.com/o/r/actions/runs/17890123456"}],
        "kill_switch_flips": [{"at": "2026-09-02T11:00:00+00:00", "from": "true", "to": "false"}],
        "stale_needs_human": None, "runs_with_no_cost_recorded": 0,
    }
    assert dg.prose_admissible("5 records, 12.5 USD on 2026-09-03, week 2026-W36, item 2 escalated.", numbers)[0] is True
    for bad, tok in [("There were 7 records.", "7"), ("45 items.", "45"), ("3 escalated.", "3"), ("31 records.", "31"),
                     ("On 2026-09-02 one flip.", "2026-09-02"), ("890 runs.", "890")]:
        ok, why = dg.prose_admissible(bad, numbers)
        assert ok is False and tok in why, (bad, why)
    for words in ("Five items were handled.", "A dozen escalations.", "None failed.", "Twelve items, four escalated."):
        ok, why = dg.prose_admissible(words, numbers)
        assert ok is False and "words" in why, (words, why)
    assert dg.prose_admissible("5 " * 700, numbers)[0] is False


def test_scalar_tokens_come_from_values_and_keys_never_from_substrings():
    toks = dg._scalar_tokens({"a": 5, "b": 12.5, "c": 3.0, "d": "100", "e": {"2026-09-03": 1}, "f": "https://x/17890123456", "g": "2026-09-02T11:00:00+00:00", "h": True, "i": None})
    assert {"5", "12.5", "3.0", "3", "100", "2026-09-03", "1"} <= toks
    assert "17890123456" not in toks and "2026-09-02" not in toks and "True" not in toks


def test_render_has_every_section_and_says_not_recorded_rather_than_zero():
    s = dg.summarise([_rec()], {"question": {"count": 2, "first": "2026-09-01", "last": "2026-09-02"}}, ["9-r1.md"], "o/r")
    md = dg.render("2026-W36", s, "o/r", "https://github.com/o/r/blob/inbound-ledger", prose="One paragraph.")
    for h in ("## Handled, by job and outcome", "## Escalated", "## Job failures", "## Declined runs", "## Drafts awaiting approval",
              "## Budget consumed per day", "## Kill-switch flips", "## Graduation streaks"):
        assert h in md, h
    assert md.startswith("# inbound digest 2026-W36\n\nOne paragraph.")
    assert "not recorded" in md and "0.00" not in md
    assert "| question | 2 |" in md and "9-r1.md" in md


def test_stale_needs_human_is_not_recorded_without_a_sweep_summary_and_listed_with_one():
    """DESIGN 6 step 4: the list lives in the sweep's audit artifact. No
    summary readable is "not recorded", never an empty list; a summary
    with an empty list says none; numbers are listed as issues."""
    s = dg.summarise([_rec()], {}, [], "o/r")
    assert s["stale_needs_human"] is None
    assert "not recorded (no sweep summary readable)" in dg.render("w", s, "o/r", "u")
    s = dg.summarise([_rec()], {}, [], "o/r", {"stale_needs_human": [], "ran_at": "2026-09-07T06:30:00+00:00"})
    assert s["stale_needs_human"] == [] and "none as of the sweep at 2026-09-07T06:30:00+00:00" in dg.render("w", s, "o/r", "u")
    s = dg.summarise([_rec()], {}, [], "o/r", {"stale_needs_human": [41, 57], "ran_at": "x"})
    md = dg.render("w", s, "o/r", "u")
    assert "- #41" in md and "- #57" in md


def test_main_end_to_end_json_and_markdown(tmp_path, capsys):
    root = _ledger(tmp_path, [_rec(), _rec(item="2", outcome="escalated", run_id="7")])
    (root / "streaks.json").write_text("{}", encoding="utf-8")
    out = tmp_path / "body.md"
    rc = dg.main(["--ledger-root", str(root), "--repo", "o/r", "--week-of", "2026-09-03", "--json", "--markdown", str(out)])
    assert rc == 0
    j = json.loads(capsys.readouterr().out)
    assert j["title"] == "inbound digest 2026-W36" and j["records"] == 2
    assert out.read_text(encoding="utf-8").startswith("# inbound digest 2026-W36")
    # render-only from the JSON, with a paragraph that invents a number
    nums = tmp_path / "numbers.json"
    nums.write_text(json.dumps(j), encoding="utf-8")
    prose = tmp_path / "prose.md"
    prose.write_text("There were 99 records.", encoding="utf-8")
    out2 = tmp_path / "body2.md"
    rc = dg.main(["--ledger-root", str(tmp_path), "--repo", "o/r", "--render-only", "--numbers", str(nums), "--prose", str(prose), "--markdown", str(out2)])
    assert rc == 0 and "99" not in out2.read_text(encoding="utf-8")
    assert "99" in json.loads(capsys.readouterr().out)["prose"]
