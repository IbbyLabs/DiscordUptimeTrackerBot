# DiscordUptimeTrackerBot

DiscordUptimeTrackerBot is a standalone Discord bot for one job: showing a live uptime tracker from a compatible status API.


## Features

- Slash uptime commands
- Active outages listed at the top of the board
- Incident history, with the services each outage affected
- Alerts when a service stops answering and when it starts again
- Live tracker message setup for a guild
- Automatic refresh for tracked messages
- Automatic alert delivery when service states change
- Group buttons for detailed service views
- Lightweight SQLite storage
- Docker image publishing on tagged GitHub releases

## Commands

- `/uptime`
- `/status`
- `/incidents`
- `/tracker setup`
- `/tracker alerts`
- `/tracker refresh`
- `/tracker stopalerts`
- `/tracker remove`

`tracker` commands require Manage Server, or the instance owner. `/uptime`,
`/status` and `/incidents` are open to any member.

The bot requests no privileged intents.

## Setup

1. Create a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env`.
4. Set `BOT_TOKEN`.
5. Run `python bot.py`.

## Docker

Build locally:

```bash
docker build -t discord-uptime-tracker-bot .
```

Run locally with your env file:

```bash
docker run --env-file .env discord-uptime-tracker-bot
```

## Environment

- `BOT_TOKEN`: Discord bot token
- `BOT_OWNER_ID`: Optional owner override
- `GUILD_ID`: Optional guild for faster command sync during development
- `DATABASE_PATH`: SQLite file path
- `STATUS_API_URL`: Optional JSON status API endpoint override
- `STATUS_PAGE_URL`: Optional public status page URL override
- `STATUS_EMOJI`: Emoji used for healthy states and presence
- `BRAND_NAME`: Board title. Set it and it wins; leave it unset and the
  status API's own name is used
- `REFRESH_MINUTES`: Automatic refresh interval in minutes

## Releases

Use the release script to bump the version, validate the repo, create the release commit and tag, push both, and publish a GitHub release:

```bash
bash scripts/release.sh patch
bash scripts/release.sh minor
bash scripts/release.sh major
```

Requirements:

- `gh` must be installed and authenticated
- Your working tree must be clean
- Run the script from the `main` branch

For a safe preview, run:

```bash
bash scripts/release.sh patch --dry-run
```

Publishing a GitHub release triggers the Docker workflow, which builds and pushes a multi-platform image for `linux/amd64` and `linux/arm64` to `ghcr.io/ibbylabs/discorduptimetrackerbot`.

Each release also updates `CHANGELOG.md` automatically and uses commit subjects since the previous tag for both the changelog entry and the GitHub release notes.

