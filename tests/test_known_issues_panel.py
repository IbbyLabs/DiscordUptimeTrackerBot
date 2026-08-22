"""The known-issues panel exists only when it has something to say.

A panel reading "nothing is in maintenance" is one nobody reads, so on the day
it carries a reason nobody sees that either.
"""

import os
from types import SimpleNamespace
from typing import Any, cast

os.environ.setdefault("BOT_TOKEN", "x")
os.environ.setdefault("STATUS_API_URL", "http://localhost/api")

from panels import build_panel_specs


def _cog(issues=(), bulletin=None):
    return SimpleNamespace(
        active_outages=lambda _d: [],
        known_issues=lambda _d: list(issues),
        outage_line=lambda _s: "",
        known_issue_line=lambda s: f"**{s['name']}** {s['maintenance']['reason']}",
        bulletin=lambda _d: bulletin,
        bulletin_lines=lambda b: [f"📢 **{b['title']}**", b["message"]],
    )


def _panels(cog):
    return {spec[0]: spec for spec in build_panel_specs(cast(Any, cog), {}, [])}


def test_nothing_to_say_means_no_panel() -> None:
    panels = _panels(_cog())
    assert "known_issues" not in panels
    assert "outages" in panels and "history" in panels


def test_a_service_in_maintenance_brings_the_panel_back() -> None:
    service = {"name": "XRDB", "maintenance": {"reason": "disk swap"}}
    panels = _panels(_cog(issues=[service]))
    assert "known_issues" in panels
    assert any("disk swap" in line for line in panels["known_issues"][2])


def test_a_bulletin_alone_is_enough() -> None:
    bulletin = {"title": "Provider notice", "message": "Debrid terms changed"}
    panels = _panels(_cog(bulletin=bulletin))
    assert "known_issues" in panels
    lines = panels["known_issues"][2]
    assert any("Provider notice" in line for line in lines)
    assert any("Debrid terms changed" in line for line in lines)


def test_a_bulletin_and_a_maintenance_both_render() -> None:
    service = {"name": "XRDB", "maintenance": {"reason": "disk swap"}}
    bulletin = {"title": "Provider notice", "message": "Debrid terms changed"}
    lines = _panels(_cog(issues=[service], bulletin=bulletin))["known_issues"][2]
    assert any("Provider notice" in line for line in lines)
    assert any("disk swap" in line for line in lines)
