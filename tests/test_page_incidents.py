import json

from incidents import format_page_incidents, normalise_page_incidents

LIVE = "/home/ubuntu/.claude/jobs/e7d81c08/tmp/inc.json"


def _row(name="Api", opened="2026-08-21T10:00:00.000Z", closed=None, group="Debrid"):
    return {
        "id": f"{name.lower()}-{opened}",
        "service": {"id": name.lower(), "name": name, "group": group},
        "state": "DOWN", "openedAt": opened, "closedAt": closed,
    }


def test_it_reads_the_pages_own_shape() -> None:
    rows = normalise_page_incidents({"incidents": [_row()]})
    assert rows[0]["name"] == "Api"
    assert rows[0]["opened_at"] == "2026-08-21T10:00:00.000Z"
    assert rows[0]["closed_at"] is None


def test_a_bare_list_is_accepted_as_well_as_the_envelope() -> None:
    assert len(normalise_page_incidents([_row()])) == 1


# A malformed payload should render an empty panel, not raise inside a command.
def test_junk_produces_no_rows_rather_than_an_error() -> None:
    assert normalise_page_incidents(None) == []
    assert normalise_page_incidents({"incidents": "nope"}) == []
    assert normalise_page_incidents({"incidents": [{}, {"openedAt": ""}]}) == []


def test_ongoing_incidents_come_first_then_newest() -> None:
    rows = normalise_page_incidents({"incidents": [
        _row("Old", "2026-08-20T10:00:00Z", "2026-08-20T11:00:00Z"),
        _row("Ongoing", "2026-08-19T10:00:00Z", None),
        _row("Recent", "2026-08-21T10:00:00Z", "2026-08-21T11:00:00Z"),
    ]})
    names = [line.split("**")[1] for line in format_page_incidents(rows)]
    assert names == ["Ongoing", "Recent", "Old"]


def test_an_ongoing_incident_is_not_given_an_end() -> None:
    line = format_page_incidents(normalise_page_incidents({"incidents": [_row()]}))[0]
    assert "ongoing" in line and " to " not in line


def test_a_closed_incident_shows_both_ends() -> None:
    line = format_page_incidents(normalise_page_incidents(
        {"incidents": [_row(closed="2026-08-21T11:00:00Z")]}))[0]
    assert " to " in line


def test_nothing_recorded_says_so() -> None:
    assert format_page_incidents([]) == ["No incidents recorded yet."]


def test_the_list_is_capped() -> None:
    rows = normalise_page_incidents({"incidents": [
        _row(f"S{i}", f"2026-08-{10+i:02d}T10:00:00Z", "2026-08-21T11:00:00Z") for i in range(15)
    ]})
    assert len(format_page_incidents(rows, limit=10)) == 10


# The live payload, so the reader is checked against the shape it will meet
# rather than only against one I wrote.
def test_it_reads_the_live_endpoints_payload() -> None:
    rows = normalise_page_incidents(json.load(open(LIVE)))
    assert len(rows) == 50
    assert all(r["opened_at"] for r in rows)
    assert any(r["closed_at"] is None for r in rows), "expected at least one ongoing incident"
    assert "<t:" in format_page_incidents(rows)[0]
