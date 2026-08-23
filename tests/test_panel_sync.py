import asyncio
import os
import tempfile
from types import SimpleNamespace
from typing import Any, cast

import discord

from cogs.uptime import UptimeCog
from tracker_db import TrackerDatabase


class FakeMessage:
    def __init__(self, mid, pinned=False, channel=None):
        self.id = mid
        self.channel = channel
        self.edited = 0
        # discord.Message.pinned is a bool on the fetched message; the counters
        # sit beside it so a test can tell "is pinned" from "was pinned again".
        self.pinned = pinned
        self.pin_calls = 0
        self.unpinned = 0
    async def edit(self, **_): self.edited += 1
    async def pin(self, **_):
        self.pin_calls += 1
        self.pinned = True
    async def unpin(self, **_):
        self.unpinned += 1
        self.pinned = False


class FakeChannel(discord.TextChannel):
    def __init__(self, cid=1, existing=None, raise_on_fetch=None):
        self.id = cid
        self._existing = existing
        self._raise = raise_on_fetch
        self.sent = 0
        self.next_id = 500
        self.recent = []
        # A real Message always knows its channel, so a double handed to this one
        # as its existing message has to as well.
        if existing is not None and getattr(existing, "channel", None) is None:
            existing.channel = self

    async def fetch_message(self, mid):
        if self._raise:
            raise self._raise
        if self._existing and self._existing.id == mid:
            return self._existing
        raise discord.NotFound(cast(Any, SimpleNamespace(status=404, reason="")), "gone")

    async def send(self, **_):
        self.sent += 1
        self.next_id += 1
        self.last_sent = FakeMessage(self.next_id, channel=self)
        return self.last_sent

    def history(self, limit=None):
        """Newest first, as discord.py yields it."""

        async def walk():
            for entry in list(self.recent)[:limit]:
                yield entry

        return walk()


async def _ready(value):
    return value


async def _db():
    t = tempfile.NamedTemporaryFile(suffix=".db", delete=False); t.close()
    db = TrackerDatabase(t.name); await db.init()
    return db, t.name


def _cog(db):
    cog = UptimeCog.__new__(UptimeCog)
    # No channel by default: a test that cares about the old message hands one back.
    cast(Any, cog).bot = SimpleNamespace(
        db=db,
        get_channel=lambda _id: None,
        fetch_channel=lambda _id: _ready(None),
    )
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


# A panel people are meant to find without scrolling has to be pinned, and the
# pin has to follow the message it belongs to.
def test_a_new_panel_is_pinned() -> None:
    async def run():
        db, path = await _db()
        try:
            ch = FakeChannel()
            await _cog(db).sync_panel("g", "outages", cast(Any, ch), cast(Any, object()))
            assert ch.last_sent.pin_calls == 1
        finally:
            os.unlink(path)
    asyncio.run(run())


def test_editing_a_pinned_panel_does_not_pin_it_again() -> None:
    async def run():
        db, path = await _db()
        try:
            cog = _cog(db)
            ch = FakeChannel()
            await cog.sync_panel("g", "outages", cast(Any, ch), cast(Any, object()))
            first = ch.last_sent
            ch._existing = first
            await cog.sync_panel("g", "outages", cast(Any, ch), cast(Any, object()))
            assert first.edited == 1
            assert first.pin_calls == 1, "an edit re-pinned a message that was already pinned"
        finally:
            os.unlink(path)
    asyncio.run(run())


# Every panel that already exists takes the edit path, so pinning only on
# create reaches none of them. This is the case a running install is in.
def test_a_panel_that_already_exists_gets_pinned_on_the_next_cycle() -> None:
    async def run():
        db, path = await _db()
        try:
            cog = _cog(db)
            existing = FakeMessage(501, pinned=False)
            ch = FakeChannel(existing=existing)
            await db.upsert_panel_message("g", "outages", "1", "501")

            await cog.sync_panel("g", "outages", cast(Any, ch), cast(Any, object()))

            assert ch.sent == 0, "it reposted rather than editing what was there"
            assert existing.edited == 1
            assert existing.pin_calls == 1, "an unpinned panel was left unpinned"
            assert existing.pinned is True
        finally:
            os.unlink(path)
    asyncio.run(run())


# Without this the pin list only ever grows, and stops describing what is current.
def test_a_panel_that_moves_channel_unpins_the_one_it_leaves() -> None:
    async def run():
        db, path = await _db()
        try:
            cog = _cog(db)
            first = FakeChannel(cid=1)
            await cog.sync_panel("g", "outages", cast(Any, first), cast(Any, object()))
            old = first.last_sent
            first._existing = old
            cast(Any, cog).bot.get_channel = lambda cid: first if cid == 1 else None
            second = FakeChannel(cid=2)
            await cog.sync_panel("g", "outages", cast(Any, second), cast(Any, object()))
            assert old.unpinned == 1, "the panel left behind kept its pin"
            assert second.last_sent.pin_calls == 1
        finally:
            os.unlink(path)
    asyncio.run(run())


# The conditional panel has to leave when its condition does, taking its pin.
def test_removing_a_panel_deletes_the_message_and_the_record() -> None:
    async def run():
        db, path = await _db()
        try:
            cog = _cog(db)
            msg = DeletableMessage(501)
            ch = FakeChannel(existing=msg)
            cast(Any, cog).bot.get_channel = lambda _id: ch
            await db.upsert_panel_message("g", "known_issues", "1", "501")

            assert await cog.remove_panel("g", "known_issues") is True
            assert msg.deleted is True
            assert await db.get_panel_message("g", "known_issues") is None
            # The other panels are untouched by one going away.
            assert await cog.remove_panel("g", "outages") is False
        finally:
            os.unlink(path)
    asyncio.run(run())


class FakeSystemMessage:
    """Discord's own "pinned a message" notice."""

    def __init__(self, mid, kind, reference_id=None):
        self.id = mid
        self.type = kind
        self.reference = (
            SimpleNamespace(message_id=reference_id) if reference_id is not None else None
        )
        self.deleted = 0

    async def delete(self):
        self.deleted += 1


# Pinning posts a system message, so a tracker that pins its panels fills the
# channel with notices about its own housekeeping.
def test_pinning_a_panel_removes_the_notice_discord_posts() -> None:
  async def run():
    cog = _cog(None)
    channel = FakeChannel()
    message = FakeMessage(900, channel=channel)
    notice = FakeSystemMessage(901, discord.MessageType.pins_add, reference_id=900)
    channel.recent = [notice]

    await cog.pin_panel_message("outages", message)

    assert message.pin_calls == 1
    assert notice.deleted == 1
  asyncio.run(run())


def test_it_leaves_an_ordinary_message_alone() -> None:
  async def run():
    cog = _cog(None)
    channel = FakeChannel()
    message = FakeMessage(900, channel=channel)
    chatter = FakeSystemMessage(901, discord.MessageType.default)
    channel.recent = [chatter]

    await cog.pin_panel_message("outages", message)

    assert chatter.deleted == 0
  asyncio.run(run())


# Two panels pinned in a row: the notice for the other one is not ours to delete.
def test_it_leaves_another_messages_pin_notice_alone() -> None:
  async def run():
    cog = _cog(None)
    channel = FakeChannel()
    message = FakeMessage(900, channel=channel)
    other = FakeSystemMessage(901, discord.MessageType.pins_add, reference_id=42)
    channel.recent = [other]

    await cog.pin_panel_message("outages", message)

    assert other.deleted == 0
  asyncio.run(run())
