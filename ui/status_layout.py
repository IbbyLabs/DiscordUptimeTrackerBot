from typing import TYPE_CHECKING, Any

import discord
from discord import ui

import status_api
from i18n import Translator, translator_for

if TYPE_CHECKING:
    from bot import DiscordUptimeTrackerBot
    from cogs.uptime import UptimeCog

ACCENT = 0x5A189A
# A Components V2 message allows 40 components and 4000 display characters.
# Group lines go in one text display rather than one each, which is what keeps
# a 19-group board inside both.
MAX_CHARS = 4000
SELECT_OPTION_LIMIT = 25


# Redirects rather than the destinations, so reissuing a link is one change
# here rather than an edit everywhere it has been pasted.
BRAND_SITE_URL = "https://ibbylabs.dev"
KOFI_URL = "https://kofi.ibbylabs.dev"
COMMUNITY_URL = "https://discord.ibbylabs.dev"
DM_URL = "https://dm.ibbylabs.dev"
SOURCE_URL = "https://github.com/IbbyLabs/DiscordUptimeTrackerBot"

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
    def __init__(
        self,
        cog: "UptimeCog",
        data: dict[str, Any],
        current: str | None,
        translate: Translator | None = None,
    ) -> None:
        _ = translate or translator_for(None)
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
            placeholder=_("Pick a group for the detail view"),
            options=options,
            custom_id="uptime_group_select",
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction) -> None:
        data = self.cog.last_status or await self.cog.fetch_status()
        settings = await self.cog.guild_render_settings(interaction.guild_id)
        _ = settings["translate"]
        if not data:
            await interaction.response.send_message(
                _("I could not fetch status data right now."),
                ephemeral=True,
            )
            return
        group_name = self.values[0]
        layout = StatusLayout(self.cog, data, group_name=group_name, **settings)
        await interaction.response.send_message(view=layout, ephemeral=True)


def _with_outages(
    cog: "UptimeCog", data: dict[str, Any], lines: list[str], translate: Translator
) -> list[str]:
    """Put what is broken above the group summary.

    A reader opening the board during an outage is looking for the broken
    service, not for the group it sits in.
    """

    outages = cog.active_outages(data)
    if not outages:
        return lines
    # The same split the panel makes: a service in the recovery hold is
    # answering, so it is not counted among things that are not responding.
    recovering = len(cog.recovering_services(data))
    not_responding = len(outages) - recovering
    _ = translate
    parts = []
    if not_responding:
        parts.append(
            _.ngettext(
                "{count} service not responding",
                "{count} services not responding",
                not_responding,
            ).format(count=not_responding)
        )
    if recovering:
        parts.append(_("{count} recovering").format(count=recovering))
    return [
        _("**Active outages** — {summary}").format(summary=" · ".join(parts)),
        *(cog.outage_line(service) for service in outages),
        "",
        *lines,
    ]


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
        translate: Translator | None = None,
    ) -> None:
        super().__init__(timeout=None)
        self._ = translate or translator_for(None)
        self.cog = cog
        self.data = data
        page_url = page_url or cog.bot.config.STATUS_PAGE_URL
        groups = cog.group_services(data)

        header = f"## {cog.tracker_name(data)}"
        if states:
            header += "\n-# " + self._("Filtered to {states}").format(
                states=", ".join(st.lower() for st in states)
            )
        up, down, degraded, unstable = cog.headline_counts(data)
        # One sentence rather than four fragments: the separator and the order
        # of label and number are the translator's to choose.
        counts = self._(
            "**Up:** {up} | **Down:** {down} | **Degraded:** {degraded}"
            " | **Unstable:** {unstable}"
        ).format(up=up, down=down, degraded=degraded, unstable=unstable)
        headline = (
            f"### {cog.get_status_text(cog.visible_services(data), healthy, data)}\n"
            f"{counts}"
        )

        if states:
            wanted = {state.upper() for state in states}
            matched = [
                service
                for service in cog.visible_services(data)
                if status_api.service_state(service) in wanted
            ]
            if matched:
                lines = cog._detail_lines(matched, False, healthy, page_url)
            else:
                lines = [self._("Nothing in that state right now.")]
        elif group_name is None:
            lines = [
                cog.group_summary_line(name, items, healthy, cog.published_group_state(data, name))
                for name, items in groups.items()
            ]
            lines = _with_outages(cog, data, lines, self._)
            # Above everything the board derives: the operator wrote it because
            # a state cannot say it.
            bulletin = cog.bulletin(data)
            if bulletin:
                lines = [*cog.bulletin_lines(bulletin), "", *lines]
        else:
            items = groups.get(group_name, [])
            has_auth = any(item.get("requiresAuth") for item in items)
            lines = [f"**{group_name}**"] + cog._detail_lines(
                items, has_auth, healthy, page_url
            )

        chunks, dropped = _body_chunks(lines)
        generated = cog.last_updated_unix(data)
        updated = (
            "-# " + self._("Last updated {when}").format(when=f"<t:{generated}:R>")
            if generated is not None
            else "-# " + self._("The status page did not say when this was generated")
        )
        # Above the credit rather than buried: a board that stopped updating
        # reads as current, which is the failure this exists to prevent.
        stale = cog.staleness_line(data)
        if stale:
            updated = f"{stale}\n{updated}"
        if dropped:
            more = self._.ngettext(
                "{count} more not shown here",
                "{count} more not shown here",
                dropped,
            ).format(count=dropped)
            updated = f"-# {more}\n{updated}"
        # Credit only. A board sits in a channel permanently, so anything that
        # does not change does not belong on it; the links live in /about.
        # The name is a brand and stays put; only the words around it move.
        credit = self._("Developed by {brand}").format(brand="IbbyLabs")
        updated = f"{updated}\n-# {credit} • v{cog.bot.version}"

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
            self.add_item(
                ui.ActionRow(GroupSelect(cog, data, group_name, self._))
            )
        self.add_item(
            ui.ActionRow(ui.Button(label=self._("Full Status Page"), url=page_url))
        )


