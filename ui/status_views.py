from typing import TYPE_CHECKING, Any

import discord
from discord import ui

if TYPE_CHECKING:
    from bot import DiscordUptimeTrackerBot
    from cogs.uptime import UptimeCog


class StatusPaginationView(ui.View):
    def __init__(
        self,
        bot: "DiscordUptimeTrackerBot",
        cog: "UptimeCog",
        data: dict[str, Any],
    ) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.cog = cog
        self.data = data
        self.groups = cog.group_services(data)
        self.group_names = list(self.groups.keys())
        self.current_page = 0
        self.total_pages = len(self.group_names)
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1
        self.page_indicator.label = f"Page {self.current_page + 1}/{max(self.total_pages, 1)}"

    @ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(
        self,
        interaction: discord.Interaction,
        _button: ui.Button,
    ) -> None:
        self.current_page -= 1
        await self._update_message(interaction)

    @ui.button(label="Page 1/1", style=discord.ButtonStyle.secondary, disabled=True)
    async def page_indicator(
        self,
        _interaction: discord.Interaction,
        _button: ui.Button,
    ) -> None:
        return

    @ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(
        self,
        interaction: discord.Interaction,
        _button: ui.Button,
    ) -> None:
        self.current_page += 1
        await self._update_message(interaction)

    async def _update_message(self, interaction: discord.Interaction) -> None:
        self._update_buttons()
        group_name = self.group_names[self.current_page]
        page_data = self.data.copy()
        page_data["services"] = self.groups[group_name]
        embed = self.cog.create_status_embed(
            page_data,
            page_info=(self.current_page + 1, self.total_pages),
            summary_mode=False,
            **await self.cog.guild_render_settings(interaction.guild_id),
        )
        await interaction.response.edit_message(embed=embed, view=self)


class StatusDashboardView(ui.View):
    def __init__(
        self,
        bot: "DiscordUptimeTrackerBot",
        cog: "UptimeCog",
        data: dict[str, Any],
        page_url: str | None = None,
    ) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.cog = cog
        self.page_url = page_url or bot.config.STATUS_PAGE_URL
        groups = cog.group_services(data)
        self.add_item(
            ui.Button(
                label="Full Status Page",
                url=self.page_url,
                row=4,
            )
        )
        for index, group_name in enumerate(list(groups.keys())[:24]):
            row = index // 5
            button = ui.Button(
                label=group_name[:80],
                style=discord.ButtonStyle.secondary,
                custom_id=f"status_group_{group_name}",
                row=row,
            )
            button.callback = self._create_group_callback(group_name)
            self.add_item(button)

    def _create_group_callback(self, group_name: str):
        async def callback(interaction: discord.Interaction) -> None:
            data = self.cog.last_status or await self.cog.fetch_status()
            if not data:
                await interaction.response.send_message(
                    "I could not fetch status data right now.",
                    ephemeral=True,
                )
                return
            groups = self.cog.group_services(data)
            services = groups.get(group_name)
            if not services:
                await interaction.response.send_message(
                    "That service group is not available right now.",
                    ephemeral=True,
                )
                return
            page_data = data.copy()
            page_data["services"] = services
            embed = self.cog.create_status_embed(
                page_data,
                summary_mode=False,
                **await self.cog.guild_render_settings(interaction.guild_id),
            )
            embed.title = group_name
            await interaction.response.send_message(embed=embed, ephemeral=True)

        return callback
