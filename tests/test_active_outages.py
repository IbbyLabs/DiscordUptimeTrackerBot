from types import SimpleNamespace
from typing import Any, cast

from cogs.uptime import UptimeCog


def _cog():
    return UptimeCog.__new__(UptimeCog)


def _svc(name, state, group="Debrid Services", down_since=None, hidden=False):
    return {
        "id": name.lower(), "name": name, "group": group,
        "url": f"https://{name.lower()}.test/",
        "hideFromStatusPage": hidden,
        "downSince": down_since,
        "last": {"state": state, "latency": 100},
    }


def test_only_services_that_are_down_appear() -> None:
    data = {"services": [
        _svc("A", "DOWN"), _svc("B", "UP"), _svc("C", "DEGRADED"), _svc("D", "MAINTENANCE"),
    ]}
    assert [s["name"] for s in _cog().active_outages(cast(Any, data))] == ["A"]


# Degrading is answering, so it is not an outage. Same rule as the alerts.
def test_a_degraded_service_is_not_an_outage() -> None:
    data = {"services": [_svc("C", "DEGRADED")]}
    assert _cog().active_outages(cast(Any, data)) == []


def test_a_hidden_service_stays_off_the_panel() -> None:
    data = {"services": [_svc("A", "DOWN", hidden=True), _svc("B", "DOWN")]}
    assert [s["name"] for s in _cog().active_outages(cast(Any, data))] == ["B"]


# The one broken longest is the one someone is most likely asking about.
def test_the_longest_outage_is_listed_first() -> None:
    data = {"services": [
        _svc("Recent", "DOWN", down_since="2026-08-21T20:00:00Z"),
        _svc("Oldest", "DOWN", down_since="2026-08-20T09:00:00Z"),
        _svc("Middle", "DOWN", down_since="2026-08-21T10:00:00Z"),
    ]}
    assert [s["name"] for s in _cog().active_outages(cast(Any, data))] == ["Oldest", "Middle", "Recent"]


def test_a_service_with_no_down_since_sorts_last_rather_than_crashing() -> None:
    data = {"services": [
        _svc("NoStamp", "DOWN"),
        _svc("Stamped", "DOWN", down_since="2026-08-21T10:00:00Z"),
    ]}
    assert [s["name"] for s in _cog().active_outages(cast(Any, data))] == ["Stamped", "NoStamp"]


def test_the_line_names_the_service_its_group_and_when_it_broke() -> None:
    line = _cog().outage_line(cast(Any, _svc("Api", "DOWN", down_since="2026-08-21T10:00:00Z")))
    assert "**Api**" in line and "Debrid Services" in line
    # A Discord stamp rather than a fixed string, so it reads in the reader's zone.
    assert "<t:" in line and ":R>" in line


def test_a_line_without_a_timestamp_still_renders() -> None:
    line = _cog().outage_line(cast(Any, _svc("Api", "DOWN")))
    assert "**Api**" in line
    assert "<t:" not in line


def _cog_with(brand_override=None, brand_name="Fallback Name"):
    from types import SimpleNamespace as NS
    cog = UptimeCog.__new__(UptimeCog)
    cast(Any, cog).bot = NS(config=NS(BRAND_NAME=brand_name, BRAND_NAME_OVERRIDE=brand_override))
    return cog


# Documented as an override, so it has to beat the API rather than lose to it.
def test_a_set_brand_name_beats_the_status_apis_own_name() -> None:
    data = {"source": {"name": "Somebody Else's Tracker"}}
    assert _cog_with(brand_override="My Board").tracker_name(cast(Any, data)) == "My Board"


# An install that sets nothing should not show our brand on someone else's API.
def test_an_unset_brand_name_takes_the_apis_name() -> None:
    data = {"source": {"name": "Their Tracker"}}
    assert _cog_with().tracker_name(cast(Any, data)) == "Their Tracker"


def test_with_neither_the_built_in_default_is_used() -> None:
    assert _cog_with().tracker_name(cast(Any, {"source": {}})) == "Fallback Name"


def _flapping(name, state="DOWN", flapping=False, group="Stremio"):
    return {
        "id": name.lower(), "name": name, "group": group,
        "url": f"https://{name.lower()}.test/", "hideFromStatusPage": False,
        "downSince": "2026-08-21T10:00:00Z",
        "last": {"state": state, "latency": 100, "flapping": flapping},
    }


