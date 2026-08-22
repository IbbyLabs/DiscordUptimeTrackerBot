"""A transient alert points at the panels that hold the current picture.

An alert is one moment and scrolls away; the panels are pinned and stay right.
Someone reading a week-old alert should be one tap from what is true now.
"""

import asyncio
import os
import tempfile
from types import SimpleNamespace
from typing import Any, cast

os.environ.setdefault("BOT_TOKEN", "x")
os.environ.setdefault("STATUS_API_URL", "http://localhost/api")

from cogs.uptime import UptimeCog
from tracker_db import TrackerDatabase
from ui.status_layout import PanelLayout


def _cog(db=None):
    cog = UptimeCog.__new__(UptimeCog)
    cast(Any, cog).bot = SimpleNamespace(
        db=db,
        version="1.2.3",
        config=SimpleNamespace(
            STATUS_PAGE_URL="https://default.example/",
            STATUS_EMOJI="🟣",
            BRAND_NAME="Uptime Tracker",
            BRAND_NAME_OVERRIDE=None,
        ),
    )
    return cog


def _text(view):
    return "\n".join(getattr(c, "content", "") or "" for c in view.walk_children())


async def _db():
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    handle.close()
    db = TrackerDatabase(handle.name)
    await db.init()
    return db, handle.name


def test_an_alert_links_to_the_pinned_panel() -> None:
    async def run():
        db, path = await _db()
        try:
            cog = _cog(db)
            await db.upsert_panel_message("g1", "outages", "c2", "m3")
            url = await cog.panel_jump_url("g1", "outages")
            assert url == "https://discord.com/channels/g1/c2/m3"

            text = _text(PanelLayout(cog, "## Outage started", ["x"], 0xD90429, live_url=url))
            assert "Live status" in text
            assert url in text
        finally:
            os.unlink(path)
    asyncio.run(run())


def test_no_panel_means_no_line_rather_than_a_dead_link() -> None:
    async def run():
        db, path = await _db()
        try:
            cog = _cog(db)
            assert await cog.panel_jump_url("g1", "outages") is None
            text = _text(PanelLayout(cog, "## Outage started", ["x"], 0xD90429, live_url=None))
            assert "Live status" not in text
            assert "Developed by IbbyLabs" in text, "the footer went with it"
        finally:
            os.unlink(path)
    asyncio.run(run())


def test_a_panel_itself_carries_no_link_to_itself() -> None:
    text = _text(PanelLayout(_cog(), "## Active outages", ["x"], 0xD90429))
    assert "Live status" not in text
