import os
from types import SimpleNamespace
from typing import Any, cast

os.environ.setdefault("BOT_TOKEN", "x")
os.environ.setdefault("STATUS_API_URL", "http://localhost/api")

from cogs.uptime import UptimeCog
from incidents import format_incident_history
from ui.status_layout import IncidentHistoryLayout


def _cog():
    cog = UptimeCog.__new__(UptimeCog)
    cast(Any, cog).bot = SimpleNamespace(
        version="9.9.9",
        config=SimpleNamespace(STATUS_PAGE_URL="https://status.test/")
    )
    return cog


def _incidents(count, name):
    return [
        {"id": i, "opened_at": "2026-08-21 10:00:00", "closed_at": "2026-08-21 11:00:00",
         "services": [{"name": name} for _ in range(5)]}
        for i in range(count)
    ]


# Ten incidents naming real services runs past the 2000-character content limit,
# which fails the command outright rather than shortening it.
def test_a_history_that_would_overflow_a_message_is_split() -> None:
    long_name = "eXtended Ratings DataBase (XRDB Dev Build)"
    lines = format_incident_history(_incidents(10, long_name))
    assert len("\n".join(lines)) > 2000, "the fixture no longer exceeds the limit it exists to test"

    layout = IncidentHistoryLayout(_cog(), lines)
    displays = [
        getattr(child, "content", "")
        for child in layout.walk_children()
        if getattr(child, "content", None)
    ]
    assert len(displays) > 2, "everything landed in one display, so nothing was split"
    assert all(len(text) <= 2000 for text in displays)


def test_a_short_history_renders_in_one_piece() -> None:
    layout = IncidentHistoryLayout(_cog(), format_incident_history(_incidents(1, "Api")))
    body = "\n".join(getattr(c, "content", "") for c in layout.walk_children())
    assert "Recent incidents" in body
    assert "Api" in body


def test_an_empty_history_still_renders() -> None:
    layout = IncidentHistoryLayout(_cog(), format_incident_history([]))
    body = "\n".join(getattr(c, "content", "") for c in layout.walk_children())
    assert "No incidents recorded yet." in body