# Not in the payload summary, so it has to be counted per service.
def test_unstable_counts_only_services_the_monitor_flagged() -> None:
    data = {"services": [
        _flapping("A", state="UP", flapping=True),
        _flapping("B", flapping=False),
        _flapping("C", state="UP", flapping=True),
    ]}
    assert _cog().unstable_count(cast(Any, data)) == 2


def test_a_hidden_service_is_not_counted() -> None:
    data = {"services": [dict(_flapping("A", state="UP", flapping=True), hideFromStatusPage=True)]}
    assert _cog().unstable_count(cast(Any, data)) == 0


def test_nothing_flagged_counts_zero_rather_than_erroring() -> None:
    assert _cog().unstable_count(cast(Any, {"services": [_flapping("A")]})) == 0
    assert _cog().unstable_count(cast(Any, {"services": [{"name": "X", "last": {}}]})) == 0


def _hc(services):
    return _cog().headline_counts(cast(Any, {
        "services": services,
        "summary": {
            "up": sum(1 for s in services if s["last"]["state"] == "UP"),
            "down": sum(1 for s in services if s["last"]["state"] == "DOWN"),
            "degraded": sum(1 for s in services if s["last"]["state"] == "DEGRADED"),
        },
    }))


# Ibby's rule: the numbers should be addable. A service is one thing with
# something wrong, not two.
def test_two_services_that_are_down_both_count_as_down() -> None:
    up, down, degraded, unstable = _hc([
        _flapping("Broken", state="DOWN", flapping=False),
        _flapping("Bouncing", state="DOWN", flapping=True),
        _flapping("Fine", state="UP", flapping=False),
    ])
    assert (up, down, degraded, unstable) == (1, 2, 0, 0)


def test_a_degraded_service_under_a_hold_stays_degraded() -> None:
    up, down, degraded, unstable = _hc([
        _flapping("Slow", state="DEGRADED", flapping=True),
        _flapping("Fine", state="UP", flapping=False),
    ])
    assert (up, down, degraded, unstable) == (1, 0, 1, 0)


# Held DOWN is the usual case, but a service can be flagged while reading UP.
def test_a_flapping_service_reading_up_leaves_the_up_count() -> None:
    up, down, degraded, unstable = _hc([
        _flapping("Bouncing", state="UP", flapping=True),
        _flapping("Fine", state="UP", flapping=False),
    ])
    assert (up, down, degraded, unstable) == (1, 0, 0, 1)


def test_with_nothing_flapping_the_counts_are_the_payloads_own() -> None:
    assert _hc([
        _flapping("A", state="DOWN", flapping=False),
        _flapping("B", state="UP", flapping=False),
    ]) == (1, 1, 0, 0)


def test_the_four_counts_add_up_to_the_services_shown() -> None:
    services = [
        _flapping("A", state="DOWN", flapping=True),
        _flapping("B", state="DOWN", flapping=False),
        _flapping("C", state="DEGRADED", flapping=False),
        _flapping("D", state="UP", flapping=False),
    ]
    assert sum(_hc(services)) == len(services)


# A service answering 503 on every check is down, whatever the recovery hold
# says. Unstable describes a service that is up and not yet trusted.
def test_a_service_that_is_down_is_not_called_unstable() -> None:
    service = _flapping("Stremio App", state="DOWN", flapping=True)
    assert _cog().is_unstable(cast(Any, service)) is False


def test_a_service_that_is_up_under_a_hold_is_unstable() -> None:
    service = _flapping("Stremio App", state="UP", flapping=True)
    assert _cog().is_unstable(cast(Any, service)) is True


def test_the_headline_calls_a_down_service_down() -> None:
    services = [_flapping("Stremio App", state="DOWN", flapping=True)]
    assert _cog().get_status_text(cast(Any, services), healthy="🟢") == "🔴 1 Service Down"


def test_a_down_service_is_listed_in_red() -> None:
    service = _flapping("Stremio App", state="DOWN", flapping=True)
    assert _cog().outage_line(cast(Any, service)).startswith("🔴")


def test_the_counts_agree_with_the_outage_list() -> None:
    services = [
        _flapping("Stremio App", state="DOWN", flapping=True),
        _flapping("Torbox", state="UP", flapping=True),
        _flapping("Real-Debrid", state="UP", flapping=False),
    ]
    up, down, degraded, unstable = _hc(services)
    assert (up, down, degraded, unstable) == (1, 1, 0, 1)
    assert len(_cog().active_outages(cast(Any, {"services": services}))) == down
