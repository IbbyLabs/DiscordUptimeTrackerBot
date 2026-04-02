import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Awaitable, Callable

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from ui.status_views import StatusDashboardView, StatusPaginationView

if TYPE_CHECKING:
    from bot import DiscordUptimeTrackerBot

log = logging.getLogger("uptimebot.cogs.uptime")

StatusData = dict[str, Any]
StatusSender = Callable[[discord.Embed], Awaitable[object]]
ErrorSender = Callable[[str], Awaitable[object]]
StatusViewSender = Callable[[discord.Embed, discord.ui.View], Awaitable[object]]
TRACKER_CHANNEL_TYPES = (
    discord.TextChannel,
    discord.Thread,
    discord.VoiceChannel,
)


def is_bot_owner():
    def predicate(interaction: discord.Interaction) -> bool:
        config = getattr(interaction.client, "config", None)
        if not config or getattr(config, "BOT_OWNER_ID", None) is None:
            return False
        return interaction.user.id == config.BOT_OWNER_ID

    return app_commands.check(predicate)


class UptimeCog(commands.Cog):
    tracker = app_commands.Group(name="tracker", description="Manage uptime tracker messages")

    def __init__(self, bot: "DiscordUptimeTrackerBot") -> None:
        self.bot = bot
        self.status_api_url = bot.config.STATUS_API_URL

    async def cog_load(self) -> None:
        self.refresh_status_task.change_interval(minutes=self.bot.config.REFRESH_MINUTES)
        self.refresh_status_task.start()
        data = await self.fetch_status()
        if data:
            self.bot.add_view(StatusDashboardView(self.bot, self, data))

    async def cog_unload(self) -> None:
        self.refresh_status_task.cancel()

    @tasks.loop(minutes=10.0)
    async def refresh_status_task(self) -> None:
        await self.bot.wait_until_ready()
        await self.update_tracked_messages()

    async def fetch_status(self) -> StatusData | None:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.status_api_url,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        log.error("Failed to fetch status: HTTP %s", response.status)
                        return None
                    payload = await response.json()
                    if not isinstance(payload, dict):
                        log.error(
                            "Unexpected status payload type: %s",
                            type(payload).__name__,
                        )
                        return None
                    return payload
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            log.error("Error fetching status: %s", exc)
            return None

    def tracker_name(self, data: StatusData) -> str:
        source_name = str(data.get("source", {}).get("name") or "").strip()
        return source_name or self.bot.config.BRAND_NAME

    def visible_services(self, data: StatusData) -> list[StatusData]:
        services = data.get("services", [])
        return [service for service in services if not service.get("hideFromStatusPage")]

    def group_services(self, data: StatusData) -> dict[str, list[StatusData]]:
        groups: dict[str, list[StatusData]] = {}
        for service in self.visible_services(data):
            group_name = str(service.get("group") or "Other")
            groups.setdefault(group_name, []).append(service)
        return groups

    def get_state_emoji(self, state: str) -> str:
        healthy = self.bot.config.STATUS_EMOJI
        if healthy.isdigit():
            healthy = f"<:emoji:{healthy}>"
        if state == "DOWN":
            return "🔴"
        if state == "DEGRADED":
            return "🟡"
        if state == "MAINTENANCE":
            return "🛠️"
        if state == "UNKNOWN":
            return "⚪"
        return healthy

    def get_status_text(self, services: list[StatusData]) -> str:
        down_count = sum(
            1 for service in services if service.get("last", {}).get("state") == "DOWN"
        )
        degraded_count = sum(
            1 for service in services if service.get("last", {}).get("state") == "DEGRADED"
        )
        maintenance_count = sum(
            1 for service in services if service.get("last", {}).get("state") == "MAINTENANCE"
        )
        if down_count > 0:
            noun = "Service" if down_count == 1 else "Services"
            return f"🔴 {down_count} {noun} Down"
        if degraded_count > 0:
            return "🟡 Services Degraded"
        if maintenance_count > 0:
            return "🛠️ Under Maintenance"
        return f"{self.get_state_emoji('UP')} All Systems Operational"

    def get_uptime_bar(self, percent: float) -> str:
        filled = max(0, min(10, round(percent / 10)))
        return "█" * filled + "░" * (10 - filled)

    def last_updated_unix(self, data: StatusData) -> int:
        generated_at = str(data.get("generatedAt") or "").strip()
        if generated_at:
            try:
                parsed_time = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
                return int(parsed_time.timestamp())
            except ValueError:
                pass
        return int(discord.utils.utcnow().timestamp())

    def _summary_counts(self, data: StatusData) -> tuple[int, int, int]:
        summary = data.get("summary", {})
        up_count = int(summary.get("up", 0))
        down_count = int(summary.get("down", 0))
        degraded_count = int(summary.get("degraded", 0))
        return up_count, down_count, degraded_count

    def _embed_title(
        self,
        data: StatusData,
        page_info: tuple[int, int] | None,
    ) -> str:
        embed_title = self.tracker_name(data)
        if page_info:
            return f"{embed_title} Page {page_info[0]}/{page_info[1]}"
        return embed_title

    def _embed_description(
        self,
        data: StatusData,
        services: list[StatusData],
    ) -> str:
        tracker_name = self.tracker_name(data)
        up_count, down_count, degraded_count = self._summary_counts(data)
        return (
            f"**Welcome to {tracker_name}**\n\n"
            f"{self.bot.config.BRAND_DESCRIPTION}\n\n"
            f"You can view the full status page at: "
            f"**{self.bot.config.STATUS_PAGE_URL}**\n\n"
            f"### {self.get_status_text(services)}\n"
            f"**Up:** {up_count} | **Down:** {down_count} | "
            f"**Degraded:** {degraded_count}"
        )

    def _summary_field_value(self, services: list[StatusData]) -> str:
        group_up = sum(1 for item in services if item.get("last", {}).get("state") == "UP")
        group_total = len(services)
        affected = group_total - group_up
        group_emoji = self.get_state_emoji("UP") if affected == 0 else "🔴"
        noun = "Service" if affected == 1 else "Services"
        status_text = "Operational" if affected == 0 else f"{affected} {noun} Affected"
        return f"{group_emoji} {group_up}/{group_total} {status_text}"

    def _detail_lines(self, services: list[StatusData], has_auth: bool) -> list[str]:
        lines: list[str] = []
        if has_auth:
            lines.append("Some services are behind authentication and marked with a lock.")
        for service in services:
            last = service.get("last", {})
            state = str(last.get("state") or "UNKNOWN")
            latency = int(last.get("latency") or 0)
            uptime_percent = float(service.get("uptimePercent") or 0)
            url = str(service.get("url") or self.bot.config.STATUS_PAGE_URL)
            name = str(service.get("name") or "Unknown Service")
            if service.get("requiresAuth"):
                name = f"{name} 🔒"
            uptime_bar = self.get_uptime_bar(uptime_percent)
            lines.append(
                f"{self.get_state_emoji(state)} **[{name}]({url})**: "
                f"{state} ({latency}ms)\n"
                f"{uptime_bar} {uptime_percent:.1f}% uptime"
            )
        return lines

    def _field_chunks(self, display_name: str, lines: list[str]) -> list[tuple[str, str]]:
        field_chunks: list[tuple[str, str]] = []
        current_value = ""
        field_index = 1
        for line in lines:
            next_value = f"{current_value}\n{line}".strip() if current_value else line
            if len(next_value) > 1024:
                field_name = display_name if field_index == 1 else f"{display_name} {field_index}"
                field_chunks.append((field_name, current_value))
                current_value = line
                field_index += 1
                continue
            current_value = next_value
        if current_value:
            field_name = display_name if field_index == 1 else f"{display_name} {field_index}"
            field_chunks.append((field_name, current_value))
        return field_chunks

    def _add_group_fields(
        self,
        embed: discord.Embed,
        data: StatusData,
        *,
        summary_mode: bool,
    ) -> None:
        for group_name, group_items in self.group_services(data).items():
            has_auth = any(item.get("requiresAuth") for item in group_items)
            display_name = f"{group_name} 🔒" if has_auth else group_name
            if summary_mode:
                embed.add_field(
                    name=display_name,
                    value=self._summary_field_value(group_items),
                    inline=True,
                )
                continue
            for field_name, field_value in self._field_chunks(
                display_name,
                self._detail_lines(group_items, has_auth),
            ):
                embed.add_field(name=field_name, value=field_value, inline=False)

    def create_status_embed(
        self,
        data: StatusData,
        page_info: tuple[int, int] | None = None,
        summary_mode: bool = False,
    ) -> discord.Embed:
        services = self.visible_services(data)
        description = (
            self._embed_description(data, services)
        )
        embed = discord.Embed(
            title=self._embed_title(data, page_info),
            description=description,
            color=0x5A189A,
            url=self.bot.config.STATUS_PAGE_URL,
        )
        self._add_group_fields(embed, data, summary_mode=summary_mode)
        embed.add_field(
            name="Last Updated",
            value=f"<t:{self.last_updated_unix(data)}:R>",
            inline=True,
        )
        embed.set_footer(text="Owned, created, and maintained by Ibby")
        if self.bot.user and self.bot.user.display_avatar:
            embed.set_author(
                name=self.tracker_name(data),
                icon_url=self.bot.user.display_avatar.url,
                url=self.bot.config.STATUS_PAGE_URL,
            )
        return embed

    async def update_tracked_messages(self) -> int:
        if self.bot.db is None:
            return 0
        tracked_messages = await self.bot.db.list_tracked_messages()
        if not tracked_messages:
            return 0
        data = await self.fetch_status()
        if not data:
            return 0
        view = StatusDashboardView(self.bot, self, data)
        embed = self.create_status_embed(data, summary_mode=True)
        updated = 0
        for item in tracked_messages:
            guild_id = str(item["guild_id"])
            channel_id = int(item["channel_id"])
            message_id = int(item["message_id"])
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except discord.HTTPException:
                    continue
            if not isinstance(channel, TRACKER_CHANNEL_TYPES):
                continue
            try:
                message = await channel.fetch_message(message_id)
                await message.edit(embed=embed, view=view)
                updated += 1
            except discord.NotFound:
                new_message = await channel.send(embed=embed, view=view)
                await self.bot.db.upsert_tracked_message(
                    guild_id,
                    str(channel_id),
                    str(new_message.id),
                )
                updated += 1
            except discord.HTTPException as exc:
                log.error(
                    "Failed to update tracker message in channel %s: %s",
                    channel_id,
                    exc,
                )
        return updated

    async def send_uptime_response(
        self,
        send_embed: StatusSender,
        send_error: ErrorSender,
        send_embed_with_view: StatusViewSender,
    ) -> None:
        data = await self.fetch_status()
        if not data:
            await send_error("I could not fetch status data right now.")
            return
        view = StatusPaginationView(self.bot, self, data)
        if not view.group_names:
            await send_error("No services were found.")
            return
        group_name = view.group_names[0]
        page_data = data.copy()
        page_data["services"] = view.groups[group_name]
        embed = self.create_status_embed(
            page_data,
            page_info=(1, len(view.group_names)),
            summary_mode=False,
        )
        if len(view.group_names) > 1:
            await send_embed_with_view(embed, view)
            return
        await send_embed(embed)

    @tracker.command(name="setup", description="Create a live uptime tracker message")
    @is_bot_owner()
    async def setup_tracker(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(
            interaction.channel,
            TRACKER_CHANNEL_TYPES,
        ):
            await interaction.response.send_message(
                "Cannot use this command here.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        data = await self.fetch_status()
        if not data or self.bot.db is None:
            await interaction.followup.send(
                "I could not fetch status data right now.",
                ephemeral=True,
            )
            return
        embed = self.create_status_embed(data, summary_mode=True)
        view = StatusDashboardView(self.bot, self, data)
        message = await interaction.channel.send(embed=embed, view=view)
        await self.bot.db.upsert_tracked_message(
            str(interaction.guild_id),
            str(interaction.channel_id),
            str(message.id),
        )
        await interaction.followup.send(
            "Uptime tracker message created. It will refresh automatically.",
            ephemeral=True,
        )

    @tracker.command(name="refresh", description="Refresh all live uptime tracker messages")
    @is_bot_owner()
    async def refresh_tracker(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        count = await self.update_tracked_messages()
        await interaction.followup.send(
            f"Refreshed {count} uptime tracker message(s).",
            ephemeral=True,
        )

    @tracker.command(
        name="remove",
        description="Stop tracking the live uptime message for this guild",
    )
    @is_bot_owner()
    async def remove_tracker(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or self.bot.db is None:
            await interaction.response.send_message(
                "Cannot use this command here.",
                ephemeral=True,
            )
            return
        await self.bot.db.delete_tracked_message(str(interaction.guild_id))
        await interaction.response.send_message(
            "Removed the tracked uptime message for this guild.",
            ephemeral=True,
        )

    @app_commands.command(name="uptime", description="View live service uptime")
    async def uptime_slash(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await self.send_uptime_response(
            lambda embed: interaction.followup.send(embed=embed, ephemeral=True),
            lambda text: interaction.followup.send(text, ephemeral=True),
            lambda embed, view: interaction.followup.send(embed=embed, view=view, ephemeral=True),
        )

    @commands.command(name="setupuptime")
    async def setup_uptime_prefix(self, ctx: commands.Context) -> None:
        if self.bot.config.BOT_OWNER_ID and ctx.author.id != self.bot.config.BOT_OWNER_ID:
            return
        if self.bot.db is None:
            return
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        data = await self.fetch_status()
        if not data:
            await ctx.send("I could not fetch status data right now.", delete_after=10)
            return
        embed = self.create_status_embed(data, summary_mode=True)
        view = StatusDashboardView(self.bot, self, data)
        message = await ctx.send(embed=embed, view=view)
        if ctx.guild:
            await self.bot.db.upsert_tracked_message(
                str(ctx.guild.id),
                str(ctx.channel.id),
                str(message.id),
            )

    @commands.command(name="refreshuptime")
    async def refresh_uptime_prefix(self, ctx: commands.Context) -> None:
        if self.bot.config.BOT_OWNER_ID and ctx.author.id != self.bot.config.BOT_OWNER_ID:
            return
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        count = await self.update_tracked_messages()
        await ctx.send(f"Refreshed {count} uptime tracker message(s).", delete_after=10)

    @commands.command(name="removeuptime")
    async def remove_uptime_prefix(self, ctx: commands.Context) -> None:
        if self.bot.config.BOT_OWNER_ID and ctx.author.id != self.bot.config.BOT_OWNER_ID:
            return
        if self.bot.db is None:
            return
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        if ctx.guild:
            await self.bot.db.delete_tracked_message(str(ctx.guild.id))
            await ctx.send(
                "Removed the tracked uptime message for this guild.",
                delete_after=10,
            )

    @commands.command(name="uptime")
    async def uptime_prefix(self, ctx: commands.Context) -> None:
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        await self.send_uptime_response(
            lambda embed: ctx.send(embed=embed, delete_after=60),
            lambda text: ctx.send(text, delete_after=60),
            lambda embed, view: ctx.send(embed=embed, view=view, delete_after=60),
        )


async def setup(bot: "DiscordUptimeTrackerBot") -> None:
    await bot.add_cog(UptimeCog(bot))
