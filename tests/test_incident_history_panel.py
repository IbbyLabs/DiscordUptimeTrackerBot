"""The history panel renders the page's list of major outages.

The 30-minute rule and the merging of neighbouring outages are the status
page's, applied by /v1/incidents?majorOnly=true. This bot no longer keeps a
copy of either, so what is left to check here is that it asks for the filtered
list and draws what comes back.
"""

import asyncio
import json
from pathlib import Path

from incidents import (
    format_page_incidents,
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

def test_the_fetch_asks_for_the_pages_filtered_list() -> None:
    """The whole rule lives behind this one parameter."""

    import status_api

    seen: dict[str, str] = {}

    async def fake_get_json(url, _key):
        seen["url"] = url
        return {"incidents": []}

    original = status_api._get_json
    status_api._get_json = fake_get_json
    try:
        asyncio.run(status_api.fetch_incidents("https://example.test/v1/incidents"))
    finally:
        status_api._get_json = original

    assert "majorOnly=true" in seen["url"], (
        "without it the panel lists every brief blip as a major outage"
    )
    assert "limit=" in seen["url"]


def test_the_panel_draws_what_it_is_given_and_filters_nothing() -> None:
    # A two-minute outage: the old local rule would have dropped it. The page
    # decides that now, so anything handed here is rendered.
    rows = [_row("brief", opened_min=-200, closed_min=-198)]
    lines = format_page_incidents(rows)
    assert any("brief" in line for line in lines)


def test_the_note_says_how_many_the_cap_leaves_out() -> None:
    rows = [
        _row(f"s{n}", opened_min=-(n + 1) * 200, closed_min=-(n + 1) * 200 + 60)
        for n in range(14)
    ]
    lines = format_page_incidents(rows)
    assert lines[-1] == "-# The 10 most recent major outages. Full history on the status page."


def test_the_note_claims_no_cap_when_there_is_none() -> None:
    rows = [
        _row(f"s{n}", opened_min=-(n + 1) * 200, closed_min=-(n + 1) * 200 + 60)
        for n in range(3)
    ]
    lines = format_page_incidents(rows)
    assert lines[-1] == "-# Major outages. Full history on the status page."


def test_the_live_fixture_still_normalises() -> None:
    rows = normalise_page_incidents(json.loads(LIVE.read_text()))
    assert rows, "the recorded response no longer parses"
    assert all(row["opened_at"] for row in rows)
