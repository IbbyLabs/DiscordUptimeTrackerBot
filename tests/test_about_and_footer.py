import os
from types import SimpleNamespace
from typing import Any, cast

os.environ.setdefault("BOT_TOKEN", "x")
os.environ.setdefault("STATUS_API_URL", "http://localhost/api")

from cogs.uptime import UptimeCog
from ui.status_layout import AboutLayout

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _cog(version="1.2.3"):
    cog = UptimeCog.__new__(UptimeCog)
    cast(Any, cog).bot = SimpleNamespace(
        version=version,
        config=SimpleNamespace(
            STATUS_PAGE_URL="https://default.example/",
            STATUS_EMOJI="🟣",
            BRAND_NAME="Uptime Tracker",
            BRAND_NAME_OVERRIDE=None,
        ),
    )
    return cog


def _text(view):
    return "\n".join(getattr(c, "content", "") or "" for c in view.walk_children())


def _urls(view):
    return [str(getattr(c, "url", "")) for c in view.walk_children() if getattr(c, "url", None)]


def test_about_carries_every_contact_route_and_the_source() -> None:
    urls = _urls(AboutLayout(_cog()))
    for expected in ("https://ibbylabs.dev", "https://kofi.ibbylabs.dev",
                     "https://discord.ibbylabs.dev", "https://dm.ibbylabs.dev"):
        assert expected in urls, expected
    assert "github.com/IbbyLabs/DiscordUptimeTrackerBot" in _text(AboutLayout(_cog()))


# Redirects, so reissuing a link is one change rather than an edit everywhere.
def test_about_uses_the_redirects_not_their_destinations() -> None:
    body = _text(AboutLayout(_cog())) + "\n".join(_urls(AboutLayout(_cog())))
    assert "discord.gg" not in body
    assert "discord.com/users" not in body
    assert "ko-fi.com" not in body


def test_about_names_the_running_version_and_the_licence() -> None:
    body = _text(AboutLayout(_cog(version="4.5.6")))
    assert "v4.5.6" in body
    assert "MIT" in body


# The guild's own settings have to reach it, or the guard test is satisfied by a
# parameter nothing reads.
def test_about_uses_the_guilds_page_url_and_emoji() -> None:
    view = AboutLayout(_cog(), healthy="🔵", page_url="https://guild.example/")
    assert "https://guild.example/" in _urls(view)
    assert "https://default.example/" not in _urls(view)
    assert "🔵" in _text(view)


def test_the_board_footer_credits_ibbylabs_and_names_the_build() -> None:
    import json
    from ui.status_layout import StatusLayout
    data = json.load(open(FIXTURES / "status.json"))
    body = _text(StatusLayout(_cog(version="7.8.9"), data))
    assert "Developed by IbbyLabs • v7.8.9" in body


# The board sits in a channel permanently, so it carries the credit and nothing
# that would become clutter.
def test_the_board_carries_no_links_beyond_the_status_page() -> None:
    import json
    from ui.status_layout import StatusLayout
    data = json.load(open(FIXTURES / "status.json"))
    view = StatusLayout(_cog(), data)
    for unwanted in ("kofi.ibbylabs.dev", "discord.ibbylabs.dev", "dm.ibbylabs.dev"):
        assert unwanted not in "\n".join(_urls(view)) + _text(view), unwanted
