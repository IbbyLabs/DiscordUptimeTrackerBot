from typing import TYPE_CHECKING, Any

import discord
from discord import ui

if TYPE_CHECKING:
    from bot import DiscordUptimeTrackerBot
    from cogs.uptime import UptimeCog

ACCENT = 0x5A189A
# A Components V2 message allows 40 components and 4000 display characters.
# Group lines go in one text display rather than one each, which is what keeps
# a 19-group board inside both.
MAX_CHARS = 4000
SELECT_OPTION_LIMIT = 25


CHUNK_CHARS = 1000
MAX_BODY_CHUNKS = 3


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _body_chunks(lines: list[str]) -> tuple[list[str], int]:
    """Whole lines packed into text displays, plus how many did not fit.

    Splitting beats trimming: a trimmed board looks complete while a service is
    missing from it. The caller renders the dropped count so the gap is visible.
    """
    chunks: list[str] = []
    current: list[str] = []
    length = 0
    for index, line in enumerate(lines):
        if current and length + len(line) + 1 > CHUNK_CHARS:
            chunks.append("\n".join(current))
            if len(chunks) == MAX_BODY_CHUNKS:
                return chunks, len(lines) - index
            current, length = [], 0
        current.append(line)
        length += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks, 0


class GroupSelect(ui.Select["StatusLayout"]):
    def __init__(self, cog: "UptimeCog", data: dict[str, Any], current: str | None) -> None:
        groups = list(cog.group_services(data).keys())
        options = [
            discord.SelectOption(
                label=_truncate(name, 100),
                value=name[:100],
                default=name == current,
            )
            for name in groups[:SELECT_OPTION_LIMIT]
        ]
        super().__init__(
            placeholder="Pick a group for the detail view",
            options=options,
            custom_id="uptime_group_select",
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction) -> None:
        data = self.cog.last_status or await self.cog.fetch_status()
        if not data:
            await interaction.response.send_message(
                "I could not fetch status data right now.",
                ephemeral=True,
            )
            return
        group_name = self.values[0]
        settings = await self.cog.guild_render_settings(interaction.guild_id)
        layout = StatusLayout(self.cog, data, group_name=group_name, **settings)
        await interaction.response.send_message(view=layout, ephemeral=True)


class StatusLayout(ui.LayoutView):
    """The status board as Components V2.

    `group_name` picks the detail view for one group; without it the board is
    the summary every group gets one line of.
    """

    def __init__(
        self,
        cog: "UptimeCog",
        data: dict[str, Any],
        *,
        healthy: str | None = None,
        page_url: str | None = None,
        group_name: str | None = None,
    ) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.data = data
        page_url = page_url or cog.bot.config.STATUS_PAGE_URL
        groups = cog.group_services(data)

        header = f"## {cog.tracker_name(data)}"
        up, down, degraded = cog._summary_counts(data)
        headline = (
            f"### {cog.get_status_text(cog.visible_services(data), healthy)}\n"
            f"**Up:** {up} | **Down:** {down} | **Degraded:** {degraded}"
        )

        if group_name is None:
            lines = [
                cog.group_summary_line(name, items, healthy)
                for name, items in groups.items()
            ]
        else:
            items = groups.get(group_name, [])
            has_auth = any(item.get("requiresAuth") for item in items)
            lines = [f"**{group_name}**"] + cog._detail_lines(
                items, has_auth, healthy, page_url
            )

        chunks, dropped = _body_chunks(lines)
        updated = f"-# Last updated <t:{cog.last_updated_unix(data)}:R>"
        if dropped:
            updated = f"-# {dropped} more not shown here\n{updated}"

        container = ui.Container(
            ui.TextDisplay(header),
            ui.TextDisplay(headline),
            ui.Separator(),
            *(ui.TextDisplay(chunk) for chunk in chunks),
            ui.Separator(),
            ui.TextDisplay(updated),
            accent_colour=ACCENT,
        )
        self.add_item(container)
        if groups:
            self.add_item(ui.ActionRow(GroupSelect(cog, data, group_name)))
        self.add_item(
            ui.ActionRow(ui.Button(label="Full Status Page", url=page_url))
        )


class AlertLayout(ui.LayoutView):
    """A status change notification as Components V2."""

    def __init__(
        self,
        cog: "UptimeCog",
        data: dict[str, Any],
        changes: list[dict[str, Any]],
        *,
        healthy: str | None = None,
        page_url: str | None = None,
    ) -> None:
        super().__init__(timeout=None)
        page_url = page_url or cog.bot.config.STATUS_PAGE_URL
        count = len(changes)
        noun = "service" if count == 1 else "services"
        lines = [
            f"{cog.get_state_emoji(str(c['state']), healthy)} **{c['name']}** "
            f"({c['group']}): {c['previous_state']} → {c['state']}, "
            f"{int(c['latency'])}ms, {float(c['uptime_percent']):.1f}% uptime"
            for c in changes
        ]
        chunks, dropped = _body_chunks(lines)
        footer = f"-# {dropped} more not shown here" if dropped else None
        children: list[ui.Item[Any]] = [
            ui.TextDisplay(f"## Status Alerts\nDetected {count} status change for {noun}."),
            ui.Separator(),
            *(ui.TextDisplay(chunk) for chunk in chunks),
        ]
        if footer:
            children.append(ui.TextDisplay(footer))
        self.add_item(ui.Container(*children, accent_colour=cog.alert_color(changes)))
        self.add_item(ui.ActionRow(ui.Button(label="Full Status Page", url=page_url)))
