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
