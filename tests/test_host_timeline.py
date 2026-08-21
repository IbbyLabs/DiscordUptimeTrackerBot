import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_uptime_embed import build_cog
from ui.status_layout import HostLayout, collapse_timeline


def bucket(state, missing=False):
    return {"state": state, "missing": missing}


def test_an_outage_survives_being_collapsed():
    """Worst wins when periods merge, or a short outage vanishes into a clean bar."""
    buckets = [bucket("UP")] * 9 + [bucket("DOWN")]
    assert "🟥" in collapse_timeline(buckets, 2)


def test_a_period_with_no_data_is_not_drawn_as_healthy():
    assert collapse_timeline([bucket("UP", missing=True)], 1) == "⬛"


def test_degradation_is_not_reported_as_an_outage():
    """A bucket goes DEGRADED when any single check was slow.

    Counting those as outages puts "63 with an outage" beside a service whose
    30-day uptime is 100%, which is the contradiction this separates.
    """
    service = {
        "id": "svc",
        "name": "Alpha",
        "group": "Core",
        "last": {"state": "UP", "status": 200, "latency": 20},
        "uptimeWindows": {"d7": 100.0},
        "historyTimeline": {
            "d7": {"buckets": [bucket("DEGRADED")] * 5 + [bucket("UP")] * 5}
        },
    }
    body = "\n".join(
        getattr(c, "content", "") or ""
        for c in HostLayout(build_cog(), service, window="d7").walk_children()
    )
    assert "no outages" in body
    assert "5 with slow or failed checks" in body


def test_a_real_outage_is_reported_as_one():
    service = {
        "id": "svc",
        "name": "Alpha",
        "group": "Core",
        "last": {"state": "DOWN", "status": 503, "latency": 0},
        "uptimeWindows": {"d7": 91.0},
        "historyTimeline": {"d7": {"buckets": [bucket("DOWN")] * 2 + [bucket("UP")] * 8}},
    }
    body = "\n".join(
        getattr(c, "content", "") or ""
        for c in HostLayout(build_cog(), service, window="d7").walk_children()
    )
    assert "2 with an outage" in body
    assert "no outages" not in body


def test_partial_history_is_only_flagged_when_it_matters():
    """`hasFullCoverage` is false for a two-minute shortfall on every window."""
    trivial = {
        "windowStart": "2026-08-14T00:00:00Z",
        "windowEnd": "2026-08-21T00:00:00Z",
        "coverageStart": "2026-08-14T00:02:00Z",
        "hasFullCoverage": False,
        "buckets": [bucket("UP")] * 4,
    }
    service = {
        "id": "s", "name": "A", "last": {"state": "UP"},
        "uptimeWindows": {}, "historyTimeline": {"d7": trivial},
    }
    body = "\n".join(
        getattr(c, "content", "") or ""
        for c in HostLayout(build_cog(), service, window="d7").walk_children()
    )
    assert "partial history" not in body

    real = dict(trivial, coverageStart="2026-08-18T00:00:00Z")
    service["historyTimeline"] = {"d7": real}
    body = "\n".join(
        getattr(c, "content", "") or ""
        for c in HostLayout(build_cog(), service, window="d7").walk_children()
    )
    assert "partial history" in body


def test_the_host_view_stays_inside_the_components_ceilings():
    service = {
        "id": "svc", "name": "Alpha", "group": "Core",
        "last": {"state": "UP", "status": 200, "latency": 20},
        "uptimeWindows": {"h1": 100, "h12": 100, "h24": 100, "d7": 99.9, "d30": 100},
        "historyTimeline": {"d30": {"buckets": [bucket("UP")] * 90}},
        "history": [
            {"time": "2026-08-21T00:00:00Z", "state": "UP", "status": 200, "latency": 5}
        ] * 40,
    }
    for window in ("d7", "d30", "recent"):
        view = HostLayout(build_cog(), service, window=window)
        assert view.content_length() <= 4000, window
        assert len(tuple(view.walk_children())) <= 40, window


def _board_data():
    def svc(name, state):
        return {
            "group": "Core", "name": name, "url": "https://x.example",
            "hideFromStatusPage": False, "requiresAuth": False, "uptimePercent": 99,
            "last": {"state": state, "latency": 10},
        }
    return {
        "source": {"name": "Status Tracker"},
        "summary": {"up": 1, "down": 1, "degraded": 1},
        "services": [svc("Up one", "UP"), svc("Down one", "DOWN"), svc("Slow one", "DEGRADED")],
    }


def _filtered(states):
    from ui.status_layout import StatusLayout

    return "\n".join(
        getattr(c, "content", "") or ""
        for c in StatusLayout(build_cog(), _board_data(), states=states).walk_children()
    )


def test_the_state_filter_lists_only_that_state():
    body = _filtered(("DOWN",))
    assert "Down one" in body
    assert "Up one" not in body
    assert "Slow one" not in body


def test_the_filter_takes_more_than_one_state():
    body = _filtered(("DOWN", "DEGRADED"))
    assert "Down one" in body and "Slow one" in body
    assert "Up one" not in body


def test_an_empty_result_says_so_rather_than_rendering_blank():
    """A board with no rows and no message reads as a broken command."""
    from ui.status_layout import StatusLayout

    data = _board_data()
    data["services"] = [data["services"][0]]
    body = "\n".join(
        getattr(c, "content", "") or ""
        for c in StatusLayout(build_cog(), data, states=("DOWN",)).walk_children()
    )
    assert "Nothing in that state" in body
