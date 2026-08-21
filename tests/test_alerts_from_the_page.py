import asyncio
import os
import tempfile
from types import SimpleNamespace
from typing import Any, cast

from cogs.uptime import UptimeCog
from tracker_db import TrackerDatabase


def _row(rid, closed=None, name="Api"):
    return {"id": rid, "name": name, "group": "Debrid", "state": "DOWN",
            "opened_at": "2026-08-21T22:15:05Z", "closed_at": closed}


class Recorder:
    def __init__(self): self.sent = []


async def _fresh():
    t = tempfile.NamedTemporaryFile(suffix=".db", delete=False); t.close()
    db = TrackerDatabase(t.name); await db.init()
    return db, t.name


def _cog(db, rows, recorder):
    cog = UptimeCog.__new__(UptimeCog)
    cast(Any, cog).bot = SimpleNamespace(db=db)

    async def fetch_incidents():
        return list(rows)

    async def send_alerts(messages):
        recorder.sent.extend(messages)
        return len(messages)

    cast(Any, cog).fetch_incidents = fetch_incidents
    cast(Any, cog).send_alerts = send_alerts
    return cog


def _headings(rec):
    return [h.splitlines()[0] for h, _ in rec.sent]


# Silent intake: the page is truth on the first cycle, the channel carries what
# happens after it.
def test_the_first_cycle_records_every_incident_and_says_nothing() -> None:
    async def run():
        db, path = await _fresh()
        try:
            rec = Recorder()
            cog = _cog(db, [_row("a"), _row("b", name="Web")], rec)
            assert await cog.process_status_alerts(cast(Any, {})) == 0
            assert rec.sent == []
            assert set(await db.get_announced_incidents()) == {"a", "b"}
        finally:
            os.unlink(path)
    asyncio.run(run())


def test_a_new_incident_after_that_is_announced_once() -> None:
    async def run():
        db, path = await _fresh()
        try:
            rec = Recorder()
            rows = [_row("a")]
            cog = _cog(db, rows, rec)
            await cog.process_status_alerts(cast(Any, {}))      # silent intake
            rows.append(_row("b", name="Web"))
            await cog.process_status_alerts(cast(Any, {}))
            assert _headings(rec) == ["## 🔴 Outage started"]
            await cog.process_status_alerts(cast(Any, {}))      # nothing new
            assert _headings(rec) == ["## 🔴 Outage started"]
        finally:
            os.unlink(path)
    asyncio.run(run())


def test_the_all_clear_waits_for_the_last_open_incident() -> None:
    async def run():
        db, path = await _fresh()
        try:
            rec = Recorder()
            rows = [_row("a")]
            cog = _cog(db, rows, rec)
            await cog.process_status_alerts(cast(Any, {}))
            rows.append(_row("b", name="Web"))
            await cog.process_status_alerts(cast(Any, {}))

            rows[1] = _row("b", closed="2026-08-21T23:00:00Z", name="Web")
            await cog.process_status_alerts(cast(Any, {}))
            assert _headings(rec)[-1] == "## 🟢 Back up", "claimed all clear while a was open"

            rows[0] = _row("a", closed="2026-08-21T23:10:00Z")
            await cog.process_status_alerts(cast(Any, {}))
            assert _headings(rec)[-1] == "## 🟢 All clear"
        finally:
            os.unlink(path)
    asyncio.run(run())


# It opened and closed between two cycles; announcing both ends at once is noise.
def test_an_incident_that_came_and_went_unseen_is_silent() -> None:
    async def run():
        db, path = await _fresh()
        try:
            rec = Recorder()
            rows = [_row("a")]
            cog = _cog(db, rows, rec)
            await cog.process_status_alerts(cast(Any, {}))
            rows.append(_row("b", closed="2026-08-21T23:00:00Z", name="Web"))
            await cog.process_status_alerts(cast(Any, {}))
            assert rec.sent == []
            assert "b" in await db.get_announced_incidents()
        finally:
            os.unlink(path)
    asyncio.run(run())


def test_a_failed_fetch_announces_nothing_rather_than_an_all_clear() -> None:
    async def run():
        db, path = await _fresh()
        try:
            rec = Recorder()
            cog = _cog(db, [], rec)
            assert await cog.process_status_alerts(cast(Any, {})) == 0
            assert rec.sent == []
            assert await db.get_announced_incidents() == {}
        finally:
            os.unlink(path)
    asyncio.run(run())


def _suppressed_row(rid, closed=None):
    return {"id": rid, "service_id": "webstreamr-mbg", "name": "WebStreamr MBG",
            "group": "Content Scrapers", "state": "DOWN",
            "opened_at": "2026-08-21T22:15:05Z", "closed_at": closed}


# The suppression list has to be reached by the alert path, not merely defined
# beside it — nine of the last fifty incidents on the page are this one service.
def test_a_suppressed_service_never_reaches_the_channel() -> None:
    async def run():
        db, path = await _fresh()
        try:
            rec = Recorder()
            rows = [_row("a")]
            cog = _cog(db, rows, rec)
            await cog.process_status_alerts(cast(Any, {}))       # silent intake
            rows.append(_suppressed_row("noisy-1"))
            await cog.process_status_alerts(cast(Any, {}))
            assert rec.sent == [], "announced a service on the suppression list"

            rows.append(_row("b", name="Real"))
            await cog.process_status_alerts(cast(Any, {}))
            assert _headings(rec) == ["## 🔴 Outage started"], "the real one should still fire"
        finally:
            os.unlink(path)
    asyncio.run(run())
