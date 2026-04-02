import asyncio
import logging
import sys
from typing import Protocol, Sequence

import discord
from discord.ext import commands

from config import Config
from tracker_db import TrackerDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("uptimebot")
COMMAND_SYNC_RETRY_DELAYS = (2.0, 5.0, 10.0)


class AppCommandTreeLike(Protocol):
    def copy_global_to(self, *, guild: discord.abc.Snowflake) -> None:
        ...

    async def sync(self, *, guild: discord.abc.Snowflake | None = None) -> Sequence[object]:
        ...


async def sync_app_commands(tree: AppCommandTreeLike, guild_id: int | None) -> bool:
    guild = discord.Object(id=guild_id) if guild_id else None
    scope = f"guild {guild_id}" if guild_id else "global"

    if guild is not None:
        tree.copy_global_to(guild=guild)

    for attempt in range(len(COMMAND_SYNC_RETRY_DELAYS) + 1):
        try:
            synced = await tree.sync(guild=guild)
            if guild_id:
                log.info("Synced %d commands to guild %d", len(synced), guild_id)
            else:
                log.info("Synced %d commands globally", len(synced))
            return True
        except discord.DiscordServerError as exc:
            if attempt >= len(COMMAND_SYNC_RETRY_DELAYS):
                log.warning(
                    "Command sync failed for %s after %d attempts. Starting without fresh command sync: %s",
                    scope,
                    attempt + 1,
                    exc,
                )
                return False
            delay = COMMAND_SYNC_RETRY_DELAYS[attempt]
            log.warning(
                "Command sync failed for %s on attempt %d/%d with Discord server error: %s. Retrying in %.1f seconds.",
                scope,
                attempt + 1,
                len(COMMAND_SYNC_RETRY_DELAYS) + 1,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
        except discord.HTTPException as exc:
            log.warning(
                "Command sync failed for %s. Starting without fresh command sync: %s",
                scope,
                exc,
            )
            return False
    return False


class DiscordUptimeTrackerBot(commands.Bot):
    def __init__(self) -> None:
        config = Config()
        intents = discord.Intents.default()
        intents.guilds = True
        intents.message_content = True
        super().__init__(command_prefix=config.COMMAND_PREFIX, intents=intents, help_command=None)
        self.config = config
        self.db: TrackerDatabase | None = None
        self.start_time = discord.utils.utcnow()
        try:
            with open("VERSION", "r", encoding="utf-8") as handle:
                self.version = handle.read().strip()
        except FileNotFoundError:
            self.version = "0.1.0"

    def get_uptime_str(self) -> str:
        diff = discord.utils.utcnow() - self.start_time
        days = diff.days
        hours, remainder = divmod(diff.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        parts: list[str] = []
        if days > 0:
            parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours > 0:
            parts.append(f"{hours} hr{'s' if hours != 1 else ''}")
        if minutes > 0:
            parts.append(f"{minutes} min{'s' if minutes != 1 else ''}")
        if seconds > 0 or not parts:
            parts.append(f"{seconds} sec{'s' if seconds != 1 else ''}")
        return ", ".join(parts)

    async def presence_updater(self) -> None:
        await self.wait_until_ready()
        while not self.is_closed():
            uptime_str = self.get_uptime_str()
            status = f"Uptime | Up for {uptime_str}"
            try:
                emoji = self.config.STATUS_EMOJI
                partial_emoji = None
                if emoji.isdigit():
                    partial_emoji = discord.PartialEmoji(name="emoji", id=int(emoji))
                elif emoji.startswith("<:") and emoji.endswith(">"):
                    try:
                        partial_emoji = discord.PartialEmoji.from_str(emoji)
                    except Exception:
                        log.warning("Invalid custom emoji format: %s", emoji)
                await self.change_presence(
                    activity=discord.CustomActivity(name=status, emoji=partial_emoji)
                )
            except Exception as exc:
                log.error("Failed to update presence: %s", exc)
            await asyncio.sleep(15)

    async def setup_hook(self) -> None:
        self.db = TrackerDatabase(self.config.DATABASE_PATH)
        await self.db.init()
        self.loop.create_task(self.presence_updater())
        await self.load_extension("cogs.uptime")
        await sync_app_commands(self.tree, self.config.GUILD_ID)

    async def on_ready(self) -> None:
        if self.user is not None:
            log.info("DiscordUptimeTrackerBot ready. Logged in as %s (%d)", self.user, self.user.id)


async def main() -> None:
    bot = DiscordUptimeTrackerBot()
    async with bot:
        await bot.start(bot.config.BOT_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
