from incidents import is_alertable_transition, is_alert_suppressed


def test_crossing_into_down_alerts_from_any_answering_state() -> None:
    assert is_alertable_transition("UP", "DOWN") is True
    # A service that answered slowly and then stopped answering is an outage
    # beginning, and it reaches DOWN without ever passing through UP.
    assert is_alertable_transition("DEGRADED", "DOWN") is True



def test_leaving_down_alerts() -> None:
    assert is_alertable_transition("DOWN", "UP") is True
    assert is_alertable_transition("DOWN", "DEGRADED") is True


def test_changes_that_never_cross_the_boundary_stay_quiet() -> None:
    assert is_alertable_transition("UP", "DEGRADED") is False
    assert is_alertable_transition("DEGRADED", "UP") is False
    assert is_alertable_transition("DOWN", "DOWN") is False
    assert is_alertable_transition("UP", "UP") is False


def test_maintenance_is_planned_and_announces_nothing() -> None:
    assert is_alertable_transition("MAINTENANCE", "DOWN") is False
    assert is_alertable_transition("DOWN", "MAINTENANCE") is False
    assert is_alertable_transition("UP", "MAINTENANCE") is False


def test_unknown_is_unmeasured_on_either_side() -> None:
    assert is_alertable_transition("UNKNOWN", "DOWN") is False
    assert is_alertable_transition("DOWN", "UNKNOWN") is False
    assert is_alertable_transition("", "DOWN") is False
    assert is_alertable_transition("UP", None) is False


def test_case_and_padding_do_not_change_the_verdict() -> None:
    assert is_alertable_transition(" up ", "down") is True


def test_suppression_matches_on_name_or_id() -> None:
    assert is_alert_suppressed({"name": "WebStreamr", "id": "something-else"}) is True
    assert is_alert_suppressed({"name": "Other", "id": "webstreamr-mbg"}) is True
    assert is_alert_suppressed({"name": "  webstreamer   mbg ", "id": ""}) is True
    assert is_alert_suppressed({"name": "Torbox", "id": "torbox"}) is False


def _cog():
    from cogs.uptime import UptimeCog
    return UptimeCog.__new__(UptimeCog)


def _svc(sid, name, state):
    return {
        "id": sid, "name": name, "group": "Debrid Services",
        "url": f"https://{sid}.test/", "last": {"state": state, "latency": 100},
        "uptimePercent": 99.0,
    }


def _run(previous_by_key, services):
    cog = _cog()
    data = {"services": services}
    previous = {}
    for service, state in zip(services, previous_by_key):
        previous[cog.service_key(service)] = state
    return [str(change["name"]) for change in cog.collect_status_changes(previous, data)]


# The filters have to be reached by the collector, not merely defined beside it.
def test_only_boundary_crossings_reach_the_alert_list() -> None:
    services = [
        _svc("a", "Went Down", "DOWN"),
        _svc("b", "Came Back", "UP"),
        _svc("c", "Slowed Only", "DEGRADED"),
    ]
    assert _run(["UP", "DOWN", "UP"], services) == ["Went Down", "Came Back"]


def test_a_suppressed_service_is_dropped_even_when_it_crosses() -> None:
    services = [_svc("webstreamr", "WebStreamr", "DOWN"), _svc("d", "Other", "DOWN")]
    assert _run(["UP", "UP"], services) == ["Other"]
