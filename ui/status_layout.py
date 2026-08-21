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
        states: tuple[str, ...] = (),
    ) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.data = data
        page_url = page_url or cog.bot.config.STATUS_PAGE_URL
        groups = cog.group_services(data)

        header = f"## {cog.tracker_name(data)}"
        if states:
            header += f"\n-# Filtered to {', '.join(st.lower() for st in states)}"
        up, down, degraded = cog._summary_counts(data)
        headline = (
            f"### {cog.get_status_text(cog.visible_services(data), healthy)}\n"
            f"**Up:** {up} | **Down:** {down} | **Degraded:** {degraded}"
        )

        if states:
            wanted = {state.upper() for state in states}
            matched = [
                service
                for service in cog.visible_services(data)
                if str((service.get("last") or {}).get("state") or "") in wanted
            ]
            if matched:
                lines = cog._detail_lines(matched, False, healthy, page_url)
            else:
                lines = ["Nothing in that state right now."]
        elif group_name is None:
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


# The API returns 84 two-hour buckets for d7 and 90 eight-hour buckets for d30.
# Both are too wide to read on a phone, so they collapse to these widths.
TIMELINE_WIDTH = {"d7": 28, "d30": 30}
STATE_BLOCK = {"UP": "🟩", "DEGRADED": "🟨", "DOWN": "🟥"}
UNKNOWN_BLOCK = "⬛"
# Worst wins when buckets merge: a short outage inside a wider bar has to
# survive the collapse or the bar reports a clean week that was not one.
STATE_RANK = {"DOWN": 3, "DEGRADED": 2, "UP": 1}


