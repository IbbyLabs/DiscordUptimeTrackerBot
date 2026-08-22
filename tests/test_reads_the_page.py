"""The board says what the status page says, rather than working it out again.

The page publishes its verdict, each group's state and the order sections
appear in. Counting states here cannot reproduce any of the three: the rule
behind them is built on core services, critical services and group ratios that
only the page holds.
"""

import os
from types import SimpleNamespace
from typing import Any, cast

os.environ.setdefault("BOT_TOKEN", "x")
os.environ.setdefault("STATUS_API_URL", "http://localhost/api")

from cogs.uptime import UptimeCog


def _cog():
    cog = UptimeCog.__new__(UptimeCog)
    cast(Any, cog).bot = SimpleNamespace(
        version="1.2.3",
        config=SimpleNamespace(
            STATUS_PAGE_URL="https://default.example/",
            STATUS_EMOJI="🟢",
            BRAND_NAME="Uptime Tracker",
            BRAND_NAME_OVERRIDE=None,
        ),
    )
    return cog


def _svc(sid, state, group="Other"):
    return {"id": sid, "name": sid, "group": group, "displayState": state, "last": {"state": state}}


# One core service down among many healthy ones: counting says "1 service
# down", the page says the estate is down and names the cause.
DATA = {
    "overall": {"state": "DOWN", "reason": "Stremio App is down"},
    "groups": [
        {"name": "Stremio", "state": "DEGRADED", "order": 0},
        {"name": "Debrid Services", "state": "UP", "order": 1},
        {"name": "Tools", "state": "DOWN", "order": 2},
    ],
    "services": [
        _svc("stremio-app", "DOWN", "Stremio"),
        _svc("stremio-web", "UP", "Stremio"),
        _svc("rd", "UP", "Debrid Services"),
        _svc("tool-a", "DOWN", "Tools"),
    ],
}


def test_the_headline_is_the_pages_verdict_and_its_reason() -> None:
    text = _cog().get_status_text(cast(Any, DATA["services"]), "🟢", cast(Any, DATA))
    assert text == "🔴 Stremio App is down"


def test_a_degraded_verdict_reads_as_degraded() -> None:
    data = {**DATA, "overall": {"state": "DEGRADED", "reason": "Torbox is degraded"}}
    text = _cog().get_status_text(cast(Any, data["services"]), "🟢", cast(Any, data))
    assert text == "🟡 Torbox is degraded"


def test_an_up_verdict_keeps_the_operational_wording() -> None:
    data = {**DATA, "overall": {"state": "UP", "reason": "all services are responding"}}
    text = _cog().get_status_text(cast(Any, data["services"]), "🟢", cast(Any, data))
    assert text == "🟢 All Systems Operational"


def test_a_payload_without_a_verdict_falls_back_to_counting() -> None:
    data = {"services": DATA["services"]}
    text = _cog().get_status_text(cast(Any, data["services"]), "🟢", cast(Any, data))
    assert text == "🔴 2 Services Down", "the fallback stopped working"


def test_sections_follow_the_published_order() -> None:
    # The services arrive Stremio, Stremio, Debrid, Tools; the page's order is
    # what should decide, so a payload that reverses it must reverse the board.
    data = {
        **DATA,
        "groups": [
            {"name": "Tools", "state": "DOWN", "order": 0},
            {"name": "Debrid Services", "state": "UP", "order": 1},
            {"name": "Stremio", "state": "DEGRADED", "order": 2},
        ],
    }
    assert list(_cog().group_services(cast(Any, data))) == [
        "Tools",
        "Debrid Services",
        "Stremio",
    ]


def test_without_a_published_order_the_board_keeps_its_own() -> None:
    data = {"services": DATA["services"]}
    assert list(_cog().group_services(cast(Any, data))) == [
        "Stremio",
        "Debrid Services",
        "Tools",
    ]


def test_a_degraded_group_is_not_drawn_as_down() -> None:
    cog = _cog()
    members = [s for s in DATA["services"] if s["group"] == "Stremio"]
    line = cog.group_summary_line("Stremio", cast(Any, members), "🟢", "DEGRADED")
    assert line.startswith("🟡"), line
    # Without the published state, one affected service reads as a red group.
    assert cog.group_summary_line("Stremio", cast(Any, members), "🟢").startswith("🔴")


def test_a_down_group_is_still_drawn_as_down() -> None:
    members = [s for s in DATA["services"] if s["group"] == "Tools"]
    line = _cog().group_summary_line("Tools", cast(Any, members), "🟢", "DOWN")
    assert line.startswith("🔴"), line
