import asyncio
import logging
from urllib.parse import urlparse
from datetime import datetime
from typing import TYPE_CHECKING, Any, Awaitable, Callable

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from ui.status_views import StatusDashboardView, StatusPaginationView

if TYPE_CHECKING:
    from bot import DiscordUptimeTrackerBot

from tracker_db import GUILD_SETTING_FIELDS

log = logging.getLogger("uptimebot.cogs.uptime")

# Per-guild field -> the config attribute it inherits from when unset.
_SETTING_DEFAULTS = {
    "status_emoji": "STATUS_EMOJI",
    "status_page_url": "STATUS_PAGE_URL",
}

_SETTING_LABELS = {
    "status_emoji": "Status emoji",
    "status_page_url": "Status page URL",
}


def validate_guild_setting(field: str, value: str) -> tuple[str | None, str | None]:
    """Returns (cleaned, error). A bad URL would break every embed for the guild."""
    value = value.strip()
    if field == "status_page_url":
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return None, "That is not a valid URL. It needs to start with http:// or https://."
        if len(value) > 500:
            return None, "That URL is too long."
        return value, None
    if field == "status_emoji":
        if len(value) > 64:
            return None, "That emoji is too long."
        return value, None
    return None, f"Unknown setting: {field}"

StatusData = dict[str, Any]
StatusSender = Callable[[discord.Embed], Awaitable[object]]
ErrorSender = Callable[[str], Awaitable[object]]
StatusViewSender = Callable[[discord.Embed, discord.ui.View], Awaitable[object]]
AlertChange = dict[str, str | int | float]
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


def can_manage_guild():
    """Whoever administers this server, plus the instance owner.

    Every `/tracker` command configures one guild, so gating them on a single
    BOT_OWNER_ID locks out every server but the operator's. The owner stays
    permitted so a self-hosted single-guild install behaves as it did.
    """

    def predicate(interaction: discord.Interaction) -> bool:
        config = getattr(interaction.client, "config", None)
        owner_id = getattr(config, "BOT_OWNER_ID", None) if config else None
        if owner_id is not None and interaction.user.id == owner_id:
            return True
        perms = getattr(interaction.user, "guild_permissions", None)
        return bool(perms and perms.manage_guild)

    return app_commands.check(predicate)


