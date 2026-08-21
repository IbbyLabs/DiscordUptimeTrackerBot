import asyncio
import os
import tempfile

from tracker_db import TrackerDatabase


def _make_db() -> tuple[TrackerDatabase, str]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    return TrackerDatabase(tmp.name), tmp.name


def test_one_incident_is_open_at_a_time_and_closes() -> None:
    async def run() -> None:
        db, path = _make_db()
        try:
            await db.init()
            assert await db.get_open_incident() is None
            first = await db.open_incident()
            open_now = await db.get_open_incident()
            assert open_now is not None and open_now["id"] == first
            await db.close_incident(first)
            assert await db.get_open_incident() is None
        finally:
            os.unlink(path)

    asyncio.run(run())


def test_a_service_rejoining_keeps_its_original_entry() -> None:
    async def run() -> None:
        db, path = _make_db()
        try:
            await db.init()
            inc = await db.open_incident()
            await db.add_incident_services(inc, [("g|Api|u", "Api")])
            await db.mark_incident_services_recovered(inc, ["g|Api|u"])
            # The same service failing again inside the incident must not
            # reopen its entry or duplicate the row.
            await db.add_incident_services(inc, [("g|Api|u", "Api")])
            rows = await db.list_incident_services(inc)
            assert len(rows) == 1
            assert rows[0]["recovered_at"] is not None
        finally:
            os.unlink(path)

    asyncio.run(run())


def test_recovering_marks_only_the_named_services() -> None:
    async def run() -> None:
        db, path = _make_db()
        try:
            await db.init()
            inc = await db.open_incident()
            await db.add_incident_services(inc, [("a", "A"), ("b", "B")])
            await db.mark_incident_services_recovered(inc, ["a"])
            rows = {r["service_key"]: r["recovered_at"] for r in await db.list_incident_services(inc)}
            assert rows["a"] is not None
            assert rows["b"] is None
        finally:
            os.unlink(path)

    asyncio.run(run())
