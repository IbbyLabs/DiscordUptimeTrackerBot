from typing import Any

import aiosqlite


class TrackerDatabase:
    def __init__(self, path: str) -> None:
        self.path = path

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS tracked_messages (
                    guild_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS alert_channels (
                    guild_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS service_states (
                    service_key TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.commit()

    async def get_tracked_message(self, guild_id: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT guild_id, channel_id, message_id FROM tracked_messages WHERE guild_id = ?",
                (guild_id,),
            ) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def list_tracked_messages(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT guild_id, channel_id, message_id FROM tracked_messages ORDER BY guild_id"
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def upsert_tracked_message(self, guild_id: str, channel_id: str, message_id: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO tracked_messages (guild_id, channel_id, message_id)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    message_id = excluded.message_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (guild_id, channel_id, message_id),
            )
            await db.commit()

    async def delete_tracked_message(self, guild_id: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM tracked_messages WHERE guild_id = ?", (guild_id,))
            await db.commit()

    async def get_alert_channel(self, guild_id: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT guild_id, channel_id FROM alert_channels WHERE guild_id = ?",
                (guild_id,),
            ) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def list_alert_channels(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT guild_id, channel_id FROM alert_channels ORDER BY guild_id"
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def upsert_alert_channel(self, guild_id: str, channel_id: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO alert_channels (guild_id, channel_id)
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (guild_id, channel_id),
            )
            await db.commit()

    async def delete_alert_channel(self, guild_id: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM alert_channels WHERE guild_id = ?", (guild_id,))
            await db.commit()

    async def get_service_states(self) -> dict[str, str]:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT service_key, state FROM service_states ORDER BY service_key"
            ) as cursor:
                rows = await cursor.fetchall()
        return {str(service_key): str(state) for service_key, state in rows}

    async def replace_service_states(self, states: dict[str, str]) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM service_states")
            if states:
                await db.executemany(
                    """
                    INSERT INTO service_states (service_key, state, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    """,
                    [(service_key, state) for service_key, state in states.items()],
                )
            await db.commit()
