import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cogs.uptime import UptimeCog


def build_cog() -> UptimeCog:
    bot = SimpleNamespace(
        config=SimpleNamespace(
            STATUS_API_URL="https://status.example.com/api",
            STATUS_PAGE_URL="https://status.example.com",
            STATUS_EMOJI="🟣",
            BRAND_NAME="Status Tracker",
            BRAND_DESCRIPTION="Status summary text",
            REFRESH_MINUTES=10.0,
            BOT_OWNER_ID=None,
        ),
        user=None,
        add_view=lambda view: None,
    )
    return UptimeCog(cast(Any, bot))


def test_create_status_embed_builds_summary_fields() -> None:
    cog = build_cog()
    data = {
        "source": {"name": "Status Tracker"},
        "summary": {"up": 2, "down": 1, "degraded": 0},
        "services": [
            {
                "group": "Stremio",
                "name": "A",
                "url": "https://example.com/a",
                "hideFromStatusPage": False,
                "requiresAuth": False,
                "uptimePercent": 100,
                "last": {"state": "UP", "latency": 10},
            },
            {
                "group": "Stremio",
                "name": "B",
                "url": "https://example.com/b",
                "hideFromStatusPage": False,
                "requiresAuth": True,
                "uptimePercent": 98.5,
                "last": {"state": "DOWN", "latency": 20},
            },
        ],
    }

    embed = cog.create_status_embed(data, summary_mode=True)

    assert embed.title == "Status Tracker"
    assert "Welcome to Status Tracker" in (embed.description or "")
    assert embed.fields[0].name == "Stremio 🔒"
    assert "1/2" in (embed.fields[0].value or "")
