from typing import Any

import aiosqlite

# The per-guild columns. Whitelisted rather than interpolated, since a column
# name cannot be bound as a parameter.
GUILD_SETTING_FIELDS = ("status_emoji", "status_page_url")
_GUILD_SETTING_COLUMNS = ", ".join(GUILD_SETTING_FIELDS)


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
                CREATE TABLE IF NOT EXISTS announced_incidents (
                    incident_id TEXT PRIMARY KEY,
                    opened_announced_at TEXT,
                    closed_announced_at TEXT,
                    seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS panel_messages (
                    guild_id TEXT NOT NULL,
                    panel TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, panel)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id TEXT PRIMARY KEY,
                    status_emoji TEXT,
                    status_page_url TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
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

    async def get_announced_incidents(self) -> dict[str, dict[str, bool]]:
        """What has already been said about each incident the page has shown us.

        A record of what this bot announced, not a copy of what happened; the
        page owns the incidents themselves.
        """

        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT incident_id, opened_announced_at, closed_announced_at"
                " FROM announced_incidents"
            ) as cursor:
                rows = await cursor.fetchall()
        return {
            str(r[0]): {"opened": r[1] is not None, "closed": r[2] is not None}
            for r in rows
        }

    async def mark_incidents_seen(
        self, incident_ids: list[str], *, closed: bool = False
    ) -> None:
        """Take incidents in without announcing them.

        Recorded as already-announced-open, so an outage present at intake is
        never later reported as starting. Its recovery is still news, so the
        closed marker is left alone unless the incident is already over.
        """

        if not incident_ids:
            return
        closed_at = "CURRENT_TIMESTAMP" if closed else "NULL"
        async with aiosqlite.connect(self.path) as db:
            await db.executemany(
                f"""
                INSERT OR IGNORE INTO announced_incidents
                    (incident_id, opened_announced_at, closed_announced_at)
                VALUES (?, CURRENT_TIMESTAMP, {closed_at})
                """,
                [(i,) for i in incident_ids],
            )
            await db.commit()

    async def mark_incidents_announced(
        self, opened: list[str], closed: list[str]
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            if opened:
                await db.executemany(
                    """
                    INSERT INTO announced_incidents (incident_id, opened_announced_at)
                    VALUES (?, CURRENT_TIMESTAMP)
                    ON CONFLICT(incident_id) DO UPDATE SET
                        opened_announced_at = COALESCE(opened_announced_at, CURRENT_TIMESTAMP)
                    """,
                    [(i,) for i in opened],
                )
            if closed:
                await db.executemany(
                    """
                    INSERT INTO announced_incidents (incident_id, closed_announced_at)
                    VALUES (?, CURRENT_TIMESTAMP)
                    ON CONFLICT(incident_id) DO UPDATE SET
                        closed_announced_at = COALESCE(closed_announced_at, CURRENT_TIMESTAMP)
                    """,
                    [(i,) for i in closed],
                )
            await db.commit()

    async def get_panel_message(self, guild_id: str, panel: str) -> dict[str, str] | None:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT channel_id, message_id FROM panel_messages"
                " WHERE guild_id = ? AND panel = ?",
                (guild_id, panel),
            ) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return None
        return {"channel_id": str(row[0]), "message_id": str(row[1])}

    async def upsert_panel_message(
        self, guild_id: str, panel: str, channel_id: str, message_id: str
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO panel_messages (guild_id, panel, channel_id, message_id, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(guild_id, panel) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    message_id = excluded.message_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (guild_id, panel, channel_id, message_id),
            )
            await db.commit()

    async def delete_panel_messages(self, guild_id: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM panel_messages WHERE guild_id = ?", (guild_id,))
            await db.commit()

    async def get_guild_settings(self, guild_id: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                f"SELECT {_GUILD_SETTING_COLUMNS} "
                "FROM guild_settings WHERE guild_id = ?",
                (guild_id,),
            ) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def list_guild_settings(self) -> dict[str, dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                f"SELECT guild_id, {_GUILD_SETTING_COLUMNS} "
                "FROM guild_settings"
            ) as cursor:
                rows = await cursor.fetchall()
        return {row["guild_id"]: dict(row) for row in rows}

    async def set_guild_setting(self, guild_id: str, field: str, value: Any) -> None:
        # Whitelisted rather than interpolated: the column name cannot be bound.
        if field not in GUILD_SETTING_FIELDS:
            raise ValueError(f"unknown guild setting: {field}")
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                f"""
                INSERT INTO guild_settings (guild_id, {field})
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    {field} = excluded.{field},
                    updated_at = CURRENT_TIMESTAMP
                """,
                (guild_id, value),
            )
            await db.commit()

    async def clear_guild_settings(self, guild_id: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM guild_settings WHERE guild_id = ?", (guild_id,))
            await db.commit()
