import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tracker_db import TrackerDatabase


def test_tracker_database_persists_alert_channels(tmp_path: Path) -> None:
    async def run() -> None:
        db = TrackerDatabase(str(tmp_path / "uptime.db"))
        await db.init()

        await db.upsert_alert_channel("1", "10")
        await db.upsert_alert_channel("2", "20")

        assert await db.get_alert_channel("1") == {"guild_id": "1", "channel_id": "10"}
        assert await db.list_alert_channels() == [
            {"guild_id": "1", "channel_id": "10"},
            {"guild_id": "2", "channel_id": "20"},
        ]

        await db.delete_alert_channel("1")

        assert await db.get_alert_channel("1") is None

    asyncio.run(run())