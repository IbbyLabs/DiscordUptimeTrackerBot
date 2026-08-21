import asyncio
import os
import tempfile
from types import SimpleNamespace
from typing import Any, cast

from incidents import build_incident_messages
from tracker_db import TrackerDatabase


class _Caller:
    """Keeps the tests reading as a sequence of cycles against one database."""

    def __init__(self, db):
        self._db = db
        # The real caller passes every service in the payload, not only the ones
        # that changed, so the catalogue accumulates rather than resetting.
        self._catalogue: set[str] = set()

    async def incident_messages(self, changes, present_keys=None):
        self._catalogue.update(str(c["key"]) for c in changes)
        if present_keys is None:
            present_keys = set(self._catalogue)
        return await build_incident_messages(self._db, changes, present_keys)


def _cog(db):
    return _Caller(db)


def _change(key, name, state, previous):
    return {
        "key": key, "group": "Debrid Services", "name": name,
        "state": state, "previous_state": previous,
        "latency": 100, "uptime_percent": 99.0,
    }


async def _fresh():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db = TrackerDatabase(tmp.name)
    await db.init()
    return db, tmp.name


def _headings(messages):
    return [heading.splitlines()[0] for heading, _ in messages]


# The whole sequence a real outage produces, in order, against a real database.
def test_an_outage_opens_spreads_recovers_and_clears() -> None:
    async def run() -> None:
        db, path = await _fresh()
        try:
            cog = _cog(db)

            opened = await cog.incident_messages([_change("a", "A", "DOWN", "UP")])
            assert _headings(opened) == ["## Outage started"]

            spread = await cog.incident_messages([_change("b", "B", "DOWN", "UP")])
            assert _headings(spread) == ["## Outage spreading"]

            partial = await cog.incident_messages([_change("a", "A", "UP", "DOWN")])
            assert _headings(partial) == ["## Back up"]

            clear = await cog.incident_messages([_change("b", "B", "UP", "DOWN")])
            assert _headings(clear) == ["## All clear"]

            assert await db.get_open_incident() is None
        finally:
            os.unlink(path)

    asyncio.run(run())


# Already named by this incident, so the channel stays quiet and the all-clear
# still waits for it.
def test_a_service_flapping_inside_an_incident_is_quiet_but_still_counted() -> None:
    async def run() -> None:
        db, path = await _fresh()
        try:
            cog = _cog(db)
            await cog.incident_messages([_change("a", "A", "DOWN", "UP")])
            await cog.incident_messages([_change("b", "B", "DOWN", "UP")])
            await cog.incident_messages([_change("a", "A", "UP", "DOWN")])

            quiet = await cog.incident_messages([_change("a", "A", "DOWN", "UP")])
            assert quiet == []
            assert await db.get_open_incident() is not None

            still = await cog.incident_messages([_change("b", "B", "UP", "DOWN")])
            assert _headings(still) == ["## Back up"], "the all-clear fired while a service was down"
        finally:
            os.unlink(path)

    asyncio.run(run())


def test_several_failing_in_one_cycle_produce_one_message() -> None:
    async def run() -> None:
        db, path = await _fresh()
        try:
            cog = _cog(db)
            msgs = await cog.incident_messages([
                _change("a", "A", "DOWN", "UP"),
                _change("b", "B", "DOWN", "UP"),
                _change("c", "C", "DOWN", "UP"),
            ])
            assert len(msgs) == 1
            heading, group = msgs[0]
            assert "3 services are not responding" in heading
            assert len(group) == 3
        finally:
            os.unlink(path)

    asyncio.run(run())


def test_nothing_changing_announces_nothing() -> None:
    async def run() -> None:
        db, path = await _fresh()
        try:
            assert await _cog(db).incident_messages([]) == []
        finally:
            os.unlink(path)

    asyncio.run(run())


def test_an_incident_closed_only_by_a_vanished_service_says_nothing() -> None:
    async def run() -> None:
        db, path = await _fresh()
        try:
            cog = _cog(db)
            await cog.incident_messages([_change("a", "A", "DOWN", "UP")])
            # The row is hidden or renamed, so it is gone from the payload.
            quiet = await build_incident_messages(db, [], present_keys={"z"})
            assert quiet == [], "claimed an all-clear for a service that never recovered"
            assert await db.get_open_incident() is None
        finally:
            os.unlink(path)

    asyncio.run(run())


def test_a_real_recovery_still_announces_the_all_clear() -> None:
    async def run() -> None:
        db, path = await _fresh()
        try:
            cog = _cog(db)
            await cog.incident_messages([_change("a", "A", "DOWN", "UP")])
            msgs = await build_incident_messages(
                db, [_change("a", "A", "UP", "DOWN")], present_keys={"a"}
            )
            assert _headings(msgs) == ["## All clear"]
        finally:
            os.unlink(path)

    asyncio.run(run())
