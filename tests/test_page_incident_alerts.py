from incidents import plan_page_incident_alerts


def _row(rid, closed=None, name="Api"):
    return {"id": rid, "name": name, "group": "G", "state": "DOWN",
            "opened_at": "2026-08-21T10:00:00Z", "closed_at": closed}


def plan(announced=None, rows=(), anything_still_down=None):
    rows = list(rows)
    # Mirrors the caller: completeness comes from the status payload, so the
    # default here is whatever these rows imply.
    if anything_still_down is None:
        anything_still_down = any(r["closed_at"] is None for r in rows)
    return plan_page_incident_alerts(
        announced=dict(announced or {}), rows=rows,
        anything_still_down=anything_still_down,
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


# 2026-08-23: one origin reboot took fifteen services down inside fourteen
# seconds, each for about two minutes. Every one was announced and none was ever
# retracted, because the page drops a closed incident that ran under thirty
# minutes. This is the shape that has to produce fifteen of each.
def _reboot_rows(closed=None):
    return [
        _row(f"svc{n}", closed=closed, name=f"Service {n}")
        for n in range(15)
    ]


def test_fifteen_services_failing_together_are_all_announced() -> None:
    p = plan(rows=_reboot_rows())
    assert len(p["open"]) == 15


def test_and_all_fifteen_recoveries_are_announced() -> None:
    announced = {f"svc{n}": {"opened": True, "closed": False} for n in range(15)}
    p = plan(announced, _reboot_rows(closed="2026-08-21T10:02:00Z"),
             anything_still_down=False)
    assert len(p["close"]) == 15, (
        "the original bug: fifteen outages announced, none retracted"
    )
    assert p["all_clear"] is True


class _Shouty:
    """A translator that changes every string, standing in for any language."""

    def __call__(self, message: str) -> str:
        return f"<{message}>"

    def ngettext(self, singular: str, plural: str, n: int) -> str:
        return f"<{singular if n == 1 else plural}>"


# The accent colour used to be chosen by looking for "Outage started" in the
# rendered heading. Translated, that match fails and an outage is drawn in the
# recovery colour, in every language but English.
def test_the_kind_survives_translation() -> None:
    from incidents import build_page_incident_messages

    built = build_page_incident_messages(
        {"open": [_row("a")], "close": [], "silent": [], "all_clear": False},
        _Shouty(),
    )
    kinds = [kind for kind, _heading, _lines in built]
    assert kinds == ["open"]
    assert "<Outage started>" in built[0][1], "the heading went untranslated"


def test_a_plural_message_asks_the_translator_for_the_plural() -> None:
    from incidents import build_page_incident_messages

    built = build_page_incident_messages(
        {"open": [_row("a"), _row("b")], "close": [], "silent": [], "all_clear": False},
        _Shouty(),
    )
    # The count is filled after the translator chooses the form.
    assert "<2 services are not responding.>" in built[0][1]
