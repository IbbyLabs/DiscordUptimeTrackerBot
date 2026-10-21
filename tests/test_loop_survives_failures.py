import asyncio
import os
import tempfile
from types import SimpleNamespace
from typing import Any, cast

import discord

import cogs.uptime as uptime
from cogs.uptime import UptimeCog
from tracker_db import TrackerDatabase


def _http_error(cls: type[discord.HTTPException], status: int) -> discord.HTTPException:
    return cls(cast(Any, SimpleNamespace(status=status, reason="test")), "test")


def _row(rid, closed=None, name="Api"):
    return {"id": rid, "name": name, "group": "Debrid", "state": "DOWN",
            "opened_at": "2026-08-21T22:15:05Z", "closed_at": closed}


async def _fresh():
    t = tempfile.NamedTemporaryFile(suffix=".db", delete=False); t.close()
    db = TrackerDatabase(t.name); await db.init()
    return db, t.name


class FlakyChannel:
    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.sent = 0

    async def send(self, **_kwargs):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise _http_error(discord.HTTPException, 503)
        self.sent += 1
        return SimpleNamespace(id=1)


def _alert_cog(db, rows, channel):
    cog = UptimeCog.__new__(UptimeCog)
    cast(Any, cog).bot = SimpleNamespace(db=db)

    async def fetch_incidents(*, major_only: bool = True):
        return list(rows)

    async def resolve_tracker_channel(_channel_id):
        return channel

    async def guild_render_settings(_guild_id):
        return {}

    async def panel_jump_url(_guild_id, _panel):
        return None

    async def guild_locale(_guild_id):
        return None

    cast(Any, cog).fetch_incidents = fetch_incidents
    cast(Any, cog).resolve_tracker_channel = resolve_tracker_channel
    cast(Any, cog).guild_render_settings = guild_render_settings
    cast(Any, cog).panel_jump_url = panel_jump_url
    cast(Any, cog).guild_locale = guild_locale
    cast(Any, cog).active_outages = lambda _data: [r for r in rows if r["closed_at"] is None]
    cast(Any, cog).visible_services = lambda _data: [{"id": "", "name": r["name"]} for r in rows]
    return cog


def test_an_alert_that_failed_to_send_is_retried_next_cycle(monkeypatch) -> None:
    monkeypatch.setattr(uptime, "PanelLayout", lambda *a, **k: object())

    async def run():
        db, path = await _fresh()
        try:
            await db.upsert_alert_channel("1", "10")
            rows = [_row("a")]
            channel = FlakyChannel(fail_times=1)
            cog = _alert_cog(db, rows, channel)
            await cog.process_status_alerts(cast(Any, {}))      # silent intake
            rows.append(_row("b", name="Web"))

            await cog.process_status_alerts(cast(Any, {}))      # send fails
            assert channel.sent == 0
            assert "b" not in await db.get_announced_incidents()

            await cog.process_status_alerts(cast(Any, {}))      # retried
            assert channel.sent == 1
            assert "b" in await db.get_announced_incidents()
        finally:
            os.unlink(path)
    asyncio.run(run())


def test_a_failed_cycle_does_not_end_the_refresh_loop() -> None:
    cog = UptimeCog.__new__(UptimeCog)

    async def wait_until_ready():
        return None

    async def run_status_cycle():
        raise AttributeError("'NoneType' object has no attribute 'get'")

    cast(Any, cog).bot = SimpleNamespace(wait_until_ready=wait_until_ready)
    cast(Any, cog).run_status_cycle = run_status_cycle
    asyncio.run(UptimeCog.refresh_status_task.coro(cog))


def test_a_board_that_cannot_be_replaced_does_not_stop_the_others(monkeypatch) -> None:
    monkeypatch.setattr(uptime, "StatusLayout", lambda *a, **k: object())

    class GoneChannel:
        async def fetch_message(self, _message_id):
            raise _http_error(discord.NotFound, 404)

        async def send(self, **_kwargs):
            raise _http_error(discord.Forbidden, 403)

    class LiveChannel:
        def __init__(self):
            self.edited = 0

        async def fetch_message(self, _message_id):
            channel = self

            class Message:
                flags = SimpleNamespace(components_v2=True)

                async def edit(self, **_kwargs):
                    channel.edited += 1
            return Message()

    live = LiveChannel()
    channels = {10: GoneChannel(), 20: live}

    async def list_tracked_messages():
        return [
            {"guild_id": "1", "channel_id": "10", "message_id": "100"},
            {"guild_id": "2", "channel_id": "20", "message_id": "200"},
        ]

    async def resolve_tracker_channel(channel_id):
        return channels[channel_id]

    async def guild_render_settings(_guild_id):
        return {}

    cog = UptimeCog.__new__(UptimeCog)
    cast(Any, cog).bot = SimpleNamespace(db=SimpleNamespace(list_tracked_messages=list_tracked_messages))
    cast(Any, cog).resolve_tracker_channel = resolve_tracker_channel
    cast(Any, cog).guild_render_settings = guild_render_settings

    assert asyncio.run(cog.update_tracked_messages(cast(Any, {"services": []}))) == 1
    assert live.edited == 1