class UptimeCog(commands.Cog):
    tracker = app_commands.Group(name="tracker", description="Manage uptime tracker messages")

    def __init__(self, bot: "DiscordUptimeTrackerBot") -> None:
        self.bot = bot
        self.status_api_url = bot.config.STATUS_API_URL
        # Last successful cycle. Read paths serve this rather than fetching, so
        # command traffic does not reach the status API at all.
        self.last_status: StatusData | None = None
        self._settings_cache: dict[str, dict[str, Any]] = {}

    async def guild_setting(self, guild_id: int | str | None, field: str) -> Any:
        """A guild's override for `field`, or the instance default.

        A guild with no row, or a NULL column, inherits. That keeps an
        untouched install behaving exactly as it does today.
        """
        default = getattr(self.bot.config, _SETTING_DEFAULTS[field])
        if guild_id is None:
            return default
        key = str(guild_id)
        row = self._settings_cache.get(key)
        if row is None:
            row = await self.bot.db.get_guild_settings(key) or {}
            self._settings_cache[key] = row
        value = row.get(field)
        return default if value is None else value

    async def guild_render_settings(self, guild_id: int | str | None) -> dict[str, Any]:
        """Every per-guild value the embed builders take, as keyword arguments.

        Call sites spread `**` this rather than naming each setting, so adding
        one reaches every render without touching them.
        """
        return {
            "healthy": await self.guild_setting(guild_id, "status_emoji"),
            "page_url": await self.guild_setting(guild_id, "status_page_url"),
        }

    def invalidate_guild_settings(self, guild_id: int | str) -> None:
        self._settings_cache.pop(str(guild_id), None)

    async def cog_load(self) -> None:
        self.refresh_status_task.change_interval(minutes=self.bot.config.REFRESH_MINUTES)
        self.refresh_status_task.start()
        data = await self.fetch_status()
        if data:
            self.last_status = data
            self.bot.add_view(StatusDashboardView(self.bot, self, data))

    async def cog_unload(self) -> None:
        self.refresh_status_task.cancel()

    @tasks.loop(minutes=10.0)
    async def refresh_status_task(self) -> None:
        await self.bot.wait_until_ready()
        await self.run_status_cycle()

    async def run_status_cycle(self) -> tuple[int, int]:
        data = await self.fetch_status()
        if not data:
            return 0, 0
        self.last_status = data
        alerts_sent = await self.process_status_alerts(data)
        updated = await self.update_tracked_messages(data)
        return updated, alerts_sent

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

    def get_state_emoji(self, state: str, healthy: str | None = None) -> str:
        healthy = healthy or self.bot.config.STATUS_EMOJI
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

    def get_status_text(self, services: list[StatusData], healthy: str | None = None) -> str:
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
        return f"{self.get_state_emoji('UP', healthy)} All Systems Operational"

    def get_uptime_bar(self, percent: float) -> str:
        filled = max(0, min(10, round(percent / 10)))
        return "█" * filled + "░" * (10 - filled)

    def service_key(self, service: StatusData) -> str:
        group_name = str(service.get("group") or "Other").strip()
        service_name = str(service.get("name") or "Unknown Service").strip()
        service_url = str(service.get("url") or "").strip()
        return "|".join((group_name, service_name, service_url))

    def service_state_map(self, data: StatusData) -> dict[str, str]:
        return {
            self.service_key(service): str(service.get("last", {}).get("state") or "UNKNOWN")
            for service in self.visible_services(data)
        }

    def collect_status_changes(
        self,
        previous_states: dict[str, str],
        data: StatusData,
    ) -> list[AlertChange]:
        changes: list[AlertChange] = []
        for service in self.visible_services(data):
            key = self.service_key(service)
            current_state = str(service.get("last", {}).get("state") or "UNKNOWN")
            previous_state = previous_states.get(key)
            if previous_state is None or previous_state == current_state:
                continue
            changes.append(
                {
                    "group": str(service.get("group") or "Other"),
                    "name": str(service.get("name") or "Unknown Service"),
                    "state": current_state,
                    "previous_state": previous_state,
                    "latency": int(service.get("last", {}).get("latency") or 0),
                    "uptime_percent": float(service.get("uptimePercent") or 0),
                }
            )
        return changes

    def alert_color(self, changes: list[AlertChange]) -> int:
        priority = {
            "DOWN": 4,
            "DEGRADED": 3,
            "MAINTENANCE": 2,
            "UNKNOWN": 1,
            "UP": 0,
        }
        highest = max(priority.get(str(change["state"]), 0) for change in changes)
        if highest >= 4:
            return 0xD90429
        if highest >= 3:
            return 0xF77F00
        if highest >= 2:
            return 0xF4A261
        return 0x2A9D8F

    def create_alert_embed(
        self,
        data: StatusData,
        changes: list[AlertChange],
        healthy: str | None = None,
        page_url: str | None = None,
    ) -> discord.Embed:
        page_url = page_url or self.bot.config.STATUS_PAGE_URL
        tracker_name = self.tracker_name(data)
        change_count = len(changes)
        noun = "service" if change_count == 1 else "services"
        embed = discord.Embed(
            title="Status Alerts",
            description=(
                f"Detected {change_count} status change for {noun}.\n\n"
                f"View the full status page: {page_url}"
            ),
            color=self.alert_color(changes),
            url=page_url,
        )
        for change in changes[:25]:
            name = str(change["name"])
            group = str(change["group"])
            current_state = str(change["state"])
            previous_state = str(change["previous_state"])
            latency = int(change["latency"])
            uptime_percent = float(change["uptime_percent"])
            embed.add_field(
                name=f"{self.get_state_emoji(current_state, healthy)} {name}",
                value=(
                    f"Group: {group}\n"
                    f"State: {previous_state} -> {current_state}\n"
                    f"Latency: {latency}ms\n"
                    f"Uptime: {uptime_percent:.1f}%"
                ),
                inline=False,
            )
        if change_count > 25:
            embed.set_footer(text=f"Showing 25 of {change_count} status changes")
        else:
            embed.set_footer(text="Owned, created, and maintained by Ibby")
        if self.bot.user and self.bot.user.display_avatar:
            embed.set_author(
                name=tracker_name,
                icon_url=self.bot.user.display_avatar.url,
                url=page_url,
            )
        return embed

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
        if page_info:
            return f"Page {page_info[0]}/{page_info[1]}"
        return ""

    def _embed_description(
        self,
        data: StatusData,
        services: list[StatusData],
        healthy: str | None = None,
        summary_mode: bool = False,
        page_url: str | None = None,
    ) -> str:
        up_count, down_count, degraded_count = self._summary_counts(data)
        # The author line already names the tracker. The tagline is for a
        # one-off /uptime; the tracker message re-renders every couple of
        # minutes and carries it forever.
        intro = "" if summary_mode else f"{self.bot.config.BRAND_DESCRIPTION}\n\n"
        return (
            f"{intro}"
            f"You can view the full status page at: "
            f"**{page_url or self.bot.config.STATUS_PAGE_URL}**\n\n"
            f"### {self.get_status_text(services, healthy)}\n"
            f"**Up:** {up_count} | **Down:** {down_count} | "
            f"**Degraded:** {degraded_count}"
        )

    async def resolve_tracker_channel(
        self,
        channel_id: int,
    ) -> discord.abc.Messageable | None:
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.HTTPException:
                return None
        if not isinstance(channel, TRACKER_CHANNEL_TYPES):
            return None
        return channel

    def _summary_field_value(self, services: list[StatusData], healthy: str | None = None) -> str:
        group_up = sum(1 for item in services if item.get("last", {}).get("state") == "UP")
        group_total = len(services)
        affected = group_total - group_up
        group_emoji = self.get_state_emoji("UP", healthy) if affected == 0 else "🔴"
        noun = "Service" if affected == 1 else "Services"
        status_text = "Operational" if affected == 0 else f"{affected} {noun} Affected"
        return f"{group_emoji} {group_up}/{group_total} {status_text}"

    def _detail_lines(
        self,
        services: list[StatusData],
        has_auth: bool,
        healthy: str | None = None,
        page_url: str | None = None,
    ) -> list[str]:
        lines: list[str] = []
        if has_auth:
            lines.append("Some services are behind authentication and marked with a lock.")
        for service in services:
            last = service.get("last", {})
            state = str(last.get("state") or "UNKNOWN")
            latency = int(last.get("latency") or 0)
            uptime_percent = float(service.get("uptimePercent") or 0)
            url = str(service.get("url") or page_url or self.bot.config.STATUS_PAGE_URL)
            name = str(service.get("name") or "Unknown Service")
            if service.get("requiresAuth"):
                name = f"{name} 🔒"
            uptime_bar = self.get_uptime_bar(uptime_percent)
            lines.append(
                f"{self.get_state_emoji(state, healthy)} **[{name}]({url})**: "
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
        healthy: str | None = None,
        page_url: str | None = None,
    ) -> None:
        for group_name, group_items in self.group_services(data).items():
            has_auth = any(item.get("requiresAuth") for item in group_items)
            display_name = f"{group_name} 🔒" if has_auth else group_name
            if summary_mode:
                embed.add_field(
                    name=display_name,
                    value=self._summary_field_value(group_items, healthy),
                    inline=True,
                )
                continue
            for field_name, field_value in self._field_chunks(
                display_name,
                self._detail_lines(group_items, has_auth, healthy, page_url),
            ):
                embed.add_field(name=field_name, value=field_value, inline=False)

    def create_status_embed(
        self,
        data: StatusData,
        page_info: tuple[int, int] | None = None,
        summary_mode: bool = False,
        healthy: str | None = None,
        page_url: str | None = None,
    ) -> discord.Embed:
        page_url = page_url or self.bot.config.STATUS_PAGE_URL
        services = self.visible_services(data)
        description = (
            self._embed_description(data, services, healthy, summary_mode, page_url)
        )
        embed = discord.Embed(
            title=self._embed_title(data, page_info),
            description=description,
            color=0x5A189A,
            url=page_url,
        )
        self._add_group_fields(
            embed, data, summary_mode=summary_mode, healthy=healthy, page_url=page_url
        )
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
                url=page_url,
            )
        return embed

    async def process_status_alerts(self, data: StatusData) -> int:
        if self.bot.db is None:
            return 0
        current_states = self.service_state_map(data)
        previous_states = await self.bot.db.get_service_states()
        await self.bot.db.replace_service_states(current_states)
        if not previous_states:
            return 0
        changes = self.collect_status_changes(previous_states, data)
        if not changes:
            return 0
        alert_channels = await self.bot.db.list_alert_channels()
        if not alert_channels:
            return 0
        sent = 0
        for item in alert_channels:
            embed = self.create_alert_embed(
                data,
                changes,
                **await self.guild_render_settings(item.get("guild_id")),
            )
            channel = await self.resolve_tracker_channel(int(item["channel_id"]))
            if channel is None:
                continue
            try:
                await channel.send(embed=embed)
                sent += 1
            except discord.HTTPException as exc:
                log.error(
                    "Failed to send alert in channel %s: %s",
                    item["channel_id"],
                    exc,
                )
        return sent

    async def update_tracked_messages(self, data: StatusData | None = None) -> int:
        if self.bot.db is None:
            return 0
        tracked_messages = await self.bot.db.list_tracked_messages()
        if not tracked_messages:
            return 0
        if data is None:
            data = await self.fetch_status()
        if not data:
            return 0
        updated = 0
        for item in tracked_messages:
            guild_id = str(item["guild_id"])
            settings = await self.guild_render_settings(guild_id)
            view = StatusDashboardView(self.bot, self, data, page_url=settings["page_url"])
            embed = self.create_status_embed(data, summary_mode=True, **settings)
            channel_id = int(item["channel_id"])
            message_id = int(item["message_id"])
            channel = await self.resolve_tracker_channel(channel_id)
            if channel is None:
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

    def refresh_result_text(self, updated: int, alerts_sent: int) -> str:
        tracker_text = f"Refreshed {updated} uptime tracker message(s)."
        if alerts_sent == 0:
            return tracker_text
        return f"{tracker_text} Sent {alerts_sent} alert(s)."

    async def send_uptime_response(
        self,
        send_embed: StatusSender,
        send_error: ErrorSender,
        send_embed_with_view: StatusViewSender,
        guild_id: int | str | None = None,
    ) -> None:
        # Serve the last cycle rather than fetching. This path is per-user, so
        # fetching here scales with people; the cycle already holds data no
        # older than one refresh interval.
        data = self.last_status
        if data is None:
            data = await self.fetch_status()
            if data:
                self.last_status = data
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
            **await self.guild_render_settings(guild_id),
        )
        if len(view.group_names) > 1:
            await send_embed_with_view(embed, view)
            return
        await send_embed(embed)

    @tracker.command(name="setup", description="Create a live uptime tracker message")
    @can_manage_guild()
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
        settings = await self.guild_render_settings(interaction.guild_id)
        embed = self.create_status_embed(data, summary_mode=True, **settings)
        view = StatusDashboardView(self.bot, self, data, page_url=settings["page_url"])
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
    @can_manage_guild()
    async def refresh_tracker(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        count, alerts_sent = await self.run_status_cycle()
        await interaction.followup.send(
            self.refresh_result_text(count, alerts_sent),
            ephemeral=True,
        )

    @tracker.command(name="alerts", description="Send status alerts to this channel")
    @can_manage_guild()
    async def setup_alerts(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not interaction.channel or self.bot.db is None:
            await interaction.response.send_message(
                "Cannot use this command here.",
                ephemeral=True,
            )
            return
        channel_id = interaction.channel_id
        if channel_id is None:
            await interaction.response.send_message(
                "Cannot use this command here.",
                ephemeral=True,
            )
            return
        channel = await self.resolve_tracker_channel(channel_id)
        if channel is None:
            await interaction.response.send_message(
                "Cannot use this command here.",
                ephemeral=True,
            )
            return
        await self.bot.db.upsert_alert_channel(
            str(interaction.guild_id),
            str(channel_id),
        )
        await interaction.response.send_message(
            "Status alerts will be sent to this channel.",
            ephemeral=True,
        )

    @tracker.command(name="settings", description="Show this server's tracker settings")
    @can_manage_guild()
    async def show_settings(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or self.bot.db is None:
            await interaction.response.send_message(
                "Cannot use this command here.",
                ephemeral=True,
            )
            return
        row = await self.bot.db.get_guild_settings(str(interaction.guild_id)) or {}
        lines = []
        for field in GUILD_SETTING_FIELDS:
            label = _SETTING_LABELS[field]
            override = row.get(field)
            default = getattr(self.bot.config, _SETTING_DEFAULTS[field])
            if override is None:
                lines.append(f"**{label}**: {default} (default)")
            else:
                lines.append(f"**{label}**: {override}")
        await interaction.response.send_message(
            "\n".join(lines) + "\n\nChange one with `/tracker set`.",
            ephemeral=True,
        )

    @tracker.command(name="set", description="Change a tracker setting for this server")
    @app_commands.describe(
        field="Which setting to change",
        value="The new value. Leave this empty to go back to the default.",
    )
    @app_commands.choices(
        field=[
            app_commands.Choice(name="Status emoji", value="status_emoji"),
            app_commands.Choice(name="Status page URL", value="status_page_url"),
        ]
    )
    @can_manage_guild()
    async def set_setting(
        self,
        interaction: discord.Interaction,
        field: app_commands.Choice[str],
        value: str | None = None,
    ) -> None:
        if not interaction.guild or self.bot.db is None:
            await interaction.response.send_message(
                "Cannot use this command here.",
                ephemeral=True,
            )
            return
        guild_id = str(interaction.guild_id)
        label = _SETTING_LABELS[field.value]
        if value is None or not value.strip():
            await self.bot.db.set_guild_setting(guild_id, field.value, None)
            self.invalidate_guild_settings(guild_id)
            default = getattr(self.bot.config, _SETTING_DEFAULTS[field.value])
            await interaction.response.send_message(
                f"{label} is back to the default: {default}",
                ephemeral=True,
            )
            return
        cleaned, error = validate_guild_setting(field.value, value)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        await self.bot.db.set_guild_setting(guild_id, field.value, cleaned)
        self.invalidate_guild_settings(guild_id)
        await interaction.response.send_message(
            f"{label} is now {cleaned}. It applies from the next refresh.",
            ephemeral=True,
        )

    @tracker.command(name="stopalerts", description="Stop sending status alerts in this guild")
    @can_manage_guild()
    async def remove_alerts(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or self.bot.db is None:
            await interaction.response.send_message(
                "Cannot use this command here.",
                ephemeral=True,
            )
            return
        await self.bot.db.delete_alert_channel(str(interaction.guild_id))
        await interaction.response.send_message(
            "Status alerts are now disabled for this guild.",
            ephemeral=True,
        )

    @tracker.command(
        name="remove",
        description="Stop tracking the live uptime message for this guild",
    )
    @can_manage_guild()
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
            guild_id=interaction.guild_id,
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
        settings = await self.guild_render_settings(ctx.guild.id if ctx.guild else None)
        embed = self.create_status_embed(data, summary_mode=True, **settings)
        view = StatusDashboardView(self.bot, self, data, page_url=settings["page_url"])
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
        count, alerts_sent = await self.run_status_cycle()
        await ctx.send(self.refresh_result_text(count, alerts_sent), delete_after=10)

    @commands.command(name="setupalerts")
    async def setup_alerts_prefix(self, ctx: commands.Context) -> None:
        if self.bot.config.BOT_OWNER_ID and ctx.author.id != self.bot.config.BOT_OWNER_ID:
            return
        if self.bot.db is None or ctx.guild is None:
            return
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        await self.bot.db.upsert_alert_channel(str(ctx.guild.id), str(ctx.channel.id))
        await ctx.send("Status alerts will be sent to this channel.", delete_after=10)

    @commands.command(name="removealerts")
    async def remove_alerts_prefix(self, ctx: commands.Context) -> None:
        if self.bot.config.BOT_OWNER_ID and ctx.author.id != self.bot.config.BOT_OWNER_ID:
            return
        if self.bot.db is None or ctx.guild is None:
            return
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        await self.bot.db.delete_alert_channel(str(ctx.guild.id))
        await ctx.send("Status alerts are now disabled for this guild.", delete_after=10)

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
            guild_id=ctx.guild.id if ctx.guild else None,
        )


async def setup(bot: "DiscordUptimeTrackerBot") -> None:
    await bot.add_cog(UptimeCog(bot))
