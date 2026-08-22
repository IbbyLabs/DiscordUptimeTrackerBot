"""A service in the recovery hold is answering, and must not be called down.

BUG-269. The page holds such a service out of "recovered" and still tells the
reader it is recovering, in amber. The bot took the first rule and used it for
the second, so a service returning 200 was listed as "not responding" for
hours. The health endpoint had already made this distinction — /v1/health
returns 200 for a recovering service, deliberately — so the board contradicted
our own API.
"""

import os
from types import SimpleNamespace
from typing import Any, cast

os.environ.setdefault("BOT_TOKEN", "x")
os.environ.setdefault("STATUS_API_URL", "http://localhost/api")

import status_api
from cogs.uptime import UptimeCog
from panels import build_panel_specs


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


def _svc(sid, display, group="Debrid Services"):
    return {
        "id": sid,
        "name": sid,
        "group": group,
        "displayState": display,
        "downSince": "2026-08-22T14:32:29Z",
        "last": {"state": "DOWN" if display in ("DOWN", "RECOVERING") else display},
    }


RECOVERING = _svc("torbox-app", "RECOVERING")
DOWN = _svc("tmdb", "DOWN", "Metadata & Catalogs")


# The two readers exist to answer two different questions. Collapsing them is
# the defect, so the distinction is asserted directly.
def test_counting_treats_recovering_as_down_and_wording_does_not() -> None:
    assert status_api.service_state(RECOVERING) == "DOWN"
    assert status_api.display_state(RECOVERING) == "RECOVERING"
    assert status_api.service_recovering(RECOVERING) is True
    assert status_api.service_recovering(DOWN) is False


def test_a_recovering_service_is_not_described_as_not_responding() -> None:
    line = _cog().outage_line(cast(Any, RECOVERING))
    assert "responding again" in line
    assert line.startswith("🟡"), line


def test_a_service_that_is_actually_down_still_reads_red() -> None:
    line = _cog().outage_line(cast(Any, DOWN))
    assert line.startswith("🔴"), line
    assert "responding again" not in line


def test_the_emoji_follows_the_page_and_renders_recovering_amber() -> None:
    cog = _cog()
    assert cog.get_state_emoji("RECOVERING", "🟢") == "🟡"
    assert cog.get_state_emoji("DOWN", "🟢") == "🔴"


def _panel(services, key="outages"):
    cog = _cog()
    stub = SimpleNamespace(
        active_outages=lambda _d: services,
        recovering_services=lambda _d: [s for s in services if status_api.service_recovering(s)],
        known_issues=lambda _d: [],
        outage_line=cog.outage_line,
        known_issue_line=lambda _s: "",
        bulletin=lambda _d: None,
        bulletin_lines=lambda _b: [],
    )
    specs = {spec[0]: spec for spec in build_panel_specs(cast(Any, stub), {}, [])}
    return specs[key]


def test_the_heading_counts_the_two_separately() -> None:
    heading = _panel([DOWN, RECOVERING])[1]
    assert "1 not responding" in heading
    assert "1 recovering" in heading
    assert "2 not responding" not in heading, "a service returning 200 was counted as not responding"


def test_only_recovering_is_amber_rather_than_red() -> None:
    key, heading, _lines, accent = _panel([RECOVERING])
    assert "not responding" not in heading, heading
    assert "1 recovering" in heading
    assert heading.startswith("## 🟡"), heading
    assert accent != 0xD90429, "an estate with nothing down was drawn as an outage"


def test_nothing_wrong_still_reads_green() -> None:
    _key, heading, lines, accent = _panel([])
    assert heading == "## 🟢 Active outages"
    assert lines == ["Everything is responding."]
    assert accent == 0x2A9D8F


# The board carries its own copy of the outage heading. Fixing the panel alone
# left the two surfaces disagreeing in the same message.
def test_the_board_heading_makes_the_same_split_as_the_panel() -> None:
    from ui.status_layout import _with_outages

    cog = _cog()
    services = [DOWN, RECOVERING]
    stub = SimpleNamespace(
        active_outages=lambda _d: services,
        recovering_services=lambda _d: [s for s in services if status_api.service_recovering(s)],
        outage_line=cog.outage_line,
    )
    head = _with_outages(cast(Any, stub), {}, ["rest"])[0]
    assert "1 service not responding" in head, head
    assert "1 recovering" in head, head
    assert "2 services not responding" not in head


def test_the_board_heading_is_unchanged_when_nothing_is_recovering() -> None:
    from ui.status_layout import _with_outages

    cog = _cog()
    stub = SimpleNamespace(
        active_outages=lambda _d: [DOWN],
        recovering_services=lambda _d: [],
        outage_line=cog.outage_line,
    )
    assert _with_outages(cast(Any, stub), {}, [])[0] == "**Active outages** — 1 service not responding"