def collapse_timeline(buckets: list[dict[str, Any]], width: int) -> str:
    if not buckets:
        return ""
    step = max(1, -(-len(buckets) // width))
    out = []
    for start in range(0, len(buckets), step):
        window = buckets[start : start + step]
        present = [b for b in window if not b.get("missing")]
        if not present:
            out.append(UNKNOWN_BLOCK)
            continue
        worst = max(
            (str(b.get("state") or "") for b in present),
            key=lambda state: STATE_RANK.get(state, 0),
        )
        out.append(STATE_BLOCK.get(worst, UNKNOWN_BLOCK))
    return "".join(out)


def _coverage_is_short(timeline: dict[str, Any]) -> bool:
    """True only when history is missing enough of the window to matter.

    `hasFullCoverage` goes false for a couple of minutes' shortfall, which is
    every window, so reporting it directly labels healthy data as incomplete.
    """
    from datetime import datetime

    def parse(value: Any) -> Any:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    start, end = parse(timeline.get("windowStart")), parse(timeline.get("windowEnd"))
    covered = parse(timeline.get("coverageStart"))
    if not (start and end and covered):
        return False
    span = (end - start).total_seconds()
    return span > 0 and (covered - start).total_seconds() / span > 0.05


def _period_counts(buckets: list[dict[str, Any]]) -> tuple[int, int]:
    """Periods that went down, and periods that only degraded.

    Kept apart because a bucket is DEGRADED when any single check in it was
    slow — three of forty-seven, in one real case — so counting the two
    together reports an outage on a service whose uptime is 100%.
    """
    down = sum(1 for b in buckets if str(b.get("state") or "") == "DOWN")
    degraded = sum(1 for b in buckets if str(b.get("state") or "") == "DEGRADED")
    return down, degraded


class WindowButton(ui.Button["HostLayout"]):
    def __init__(self, label: str, window: str, current: str, service_id: str) -> None:
        super().__init__(
            label=label,
            style=(
                discord.ButtonStyle.primary
                if window == current
                else discord.ButtonStyle.secondary
            ),
            custom_id=f"uptime_window_{window}_{service_id}"[:100],
            disabled=window == current,
        )
        self.window = window
        self.service_id = service_id

    async def callback(self, interaction: discord.Interaction) -> None:
        view: "HostLayout" = self.view  # type: ignore[assignment]
        await interaction.response.defer()
        detail = await view.cog.fetch_service_detail(self.service_id)
        if detail is None:
            await interaction.followup.send(
                "I could not fetch that service right now.", ephemeral=True
            )
            return
        settings = await view.cog.guild_render_settings(interaction.guild_id)
        await interaction.edit_original_response(
            view=HostLayout(view.cog, detail, window=self.window, **settings)
        )


class HostLayout(ui.LayoutView):
    """One service: its current state, uptime windows, and a collapsed timeline.

    `window` is d7, d30 or recent; recent lists the last checks instead of bars.
    """

    def __init__(
        self,
        cog: "UptimeCog",
        service: dict[str, Any],
        *,
        window: str = "d7",
        healthy: str | None = None,
        page_url: str | None = None,
    ) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        page_url = page_url or cog.bot.config.STATUS_PAGE_URL
        last = service.get("last") or {}
        state = str(last.get("state") or "UNKNOWN")
        name = str(service.get("name") or "Unknown service")
        if service.get("requiresAuth"):
            name = f"{name} 🔒"
        service_id = str(service.get("id") or "")

        head = [f"## {cog.get_state_emoji(state, healthy)} {name}"]
        group = service.get("group")
        if group:
            head.append(f"-# {group}")

        facts = [f"**State** · {state.title()}"]
        if last.get("status"):
            facts.append(f"**HTTP** · {last['status']}")
        if last.get("latency"):
            facts.append(f"**Latency** · {int(last['latency'])}ms")
        since = service.get("downSince") if state != "UP" else service.get("upSince")
        if since:
            facts.append(f"**Since** · {_discord_time(since)}")
        detail_line = " | ".join(facts)

        notes = []
        if last.get("error"):
            notes.append(f"⚠️ {str(last['error'])[:200]}")
        if last.get("degradedReason"):
            notes.append(f"⚠️ {last['degradedReason']}")
        if last.get("flapping"):
            notes.append("⚠️ Flapping between states")
        if last.get("recovering"):
            notes.append("Recovering")
        if service.get("maintenance"):
            notes.append("🔧 Under maintenance")

        windows = service.get("uptimeWindows") or {}
        uptime_line = " | ".join(
            f"**{label}** {float(windows[key]):.2f}%"
            for key, label in (
                ("h1", "1h"), ("h12", "12h"), ("h24", "24h"),
                ("d7", "7d"), ("d30", "30d"),
            )
            if key in windows
        )

        body, caption = self._window_body(service, window)

        children: list[ui.Item[Any]] = [ui.TextDisplay("\n".join(head))]
        children.append(ui.TextDisplay(detail_line))
        if notes:
            children.append(ui.TextDisplay("\n".join(notes)))
        if uptime_line:
            children.append(ui.Separator())
            children.append(ui.TextDisplay(uptime_line))
        if body:
            children.append(ui.Separator())
            children.append(ui.TextDisplay(f"{caption}\n{body}"))
        self.add_item(ui.Container(*children, accent_colour=ACCENT))

        if service_id:
            self.add_item(
                ui.ActionRow(
                    WindowButton("7 days", "d7", window, service_id),
                    WindowButton("30 days", "d30", window, service_id),
                    WindowButton("Recent checks", "recent", window, service_id),
                )
            )
        self.add_item(ui.ActionRow(ui.Button(label="Full Status Page", url=page_url)))

    def _window_body(self, service: dict[str, Any], window: str) -> tuple[str, str]:
        if window == "recent":
            checks = list(service.get("history") or [])[-10:]
            if not checks:
                return "", ""
            lines = [
                f"{STATE_BLOCK.get(str(c.get('state') or ''), UNKNOWN_BLOCK)} "
                f"{_discord_time(c.get('time'))} · {c.get('status') or '—'} · "
                f"{int(c.get('latency') or 0)}ms"
                for c in reversed(checks)
            ]
            return "\n".join(lines), f"**Last {len(lines)} checks**"
        timeline = (service.get("historyTimeline") or {}).get(window) or {}
        buckets = timeline.get("buckets") or []
        if not buckets:
            return "", ""
        bar = collapse_timeline(buckets, TIMELINE_WIDTH.get(window, 30))
        down, degraded = _period_counts(buckets)
        span = "7 days" if window == "d7" else "30 days"
        # Counts are of source periods, not of blocks drawn: each block merges
        # several, so the two numbers do not match and the wording says which.
        parts = [f"{len(buckets)} periods"]
        parts.append(f"{down} with an outage" if down else "no outages")
        if degraded:
            parts.append(f"{degraded} with slow or failed checks")
        if _coverage_is_short(timeline):
            parts.append("partial history")
        return bar, f"**Last {span}** · " + ", ".join(parts)


def _discord_time(value: Any) -> str:
    from datetime import datetime

    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return "—"
    return f"<t:{int(parsed.timestamp())}:R>"
