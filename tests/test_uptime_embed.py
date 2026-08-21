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

    from ui.status_layout import StatusLayout

    view = StatusLayout(cog, data)
    body = "\n".join(getattr(child, "content", "") or "" for child in view.walk_children())

    # Identity appears once, in the header. Asserting the count rather than the
    # absence, so the repetition cannot creep back one line at a time.
    assert body.count("Status Tracker") == 1
    assert "Welcome to" not in body
    assert "Stremio" in body
    assert "1/2" in body
    # Both Components V2 ceilings, on the message a server sees every refresh.
    assert view.content_length() <= 4000
    assert len(tuple(view.walk_children())) <= 40


class FakeDB:
    def __init__(
        self,
        states: dict[str, str] | None = None,
        alert_channels: list[dict[str, str]] | None = None,
    ) -> None:
        self.states = states or {}
        self.alert_channels = alert_channels or []

    async def get_service_states(self) -> dict[str, str]:
        return dict(self.states)

    async def replace_service_states(self, states: dict[str, str]) -> None:
        self.states = dict(states)

    async def list_alert_channels(self) -> list[dict[str, str]]:
        return list(self.alert_channels)

    async def get_guild_settings(self, guild_id: str) -> dict[str, object]:
        return {}


class FakeChannel:
    def __init__(self) -> None:
        self.sent_views: list[Any] = []

    async def send(self, *, view: Any) -> None:
        self.sent_views.append(view)


def build_alert_cog(
    *,
    states: dict[str, str] | None = None,
    alert_channels: list[dict[str, str]] | None = None,
) -> tuple[UptimeCog, FakeDB, FakeChannel]:
    db = FakeDB(states=states, alert_channels=alert_channels)
    channel = FakeChannel()

    async def fetch_channel(channel_id: int) -> FakeChannel:
        return channel

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
        db=db,
        get_channel=lambda channel_id: channel,
        fetch_channel=fetch_channel,
    )
    cog = UptimeCog(cast(Any, bot))

    async def resolve_tracker_channel(channel_id: int) -> FakeChannel:
        return channel

    cog.resolve_tracker_channel = resolve_tracker_channel  # type: ignore[method-assign]
    return cog, db, channel


def test_process_status_alerts_primes_baseline_without_sending() -> None:
    async def run() -> None:
        cog, db, channel = build_alert_cog(
            alert_channels=[{"guild_id": "1", "channel_id": "123"}],
        )
        data = {
            "source": {"name": "Status Tracker"},
            "summary": {"up": 1, "down": 0, "degraded": 0},
            "services": [
                {
                    "group": "Core",
                    "name": "API",
                    "url": "https://example.com/api",
                    "hideFromStatusPage": False,
                    "requiresAuth": False,
                    "uptimePercent": 100,
                    "last": {"state": "UP", "latency": 10},
                }
            ],
        }

        sent = await cog.process_status_alerts(data)

        assert sent == 0
        assert channel.sent_views == []
        assert db.states == {"Core|API|https://example.com/api": "UP"}

    import asyncio

    asyncio.run(run())


def test_process_status_alerts_sends_when_service_changes() -> None:
    async def run() -> None:
        states = {"Core|API|https://example.com/api": "UP"}
        cog, db, channel = build_alert_cog(
            states=states,
            alert_channels=[{"guild_id": "1", "channel_id": "123"}],
        )
        data = {
            "source": {"name": "Status Tracker"},
            "summary": {"up": 0, "down": 1, "degraded": 0},
            "services": [
                {
                    "group": "Core",
                    "name": "API",
                    "url": "https://example.com/api",
                    "hideFromStatusPage": False,
                    "requiresAuth": False,
                    "uptimePercent": 98.5,
                    "last": {"state": "DOWN", "latency": 250},
                }
            ],
        }

        sent = await cog.process_status_alerts(data)

        assert sent == 1
        assert db.states == {"Core|API|https://example.com/api": "DOWN"}
        assert len(channel.sent_views) == 1
        layout = channel.sent_views[0]
        body = "\n".join(
            getattr(child, "content", "") for child in layout.walk_children()
        )
        assert "Status Alerts" in body
        assert "Status Tracker" not in body
        assert "🔴 **API**" in body
        assert "UP → DOWN" in body
        assert layout.content_length() <= 4000

    import asyncio

    asyncio.run(run())
