from incidents import format_incident_history


def _inc(opened, closed=None, services=()):
    return {"id": 1, "opened_at": opened, "closed_at": closed,
            "services": [{"name": n} for n in services]}


def test_nothing_recorded_says_so_rather_than_rendering_empty() -> None:
    assert format_incident_history([]) == ["No incidents recorded yet."]


def test_a_closed_incident_shows_both_ends() -> None:
    lines = format_incident_history([_inc("2026-08-21 10:00:00", "2026-08-21 11:00:00", ["Api"])])
    assert lines[0].startswith("🟢")
    assert " to " in lines[0]
    assert "Api" in lines[0]


# An open incident has no end, and saying one would invent it.
def test_an_open_incident_reads_as_ongoing() -> None:
    lines = format_incident_history([_inc("2026-08-21 10:00:00", None, ["Api"])])
    assert lines[0].startswith("🔴")
    assert "ongoing" in lines[0]


def test_timestamps_render_in_the_readers_own_zone() -> None:
    lines = format_incident_history([_inc("2026-08-21 10:00:00", None, ["Api"])])
    assert "<t:" in lines[0] and ":f>" in lines[0]


# SQLite writes CURRENT_TIMESTAMP as UTC with no zone; reading it as local time
# would move every stamp by an hour in summer.
def test_a_naive_timestamp_is_read_as_utc() -> None:
    lines = format_incident_history([_inc("2026-08-21 10:00:00", None, ["Api"])])
    assert "<t:1787306400:f>" in lines[0]


def test_an_unparseable_timestamp_is_shown_rather_than_dropped() -> None:
    lines = format_incident_history([_inc("not a date", None, ["Api"])])
    assert "not a date" in lines[0]


def test_a_long_service_list_is_summarised() -> None:
    lines = format_incident_history([_inc("2026-08-21 10:00:00", None,
                                          ["A", "B", "C", "D", "E", "F", "G"])])
    assert "and 2 more" in lines[0]
    assert "G" not in lines[0].split("-# ")[1].split(" and ")[0]


def test_an_incident_with_no_services_still_renders() -> None:
    lines = format_incident_history([_inc("2026-08-21 10:00:00", None, [])])
    assert "no services recorded" in lines[0]
