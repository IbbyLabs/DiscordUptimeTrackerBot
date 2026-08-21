from incidents import alertable_rows, is_alert_suppressed, is_alertable_transition


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


def _row(name, sid):
    return {"id": f"{sid}-x", "service_id": sid, "name": name, "group": "G",
            "state": "DOWN", "opened_at": "2026-08-21T10:00:00Z", "closed_at": None}


# The suppression list has to reach the page-driven alerts, not just exist.
def test_a_suppressed_service_is_dropped_from_the_alertable_incidents() -> None:
    rows = [_row("WebStreamr MBG", "webstreamr-mbg"), _row("Torbox", "torbox")]
    assert [r["name"] for r in alertable_rows(rows)] == ["Torbox"]


def test_suppression_matches_on_the_service_id_too() -> None:
    assert alertable_rows([_row("Something Else", "webstreamr")]) == []


def test_nothing_suppressed_leaves_the_list_alone() -> None:
    rows = [_row("Torbox", "torbox"), _row("Comet", "comet")]
    assert len(alertable_rows(rows)) == 2
