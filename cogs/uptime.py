import asyncio
import logging
from urllib.parse import urlparse
from datetime import datetime
from typing import TYPE_CHECKING, Any, Awaitable, Callable

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks


if TYPE_CHECKING:
    from bot import DiscordUptimeTrackerBot

from incidents import build_incident_messages, format_incident_history
from tracker_db import GUILD_SETTING_FIELDS

from ui.status_layout import AlertLayout, HostLayout, StatusLayout

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
StatusSender = Callable[[discord.ui.LayoutView], Awaitable[object]]
ErrorSender = Callable[[str], Awaitable[object]]
StatusViewSender = Callable[[discord.Embed, discord.ui.View], Awaitable[object]]
def _discord_relative(iso: str) -> str:
    """An ISO timestamp as Discord's relative stamp, or the raw text.

    Discord renders the reader's own timezone, which a preformatted string
    cannot do.
    """

    try:
        moment = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return iso
    return f"<t:{int(moment.timestamp())}:R>"


AlertChange = dict[str, str | int | float]

# Services whose transitions are not announced. Both forms are listed because a
# status source can rename a service without changing its id, or the reverse.
_ALERT_SUPPRESSED_NAMES = {
    "webstreamr",
    "webstreamer",
    "webstreamer mbg",
}
_ALERT_SUPPRESSED_IDS = {
    "webstreamr",
    "webstreamer",
    "webstreamr_mbg",
    "webstreamrmbg",
    "webstreamer_mbg",
}


