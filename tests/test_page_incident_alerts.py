from datetime import datetime, timedelta, timezone

from incidents import plan_page_incident_alerts

OPENED = "2026-08-21T10:00:00Z"
# An hour after OPENED, so every existing case is comfortably past the
# thirty-minute gate and still tests what it did before.
NOW = datetime(2026, 8, 21, 11, 0, tzinfo=timezone.utc)


def _row(rid, closed=None, name="Api", opened=OPENED):
    return {"id": rid, "name": name, "group": "G", "state": "DOWN",
            "opened_at": opened, "closed_at": closed}


def plan(announced=None, rows=(), anything_still_down=None, now=NOW):
    rows = list(rows)
    # Mirrors the caller: completeness comes from the status payload, so the
    # default here is whatever these rows imply.
    if anything_still_down is None:
        anything_still_down = any(r["closed_at"] is None for r in rows)
    return plan_page_incident_alerts(
        announced=dict(announced or {}), rows=rows,
        anything_still_down=anything_still_down, now=now,
    )


def test_an_incident_we_have_never_seen_and_is_open_is_announced() -> None:
    p = plan(rows=[_row("a")])
    assert [r["id"] for r in p["open"]] == ["a"]
    assert p["close"] == []


# Opened and closed between two cycles: announcing both ends at once says
# nothing anyone can act on.
def test_one_that_opened_and_closed_unseen_is_recorded_silently() -> None:
    p = plan(rows=[_row("a", closed="2026-08-21T11:00:00Z")])
    assert p["open"] == [] and p["close"] == []
    assert p["silent"] == ["a"]


def test_an_announced_incident_closing_is_announced_once() -> None:
    p = plan({"a": {"opened": True, "closed": False}},
             [_row("a", closed="2026-08-21T11:00:00Z")])
    assert [r["id"] for r in p["close"]] == ["a"]
    assert p["all_clear"] is True


def test_a_closure_already_announced_is_not_repeated() -> None:
    p = plan({"a": {"opened": True, "closed": True}},
             [_row("a", closed="2026-08-21T11:00:00Z")])
    assert p["close"] == []


def test_an_opening_already_announced_is_not_repeated() -> None:
    p = plan({"a": {"opened": True, "closed": False}}, [_row("a")])
    assert p["open"] == []


# Seen on a silent first cycle, then it closes: that closure is news.
def test_one_seen_silently_still_announces_when_it_closes() -> None:
    p = plan({"a": {"opened": False, "closed": False}},
             [_row("a", closed="2026-08-21T11:00:00Z")])
    assert [r["id"] for r in p["close"]] == ["a"]


def test_the_all_clear_waits_for_every_open_incident() -> None:
    p = plan({"a": {"opened": True, "closed": False}, "b": {"opened": True, "closed": False}},
             [_row("a", closed="2026-08-21T11:00:00Z"), _row("b", name="Other")])
    assert [r["id"] for r in p["close"]] == ["a"]
    assert p["all_clear"] is False, "called all clear while b was still open"


def test_several_opening_in_one_cycle_are_one_batch() -> None:
    p = plan(rows=[_row("a"), _row("b"), _row("c")])
    assert len(p["open"]) == 3


def test_nothing_happening_announces_nothing() -> None:
    p = plan({"a": {"opened": True, "closed": False}}, [_row("a")])
    assert p["open"] == [] and p["close"] == [] and p["all_clear"] is False


# The incident list is paged; an outage older than the window is absent from it
# while the service is still down. The status payload is the complete answer.
def test_the_all_clear_does_not_fire_when_the_payload_still_shows_a_service_down() -> None:
    p = plan({"a": {"opened": True, "closed": False}},
             [_row("a", closed="2026-08-21T11:00:00Z")],
             anything_still_down=True)
    assert [r["id"] for r in p["close"]] == ["a"]
    assert p["all_clear"] is False, "called all clear off a truncated incident list"


def test_the_all_clear_fires_when_the_payload_shows_nothing_down() -> None:
    p = plan({"a": {"opened": True, "closed": False}},
             [_row("a", closed="2026-08-21T11:00:00Z")],
             anything_still_down=False)
    assert p["all_clear"] is True


# The page drops a closed incident that ran under its own thirty-minute
# threshold, so anything announced sooner could never be retracted. A short
# outage is therefore not announced at all.
def test_an_outage_shorter_than_the_threshold_is_not_announced() -> None:
    p = plan(rows=[_row("a")], now=NOW - timedelta(minutes=31))
    assert p["open"] == []


# And it must not be recorded either, or the cycle that finds it old enough
# would see it as already spoken about and stay silent for good.
def test_a_young_outage_is_left_unrecorded_so_it_can_still_be_announced() -> None:
    p = plan(rows=[_row("a")], now=NOW - timedelta(minutes=31))
    assert p["silent"] == []


def test_the_same_outage_is_announced_once_it_passes_the_threshold() -> None:
    young = plan(rows=[_row("a")], now=NOW - timedelta(minutes=31))
    assert young["open"] == []
    grown = plan(rows=[_row("a")], now=NOW - timedelta(minutes=29))
    assert [r["id"] for r in grown["open"]] == ["a"]


def test_exactly_the_threshold_counts_as_long_enough() -> None:
    p = plan(rows=[_row("a")], now=NOW - timedelta(minutes=30))
    assert [r["id"] for r in p["open"]] == ["a"]


# A page format change should be visible rather than turning into silence about
# a live outage.
def test_an_unreadable_opened_at_is_announced_rather_than_swallowed() -> None:
    p = plan(rows=[_row("a", opened="not-a-timestamp")])
    assert [r["id"] for r in p["open"]] == ["a"]
