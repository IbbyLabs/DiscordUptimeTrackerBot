import asyncio
import os
import tempfile
from types import SimpleNamespace
from typing import Any, cast

import discord

from cogs.uptime import UptimeCog
from tracker_db import TrackerDatabase


class FakeMessage:
    def __init__(self, mid): self.id = mid; self.edited = 0
    async def edit(self, **_): self.edited += 1


class FakeChannel(discord.TextChannel):
    def __init__(self, cid=1, existing=None, raise_on_fetch=None):
        self.id = cid
        self._existing = existing
        self._raise = raise_on_fetch
        self.sent = 0
        self.next_id = 500

    async def fetch_message(self, mid):
        if self._raise:
            raise self._raise
        if self._existing and self._existing.id == mid:
            return self._existing
        raise discord.NotFound(cast(Any, SimpleNamespace(status=404, reason="")), "gone")

    async def send(self, **_):
        self.sent += 1
        self.next_id += 1
        return FakeMessage(self.next_id)


async def _db():
    t = tempfile.NamedTemporaryFile(suffix=".db", delete=False); t.close()
    db = TrackerDatabase(t.name); await db.init()
    return db, t.name


def _cog(db):
    cog = UptimeCog.__new__(UptimeCog)
    cast(Any, cog).bot = SimpleNamespace(db=db)
    return cog


def test_the_first_sync_posts_and_records_the_message() -> None:
    async def run():
        db, path = await _db()
        try:
            ch = FakeChannel()
            await _cog(db).sync_panel("g", "outages", cast(Any, ch), cast(Any, object()))
            assert ch.sent == 1
            stored = await db.get_panel_message("g", "outages")
            assert stored["channel_id"] == "1"
        finally:
            os.unlink(path)
    asyncio.run(run())


# The whole point: one message kept current, not a new one every cycle.
def test_a_later_sync_edits_rather_than_posting_again() -> None:
    async def run():
        db, path = await _db()
        try:
            existing = FakeMessage(501)
            ch = FakeChannel(existing=existing)
            cog = _cog(db)
            await cog.sync_panel("g", "outages", cast(Any, ch), cast(Any, object()))
            await cog.sync_panel("g", "outages", cast(Any, ch), cast(Any, object()))
            await cog.sync_panel("g", "outages", cast(Any, ch), cast(Any, object()))
            assert ch.sent == 1, "posted more than once"
            assert existing.edited == 2
        finally:
            os.unlink(path)
    asyncio.run(run())


def test_a_deleted_panel_is_posted_again() -> None:
    async def run():
        db, path = await _db()
        try:
            ch = FakeChannel()
            cog = _cog(db)
            await cog.sync_panel("g", "outages", cast(Any, ch), cast(Any, object()))
            first = (await db.get_panel_message("g", "outages"))["message_id"]
            await cog.sync_panel("g", "outages", cast(Any, ch), cast(Any, object()))
            assert ch.sent == 2
            assert (await db.get_panel_message("g", "outages"))["message_id"] != first
        finally:
            os.unlink(path)
    asyncio.run(run())


def test_two_panels_in_one_guild_do_not_share_a_message() -> None:
    async def run():
        db, path = await _db()
        try:
            ch = FakeChannel()
            cog = _cog(db)
            await cog.sync_panel("g", "outages", cast(Any, ch), cast(Any, object()))
            await cog.sync_panel("g", "history", cast(Any, ch), cast(Any, object()))
            a = await db.get_panel_message("g", "outages")
            b = await db.get_panel_message("g", "history")
            assert a["message_id"] != b["message_id"]
        finally:
            os.unlink(path)
    asyncio.run(run())


# A moved alert channel should leave the old panel and start one where it now is.
def test_moving_the_channel_posts_a_new_panel() -> None:
    async def run():
        db, path = await _db()
        try:
            cog = _cog(db)
            first = FakeChannel(cid=1)
            await cog.sync_panel("g", "outages", cast(Any, first), cast(Any, object()))
            second = FakeChannel(cid=2)
            await cog.sync_panel("g", "outages", cast(Any, second), cast(Any, object()))
            assert second.sent == 1
            assert (await db.get_panel_message("g", "outages"))["channel_id"] == "2"
        finally:
            os.unlink(path)
    asyncio.run(run())


# Silent intake: the page is the truth on the first cycle, and the channel
# carries only what happens after it.
def test_the_first_cycle_records_without_announcing() -> None:
    from tests.test_uptime_embed import build_alert_cog

    async def run():
        cog, db, channel = build_alert_cog(
            states={},
            alert_channels=[{"guild_id": "1", "channel_id": "123"}],
        )
        data = {
            "source": {"name": "T"}, "summary": {"up": 0, "down": 1, "degraded": 0},
            "services": [{
                "group": "Core", "name": "API", "url": "https://x.test/",
                "hideFromStatusPage": False, "uptimePercent": 90.0,
                "last": {"state": "DOWN", "latency": 10},
            }],
        }
        sent = await cog.process_status_alerts(cast(Any, data))
        assert sent == 0
        assert channel.sent_views == []
        # Recorded, so the next cycle can tell what changed.
        assert db.states != {}
    asyncio.run(run())