def _alert_filter_name(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _alert_filter_id(value: object) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return "_".join(part for part in normalized.split("_") if part)


def is_alert_suppressed(service: dict[str, object]) -> bool:
    return (
        _alert_filter_name(service.get("name")) in _ALERT_SUPPRESSED_NAMES
        or _alert_filter_id(service.get("id")) in _ALERT_SUPPRESSED_IDS
    )


def is_alertable_transition(previous_state: object, current_state: object) -> bool:
    """Crossing the DOWN boundary, in either direction.

    DOWN is the state where the check got no answer; every other reported state
    means it answered. UNKNOWN is unmeasured and maintenance is planned, so
    neither is a verdict about availability on either side of the change.
    """

    previous = str(previous_state or "").strip().upper()
    current = str(current_state or "").strip().upper()
    if not previous or not current:
        return False
    if {previous, current} & {"UNKNOWN", "MAINTENANCE"}:
        return False
    return (previous == "DOWN") != (current == "DOWN")

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
    # default_permissions tells Discord the requirement, so a member without it
    # is not offered these at all. It does not replace can_manage_guild(): an
    # admin can override the default in Integrations, and the check is what
    # holds the line when they do.
    tracker = app_commands.Group(
        name="tracker",
        description="Manage uptime tracker messages",
        default_permissions=discord.Permissions(manage_guild=True),
        guild_only=True,
    )

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
            self.bot.add_view(
                StatusLayout(self, data, **await self.guild_render_settings(None))
            )

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

    async def fetch_service_detail(
        self,
        service_id: str,
        *,
        history: bool = True,
        timeline: bool = True,
        history_limit: int = 12,
    ) -> StatusData | None:
        """One service, with its check history and long-range buckets.

        The timeline is only computed for a single-service request, and both
        extras are off unless asked for, so `serviceId` is not optional here.
        """
        params = {"serviceId": service_id}
        if history:
            params["includeHistory"] = "1"
            params["historyLimit"] = str(history_limit)
        if timeline:
            params["includeTimeline"] = "1"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.status_api_url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as response:
                    if response.status != 200:
                        log.error(
                            "Failed to fetch detail for service %s: HTTP %s",
                            service_id,
                            response.status,
                        )
                        return None
                    payload = await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            log.error("Error fetching detail for service %s: %s", service_id, exc)
            return None
        services = payload.get("services") if isinstance(payload, dict) else None
        if not services:
            log.warning("No service returned for id %s", service_id)
            return None
        return services[0]

    def find_service(self, data: StatusData, needle: str) -> StatusData | None:
        needle = needle.strip().casefold()
        for service in self.visible_services(data):
            if needle in (str(service.get("id") or "").casefold(), str(service.get("name") or "").casefold()):
                return service
        return None

    def tracker_name(self, data: StatusData) -> str:
        source_name = str(data.get("source", {}).get("name") or "").strip()
        return source_name or self.bot.config.BRAND_NAME

    def active_outages(self, data: StatusData) -> list[StatusData]:
        """Services the payload currently reports as not responding.

        Read from the payload rather than the incident tables, so the panel is
        right on the first refresh after a restart and cannot drift from what
        the status page says.
        """

        down = [
            service
            for service in self.visible_services(data)
            if str((service.get("last") or {}).get("state") or "").upper() == "DOWN"
        ]
        # Longest outage first: the one that has been broken longest is the one
        # someone is most likely asking about.
        return sorted(down, key=lambda s: str(s.get("downSince") or "9999"))

    def outage_line(self, service: StatusData) -> str:
        name = str(service.get("name") or "Unknown Service")
        group = str(service.get("group") or "Other")
        since = str(service.get("downSince") or "")
        when = f" since {_discord_relative(since)}" if since else ""
        return f"🔴 **{name}** ({group}){when}"

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
            if not is_alertable_transition(previous_state, current_state):
                continue
            if is_alert_suppressed(service):
                continue
            changes.append(
                {
                    "key": key,
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

    def group_summary_line(
        self,
        name: str,
        services: list[StatusData],
        healthy: str | None = None,
    ) -> str:
        group_up = sum(1 for item in services if item.get("last", {}).get("state") == "UP")
        group_total = len(services)
        affected = group_total - group_up
        group_emoji = self.get_state_emoji("UP", healthy) if affected == 0 else "🔴"
        noun = "service" if affected == 1 else "services"
        status_text = "operational" if affected == 0 else f"{affected} {noun} affected"
        if any(item.get("requiresAuth") for item in services):
            name = f"{name} 🔒"
        return f"{group_emoji} **{name}** · {group_up}/{group_total}, {status_text}"

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


    async def process_status_alerts(self, data: StatusData) -> int:
        if self.bot.db is None:
            return 0
        current_states = self.service_state_map(data)
        previous_states = await self.bot.db.get_service_states()
        await self.bot.db.replace_service_states(current_states)
        if not previous_states:
            return 0
        changes = self.collect_status_changes(previous_states, data)
        messages = await build_incident_messages(
            self.bot.db, changes, present_keys=set(current_states)
        )
        if not messages:
            return 0
        alert_channels = await self.bot.db.list_alert_channels()
        if not alert_channels:
            return 0
        sent = 0
        for item in alert_channels:
            settings = await self.guild_render_settings(item.get("guild_id"))
            channel = await self.resolve_tracker_channel(int(item["channel_id"]))
            if channel is None:
                continue
            for heading, group in messages:
                layout = AlertLayout(self, data, group, heading=heading, **settings)
                try:
                    await channel.send(view=layout)
                    sent += 1
                except discord.HTTPException as exc:
                    log.error(
                        "Failed to send alert in channel %s: %s",
                        item["channel_id"],
                        exc,
                    )
        return sent

    async def _replace_tracker_message(
        self,
        channel: discord.abc.Messageable,
        message: discord.Message,
        layout: "StatusLayout",
        guild_id: str,
        channel_id: int,
    ) -> None:
        new_message = await channel.send(view=layout)
        await self.bot.db.upsert_tracked_message(
            guild_id,
            str(channel_id),
            str(new_message.id),
        )
        log.info(
            "Replaced the embed tracker message in channel %s with a components message",
            channel_id,
        )
        try:
            await message.delete()
        except discord.HTTPException as exc:
            log.warning(
                "Could not delete the old tracker message in channel %s: %s",
                channel_id,
                exc,
            )

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
            layout = StatusLayout(self, data, **settings)
            channel_id = int(item["channel_id"])
            message_id = int(item["message_id"])
            channel = await self.resolve_tracker_channel(channel_id)
            if channel is None:
                continue
            try:
                message = await channel.fetch_message(message_id)
                if message.flags.components_v2:
                    await message.edit(view=layout)
                else:
                    # Discord will not let the Components V2 flag be added to a
                    # message that was sent without it, so an embed-era tracker
                    # is replaced rather than edited.
                    await self._replace_tracker_message(
                        channel, message, layout, guild_id, channel_id
                    )
                updated += 1
            except discord.NotFound:
                new_message = await channel.send(view=layout)
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
        send_view: StatusSender,
        send_error: ErrorSender,
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
        if not self.group_services(data):
            await send_error("No services were found.")
            return
        layout = StatusLayout(
            self, data, **await self.guild_render_settings(guild_id)
        )
        await send_view(layout)

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
        layout = StatusLayout(self, data, **settings)
        message = await interaction.channel.send(view=layout)
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
    @app_commands.checks.cooldown(1, 60.0, key=lambda i: i.guild_id)
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

    async def _status_data(self) -> StatusData | None:
        data = self.last_status
        if data is None:
            data = await self.fetch_status()
            if data:
                self.last_status = data
        return data

    async def group_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        data = await self._status_data()
        if not data:
            return []
        needle = current.casefold()
        return [
            app_commands.Choice(name=name[:100], value=name[:100])
            for name in self.group_services(data)
            if needle in name.casefold()
        ][:25]

    async def host_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        data = await self._status_data()
        if not data:
            return []
        needle = current.casefold()
        return [
            app_commands.Choice(
                name=str(service.get("name") or "?")[:100],
                value=str(service.get("id") or service.get("name") or "")[:100],
            )
            for service in self.visible_services(data)
            if needle in str(service.get("name") or "").casefold()
        ][:25]

    @app_commands.command(name="status", description="Service status, by group or by host")
    @app_commands.describe(
        group="Show one group's services",
        host="Show one service in detail, with its uptime history",
        state="List every service currently in this state",
    )
    @app_commands.choices(
        state=[
            app_commands.Choice(name="Down", value="DOWN"),
            app_commands.Choice(name="Degraded", value="DEGRADED"),
            app_commands.Choice(name="Down or degraded", value="DOWN,DEGRADED"),
        ]
    )
    @app_commands.autocomplete(group=group_autocomplete, host=host_autocomplete)
    async def status_slash(
        self,
        interaction: discord.Interaction,
        group: str | None = None,
        host: str | None = None,
        state: app_commands.Choice[str] | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        data = await self._status_data()
        if not data:
            await interaction.followup.send(
                "I could not fetch status data right now.",
                ephemeral=True,
            )
            return
        settings = await self.guild_render_settings(interaction.guild_id)
        if host:
            service = self.find_service(data, host)
            if service is None:
                await interaction.followup.send(
                    f"I could not find a service called {host}.",
                    ephemeral=True,
                )
                return
            detail = await self.fetch_service_detail(str(service["id"]))
            layout = HostLayout(self, detail or service, **settings)
            await interaction.followup.send(view=layout, ephemeral=True)
            return
        if group and group not in self.group_services(data):
            await interaction.followup.send(
                f"I could not find a group called {group}.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            view=StatusLayout(
                self,
                data,
                group_name=group,
                states=tuple(state.value.split(",")) if state else (),
                **settings,
            ),
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

    # Read-only and ephemeral, so it sits beside /uptime rather than inside the
    # manager-gated group: an outage is what an ordinary member wants to look up.
    @app_commands.command(name="incidents", description="Recent outages and who they affected")
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: i.guild_id)
    async def incidents_slash(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if self.bot.db is None:
            await interaction.followup.send("No incident history is available.", ephemeral=True)
            return
        incidents = await self.bot.db.list_recent_incidents_with_services(10)
        lines = format_incident_history(incidents)
        await interaction.followup.send(
            "## Recent incidents\n" + "\n".join(lines),
            ephemeral=True,
        )

    @app_commands.command(name="uptime", description="View live service uptime")
    async def uptime_slash(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await self.send_uptime_response(
            lambda view: interaction.followup.send(view=view, ephemeral=True),
            lambda text: interaction.followup.send(text, ephemeral=True),
            guild_id=interaction.guild_id,
        )


async def setup(bot: "DiscordUptimeTrackerBot") -> None:
    await bot.add_cog(UptimeCog(bot))
