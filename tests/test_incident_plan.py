from incidents import plan_incident_alerts


def plan(**kw):
    base = dict(incident_open=False, seen_keys=set(), down_keys=set(), newly_down=[], newly_up=[])
    base.update(kw)
    return plan_incident_alerts(**base)


def test_the_first_service_down_opens_the_incident() -> None:
    p = plan(newly_down=[("a", "A")])
    assert p["opening"] is True
    assert p["opened_with"] == [("a", "A")]
    assert p["joined"] == []
    assert p["closing"] is False


# Several failing in one cycle is one message, which is what the batching means
# when every change a cycle sees arrives together.
def test_several_failing_together_open_one_incident() -> None:
    p = plan(newly_down=[("a", "A"), ("b", "B")])
    assert p["opening"] is True
    assert p["opened_with"] == [("a", "A"), ("b", "B")]


def test_a_new_service_joining_an_open_incident_announces() -> None:
    p = plan(incident_open=True, seen_keys={"a"}, down_keys={"a"}, newly_down=[("b", "B")])
    assert p["opening"] is False
    assert p["joined"] == [("b", "B")]
    assert p["closing"] is False


# Already named by this incident, so the panel carries it and the channel does not.
def test_a_service_the_incident_already_named_rejoins_quietly() -> None:
    p = plan(incident_open=True, seen_keys={"a"}, down_keys=set(), newly_down=[("a", "A")])
    assert p["joined"] == []
    assert p["rejoined"] == [("a", "A")]
    assert p["closing"] is False
    # It counts as down again, so the all-clear waits for it.
    assert p["still_down"] == {"a"}


def test_a_service_recovering_announces_so_people_can_switch_back() -> None:
    p = plan(incident_open=True, seen_keys={"a", "b"}, down_keys={"a", "b"}, newly_up=[("a", "A")])
    assert p["recovered"] == [("a", "A")]
    assert p["closing"] is False


def test_the_last_recovery_closes_the_incident() -> None:
    p = plan(incident_open=True, seen_keys={"a"}, down_keys={"a"}, newly_up=[("a", "A")])
    assert p["recovered"] == [("a", "A")]
    assert p["closing"] is True
    assert p["still_down"] == set()


def test_a_service_recovering_that_was_never_down_announces_nothing() -> None:
    p = plan(incident_open=True, seen_keys={"a"}, down_keys={"a"}, newly_up=[("z", "Z")])
    assert p["recovered"] == []
    assert p["closing"] is False


def test_one_cycle_can_open_and_close_when_nothing_is_left_down() -> None:
    p = plan(newly_down=[("a", "A")], newly_up=[("a", "A")])
    assert p["opening"] is True
    assert p["closing"] is True


def test_nothing_happening_announces_nothing() -> None:
    p = plan(incident_open=True, seen_keys={"a"}, down_keys={"a"})
    assert p["opening"] is False and p["closing"] is False
    assert p["joined"] == [] and p["recovered"] == []


# The key carries group and name, so hiding a row, renaming it or moving it to
# another group all remove it from the payload mid-incident.
def test_a_service_that_leaves_the_payload_stops_holding_the_incident_open() -> None:
    p = plan(incident_open=True, seen_keys={"a", "b"}, down_keys={"a", "b"},
             newly_up=[("b", "B")], present_keys={"b"})
    assert p["vanished"] == {"a"}
    assert p["still_down"] == set()
    assert p["closing"] is True


def test_a_vanished_service_alone_closes_the_incident() -> None:
    p = plan(incident_open=True, seen_keys={"a"}, down_keys={"a"}, present_keys={"b"})
    assert p["closing"] is True
    assert p["recovered"] == []


# An empty payload is a failed fetch, not every service leaving at once.
def test_an_empty_payload_prunes_nothing() -> None:
    p = plan(incident_open=True, seen_keys={"a"}, down_keys={"a"}, present_keys=set())
    assert p["vanished"] == set()
    assert p["still_down"] == {"a"}
    assert p["closing"] is False


def test_a_present_service_is_untouched_by_the_prune() -> None:
    p = plan(incident_open=True, seen_keys={"a"}, down_keys={"a"}, present_keys={"a"})
    assert p["vanished"] == set()
    assert p["closing"] is False
