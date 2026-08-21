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
                CREATE TABLE IF NOT EXISTS service_states (
                    service_key TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
                CREATE TABLE IF NOT EXISTS incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    opened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    closed_at TEXT
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS incident_services (
                    incident_id INTEGER NOT NULL,
                    service_key TEXT NOT NULL,
                    name TEXT NOT NULL,
                    joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    recovered_at TEXT,
                    PRIMARY KEY (incident_id, service_key)
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

    async def get_open_incident(self) -> dict[str, object] | None:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT id, opened_at FROM incidents"
                " WHERE closed_at IS NULL ORDER BY id DESC LIMIT 1"
            ) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return None
        return {"id": int(row[0]), "opened_at": str(row[1])}

    async def open_incident(self) -> int:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "INSERT INTO incidents (opened_at) VALUES (CURRENT_TIMESTAMP)"
            )
            await db.commit()
            return int(cursor.lastrowid or 0)

    async def close_incident(self, incident_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE incidents SET closed_at = CURRENT_TIMESTAMP"
                " WHERE id = ? AND closed_at IS NULL",
                (incident_id,),
            )
            await db.commit()

    async def add_incident_services(
        self, incident_id: int, services: list[tuple[str, str]]
    ) -> None:
        """Record services as part of an incident.

        A service already recorded keeps its original joined_at and stays
        recovered or not, so a flap does not re-open its entry.
        """

        if not services:
            return
        async with aiosqlite.connect(self.path) as db:
            await db.executemany(
                """
                INSERT OR IGNORE INTO incident_services (incident_id, service_key, name, joined_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                [(incident_id, key, name) for key, name in services],
            )
            await db.commit()

    async def mark_incident_services_recovered(
        self, incident_id: int, service_keys: list[str]
    ) -> None:
        if not service_keys:
            return
        async with aiosqlite.connect(self.path) as db:
            await db.executemany(
                """
                UPDATE incident_services SET recovered_at = CURRENT_TIMESTAMP
                WHERE incident_id = ? AND service_key = ? AND recovered_at IS NULL
                """,
                [(incident_id, key) for key in service_keys],
            )
            await db.commit()

    async def mark_incident_services_down(
        self, incident_id: int, service_keys: list[str]
    ) -> None:
        """Clear the recovery on services that have failed again.

        The announcement stays quiet for a service the incident already named,
        but the all-clear has to wait for it, so its recovery is withdrawn.
        """

        if not service_keys:
            return
        async with aiosqlite.connect(self.path) as db:
            await db.executemany(
                """
                UPDATE incident_services SET recovered_at = NULL
                WHERE incident_id = ? AND service_key = ?
                """,
                [(incident_id, key) for key in service_keys],
            )
            await db.commit()

    async def list_incident_services(self, incident_id: int) -> list[dict[str, object]]:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                """
                SELECT service_key, name, joined_at, recovered_at FROM incident_services
                WHERE incident_id = ? ORDER BY joined_at, service_key
                """,
                (incident_id,),
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            {"service_key": str(r[0]), "name": str(r[1]),
             "joined_at": str(r[2]),
             "recovered_at": None if r[3] is None else str(r[3])}
            for r in rows
        ]

    async def list_recent_incidents(self, limit: int = 10) -> list[dict[str, object]]:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT id, opened_at, closed_at FROM incidents ORDER BY id DESC LIMIT ?",
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            {"id": int(r[0]), "opened_at": str(r[1]),
             "closed_at": None if r[2] is None else str(r[2])}
            for r in rows
        ]

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