class PanelLayout(ui.LayoutView):
    """One persistent panel, kept current in the alert channel.

    Chunked like the board, because a panel grows with the estate and a message
    that outgrows the limit fails rather than shortening.
    """

    def __init__(
        self,
        cog: "UptimeCog",
        heading: str,
        lines: list[str],
        accent: int,
        *,
        healthy: str | None = None,
        page_url: str | None = None,
        live_url: str | None = None,
        translate: Translator | None = None,
    ) -> None:
        super().__init__(timeout=None)
        self._ = translate or translator_for(None)
        del healthy
        page_url = page_url or cog.bot.config.STATUS_PAGE_URL
        chunks, dropped = _body_chunks(lines)
        children: list[ui.Item[Any]] = [
            ui.TextDisplay(heading),
            ui.Separator(),
            *(ui.TextDisplay(chunk) for chunk in chunks),
        ]
        if dropped:
            more = self._.ngettext(
                "{count} more not shown here",
                "{count} more not shown here",
                dropped,
            ).format(count=dropped)
            children.append(ui.TextDisplay(f"-# {more}"))
        # An alert is one moment; the panels are the current picture. Omitted
        # when there is no panel to point at rather than rendering a dead link.
        if live_url:
            children.append(
                ui.TextDisplay(
                    "-# " + self._("Live status: [pinned panels]({url})").format(url=live_url)
                )
            )
        credit = self._("Developed by {brand}").format(brand="IbbyLabs")
        children.append(ui.TextDisplay(f"-# {credit} • v{cog.bot.version}"))
        self.add_item(ui.Container(*children, accent_colour=accent))
        self.add_item(
            ui.ActionRow(ui.Button(label=self._("Full Status Page"), url=page_url))
        )


class AboutLayout(ui.LayoutView):
    """Who made it, how to reach them, and how to run your own.

    Everything the board deliberately leaves off lives here: a member runs the
    command, so the links reach someone who asked for them rather than everyone
    who can see a pinned message.
    """

    def __init__(
        self,
        cog: "UptimeCog",
        *,
        healthy: str | None = None,
        page_url: str | None = None,
        translate: Translator | None = None,
    ) -> None:
        super().__init__(timeout=None)
        self._ = translate or translator_for(None)
        version = cog.bot.version
        marker = cog.get_state_emoji("UP", healthy)
        page_url = page_url or cog.bot.config.STATUS_PAGE_URL
        self.add_item(
            ui.Container(
                ui.TextDisplay(
                    f"## {marker} " + self._("Uptime Tracker") + "\n"
                    + self._(
                        "A live status board for Stremio addons, developed by {brand}."
                    ).format(brand="IbbyLabs")
                ),
                ui.Separator(),
                ui.TextDisplay(
                    self._("**Version**\n`v{version}`").format(version=version)
                    + "\n\n"
                    + self._(
                        "**Source**\nOpen source under the MIT licence — run your own"
                        " instance from [GitHub]({url})."
                    ).format(url=SOURCE_URL)
                ),
                accent_colour=0x5865F2,
            )
        )
        self.add_item(
            ui.ActionRow(
                # IbbyLabs is a name and stays as it is. The rest are words.
                ui.Button(label=self._("Status Page"), url=page_url),
                ui.Button(label="IbbyLabs", url=BRAND_SITE_URL),
                ui.Button(label=self._("Support"), url=KOFI_URL),
                ui.Button(label=self._("Community"), url=COMMUNITY_URL),
                ui.Button(label=self._("Message Ibby"), url=DM_URL),
            )
        )


