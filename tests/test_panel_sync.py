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
class DeletableMessage(FakeMessage):
    def __init__(self, mid): super().__init__(mid); self.deleted = False
    async def delete(self): self.deleted = True


def test_stopping_alerts_removes_the_panels_and_their_records() -> None:
    async def run():
        db, path = await _db()
        try:
            cog = _cog(db)
            msg = DeletableMessage(501)
            ch = FakeChannel(existing=msg)
            cast(Any, cog).bot.get_channel = lambda _id: ch
            cast(Any, cog).resolve_tracker_channel = lambda _id: _ready(ch)

            for panel in ("outages", "known_issues", "history"):
                await db.upsert_panel_message("g", panel, "1", "501")

            removed = await cog.delete_panels("g")
            assert removed == 3
            assert msg.deleted is True
            for panel in ("outages", "known_issues", "history"):
                assert await db.get_panel_message("g", panel) is None
        finally:
            os.unlink(path)
    asyncio.run(run())


async def _ready(value):
    return value


# A panel someone already deleted should not stop the rest being cleaned up.
def test_a_missing_panel_message_does_not_block_the_cleanup() -> None:
    async def run():
        db, path = await _db()
        try:
            cog = _cog(db)
            ch = FakeChannel(existing=None)
            cast(Any, cog).resolve_tracker_channel = lambda _id: _ready(ch)
            await db.upsert_panel_message("g", "outages", "1", "999")
            assert await cog.delete_panels("g") == 1
            assert await db.get_panel_message("g", "outages") is None
        finally:
            os.unlink(path)
    asyncio.run(run())
