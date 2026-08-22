import json
from pathlib import Path

from incidents import (
    format_page_incidents,
    major_incidents,
    normalise_page_incidents,
)

FIXTURES = Path(__file__).parent / "fixtures"
LIVE = FIXTURES / "incidents.json"
NOW = 1_787_400_000_000  # fixed, so nothing here depends on the clock
MINUTE = 60_000


def _row(sid, opened_min, closed_min=None, state="DOWN", name=None):
    def stamp(m):
        import datetime
        return datetime.datetime.fromtimestamp(
            (NOW + m * MINUTE) / 1000, datetime.timezone.utc
        ).isoformat().replace("+00:00", "Z")
    return {"id": f"{sid}-{opened_min}", "service_id": sid, "name": name or sid,
            "group": "G", "state": state, "opened_at": stamp(opened_min),
            "closed_at": stamp(closed_min) if closed_min is not None else None,
            "error": "", "events": []}


def test_a_short_closed_outage_is_left_out() -> None:
    assert major_incidents([_row("a", -200, -190)], NOW) == []


def test_one_over_the_minimum_is_kept() -> None:
    assert len(major_incidents([_row("a", -200, -160)], NOW)) == 1


# Ongoing outages are listed however brief, because they have not finished yet.
def test_a_brief_ongoing_outage_is_kept() -> None:
    kept = major_incidents([_row("a", -5)], NOW)
    assert len(kept) == 1 and kept[0]["ongoing"] is True


def test_a_brief_ongoing_outage_in_a_quiet_state_is_not_kept() -> None:
    assert major_incidents([_row("a", -5, state="UP")], NOW) == []


# Milo's case: two 20-minute outages 10 minutes apart become one incident.
def test_two_short_outages_close_together_merge_into_one() -> None:
    rows = [_row("a", -200, -180), _row("a", -170, -150)]
    kept = major_incidents(rows, NOW)
    assert len(kept) == 1
    assert kept[0]["merged_count"] == 2
    # The reference sums the durations rather than spanning the gap: 20 + 20.
    assert kept[0]["duration_ms"] == 40 * MINUTE


def test_outages_further_apart_than_the_window_stay_separate() -> None:
    rows = [_row("a", -300, -260), _row("a", -200, -160)]
    assert len(major_incidents(rows, NOW)) == 2


def test_different_services_never_merge() -> None:
    rows = [_row("a", -200, -180), _row("b", -170, -150)]
    assert major_incidents(rows, NOW) == []


def test_a_merge_takes_the_worse_state() -> None:
    rows = [_row("a", -200, -180, state="DEGRADED"), _row("a", -170, -150, state="DOWN")]
    assert major_incidents(rows, NOW)[0]["state"] == "DOWN"


def test_the_newest_is_listed_first() -> None:
    rows = [_row("a", -400, -350), _row("b", -200, -150)]
    assert [k["service_id"] for k in major_incidents(rows, NOW)] == ["b", "a"]


# The page serves raw incidents, so the bot applies the rule itself.
def test_the_live_payload_loses_the_short_ones() -> None:
    rows = normalise_page_incidents(json.load(open(LIVE)))
    kept = major_incidents(rows, NOW)
    assert len(kept) < len(rows), "nothing was filtered from real data"
    assert any(k["merged_count"] > 1 for k in kept), "nothing merged in real data"


def test_the_panel_names_the_same_scope_as_the_page() -> None:
    lines = format_page_incidents(major_incidents(
        normalise_page_incidents(json.load(open(LIVE))), NOW))
    assert lines[-1].endswith("Full history on the status page.")


# The filter has to be reached by the panel, not merely available beside it.
def test_the_history_panel_applies_the_rule() -> None:
    import os
    from types import SimpleNamespace
    from typing import Any, cast

    os.environ.setdefault("BOT_TOKEN", "x")
    os.environ.setdefault("STATUS_API_URL", "http://localhost/api")
    from panels import build_panel_specs

    cog = SimpleNamespace(
        active_outages=lambda _d: [],
        known_issues=lambda _d: [],
        outage_line=lambda _s: "",
        known_issue_line=lambda _s: "",
        bulletin=lambda _d: None,
        bulletin_lines=lambda _b: [],
    )
    # Few enough rows that the display cap cannot stand in for the filter.
    rows = [_row("short", -200, -190), _row("brief", -100, -95), _row("long", -300, -240)]
    specs = build_panel_specs(cast(Any, cog), {}, rows)
    history = next(s for s in specs if s[0] == "history")
    named = [line for line in history[2] if "**" in line]
    assert len(named) == 1, f"expected only the long one, got {named}"
    assert "long" in named[0]
    assert any("Full history on the status page" in line for line in history[2])


# 107 major outages over the window and a panel that shows ten: naming only the
# window would read as the whole list.
def test_the_note_says_how_many_the_cap_leaves_out() -> None:
    rows = [
        _row(f"s{n}", opened_min=-(n + 1) * 200, closed_min=-(n + 1) * 200 + 60)
        for n in range(14)
    ]
    lines = format_page_incidents(major_incidents(rows, NOW))
    assert lines[-1] == "-# The 10 most recent major outages. Full history on the status page."


def test_the_note_claims_no_cap_when_there_is_none() -> None:
    rows = [
        _row(f"s{n}", opened_min=-(n + 1) * 200, closed_min=-(n + 1) * 200 + 60)
        for n in range(3)
    ]
    lines = format_page_incidents(major_incidents(rows, NOW))
    assert lines[-1] == "-# Major outages. Full history on the status page."