class IncidentHistoryLayout(ui.LayoutView):
    """Recent incidents as Components V2.

    Chunked like the board: a plain content string is capped at 2000 characters
    and ten incidents naming real services passes that, which fails the whole
    command rather than shortening it.
    """

    def __init__(
        self,
        cog: "UptimeCog",
        lines: list[str],
        *,
        healthy: str | None = None,
        page_url: str | None = None,
        translate: Translator | None = None,
    ) -> None:
        super().__init__(timeout=None)
        self._ = translate or translator_for(None)
        del healthy
        page_url = page_url or cog.bot.config.STATUS_PAGE_URL
        chunks, dropped = _body_chunks(lines)
        children: list[ui.Item[Any]] = [
            ui.TextDisplay("## " + self._("Recent incidents")),
            ui.Separator(),
            *(ui.TextDisplay(chunk) for chunk in chunks),
        ]
        if dropped:
            children.append(
                ui.TextDisplay(
                    "-# "
                    + self._.ngettext(
                        "{count} older not shown here",
                        "{count} older not shown here",
                        dropped,
                    ).format(count=dropped)
                )
            )
        self.add_item(ui.Container(*children, accent_colour=0x5865F2))
        self.add_item(
            ui.ActionRow(ui.Button(label=self._("Full Status Page"), url=page_url))
        )


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


def _state_word(state: str, translate: Translator) -> str:
    """The display state as a reader sees it. An unlisted state passes through."""
    _ = translate
    return {
        "UP": _("Up"),
        "DOWN": _("Down"),
        "DEGRADED": _("Degraded"),
        "RECOVERING": _("Recovering"),
        "MAINTENANCE": _("Maintenance"),
        "UNKNOWN": _("Unknown"),
    }.get(state.upper(), state.title())


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
        settings = await view.cog.guild_render_settings(interaction.guild_id)
        _ = settings["translate"]
        if detail is None:
            await interaction.followup.send(
                _("I could not fetch that service right now."),
                ephemeral=True,
            )
            return
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
        translate: Translator | None = None,
    ) -> None:
        super().__init__(timeout=None)
        self._ = translate or translator_for(None)
        self.cog = cog
        page_url = page_url or cog.bot.config.STATUS_PAGE_URL
        last = service.get("last") or {}
        state = status_api.display_state(service)
        name = str(service.get("name") or self._("Unknown service"))
        if service.get("requiresAuth"):
            name = f"{name} 🔒"
        service_id = str(service.get("id") or "")

        head = [f"## {cog.get_state_emoji(state, healthy)} {name}"]
        group = service.get("group")
        if group:
            head.append(f"-# {group}")

        facts = [
            self._("**State** · {state}").format(
                state=_state_word(state, self._)
            )
        ]
        if last.get("status"):
            facts.append(
                self._("**HTTP** · {status}").format(status=last["status"])
            )
        if last.get("latency"):
            facts.append(
                self._("**Latency** · {ms}ms").format(ms=int(last["latency"]))
            )
        since = service.get("downSince") if state != "UP" else service.get("upSince")
        if since:
            facts.append(
                self._("**Since** · {when}").format(when=_discord_time(since))
            )
        detail_line = " | ".join(facts)

        notes = []
        if last.get("error"):
            notes.append(f"⚠️ {str(last['error'])[:200]}")
        if last.get("degradedReason"):
            notes.append(f"⚠️ {last['degradedReason']}")
        if last.get("flapping"):
            notes.append(self._("⚠️ Flapping between states"))
        if last.get("recovering"):
            notes.append(self._("Recovering"))
        if service.get("maintenance"):
            notes.append(self._("🔧 Under maintenance"))

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
                    WindowButton(self._("7 days"), "d7", window, service_id),
                    WindowButton(self._("30 days"), "d30", window, service_id),
                    WindowButton(
                        self._("Recent checks"), "recent", window, service_id
                    ),
                )
            )
        self.add_item(
            ui.ActionRow(ui.Button(label=self._("Full Status Page"), url=page_url))
        )

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
