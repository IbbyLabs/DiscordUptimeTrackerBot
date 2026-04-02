# DiscordUptimeTrackerBot

DiscordUptimeTrackerBot is a standalone Discord bot for one job: showing a live uptime tracker from a compatible status API.


## Features

- Slash and prefix uptime commands
- Live tracker message setup for a guild
- Automatic refresh for tracked messages
- Group buttons for detailed service views
- Lightweight SQLite storage

## Commands

- `/uptime`
- `/tracker setup`
- `/tracker refresh`
- `/tracker remove`
- `.uptime`
- `.setupuptime`
- `.refreshuptime`
- `.removeuptime`

`tracker` commands are owner only.

## Setup

1. Create a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env`.
4. Set `BOT_TOKEN`.
5. Run `python bot.py`.

## Environment

- `BOT_TOKEN`: Discord bot token
- `BOT_OWNER_ID`: Optional owner override
- `GUILD_ID`: Optional guild for faster command sync during development
- `COMMAND_PREFIX`: Prefix command trigger. Default is `.`
- `DATABASE_PATH`: SQLite file path
- `STATUS_API_URL`: Optional JSON status API endpoint override
- `STATUS_PAGE_URL`: Optional public status page URL override
- `STATUS_EMOJI`: Emoji used for healthy states and presence
- `BRAND_NAME`: Optional embed title override
- `BRAND_DESCRIPTION`: Optional embed intro text override
- `REFRESH_MINUTES`: Automatic refresh interval in minutes
