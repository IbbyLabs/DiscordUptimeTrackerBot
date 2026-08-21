import json
import os
from types import SimpleNamespace
from typing import Any, cast

os.environ.setdefault("BOT_TOKEN", "x")
os.environ.setdefault("STATUS_API_URL", "http://localhost/api")

from cogs.uptime import UptimeCog
from ui.status_layout import StatusLayout


def _cog():
    cog = UptimeCog.__new__(UptimeCog)
    cast(Any, cog).bot = SimpleNamespace(
        version="1.0.0",
        config=SimpleNamespace(
            STATUS_PAGE_URL="https://status.example/", STATUS_EMOJI="🟣",
            BRAND_NAME="Tracker", BRAND_NAME_OVERRIDE=None,
        ),
    )
    return cog


# The shape the status page publishes, from serializeBulletinStateForApi.
def _bulletin(**over):
    base = {
        "active": True,
        "title": "Torbox usenet is discontinued",
        "message": "Torbox have withdrawn usenet. The row stays for history.",
        "affectedServiceIds": ["torbox-usenet"],
        "affectedServices": [{"id": "torbox-usenet", "name": "Torbox Usenet", "group": "Debrid"}],
        "updatedAt": "2026-08-21T22:00:00Z",
    }
    base.update(over)
    return base


def test_no_bulletin_set_reads_as_none() -> None:
    assert _cog().bulletin(cast(Any, {"bulletin": None})) is None
    assert _cog().bulletin(cast(Any, {})) is None


# active:false is the page saying there is no notice, not a notice saying false.
def test_an_inactive_bulletin_is_not_shown() -> None:
    assert _cog().bulletin(cast(Any, {"bulletin": _bulletin(active=False)})) is None


def test_a_bulletin_with_no_message_is_not_shown() -> None:
    assert _cog().bulletin(cast(Any, {"bulletin": _bulletin(message="   ")})) is None


def test_the_lines_carry_the_title_message_and_who_it_affects() -> None:
    lines = _cog().bulletin_lines(_bulletin())
    body = "\n".join(lines)
    assert "Torbox usenet is discontinued" in body
    assert "withdrawn usenet" in body
    assert "Affects Torbox Usenet" in body
    assert "<t:" in body


def test_a_bulletin_without_a_title_still_renders() -> None:
    body = "\n".join(_cog().bulletin_lines(_bulletin(title=None)))
    assert "Notice" in body


def test_a_long_affected_list_is_summarised() -> None:
    services = [{"id": f"s{i}", "name": f"Service {i}"} for i in range(8)]
    body = "\n".join(_cog().bulletin_lines(_bulletin(affectedServices=services)))
    assert "and 3 more" in body


def test_no_affected_services_omits_the_line() -> None:
    body = "\n".join(_cog().bulletin_lines(_bulletin(affectedServices=[])))
    assert "Affects" not in body


# It goes above what the board derives, because a state cannot say it.
def test_the_bulletin_is_the_first_thing_on_the_board() -> None:
    data = json.load(open("/home/ubuntu/.claude/jobs/e7d81c08/tmp/live.json"))
    data["bulletin"] = _bulletin()
    body = "\n".join(
        getattr(c, "content", "") or "" for c in StatusLayout(_cog(), data).walk_children()
    )
    lines = [l for l in body.split("\n") if l.strip()]
    position = next(i for i, l in enumerate(lines) if "discontinued" in l)
    outages = next(i for i, l in enumerate(lines) if "Active outages" in l)
    assert position < outages, "the bulletin sat below the derived sections"


def test_a_board_with_no_bulletin_is_unchanged() -> None:
    data = json.load(open("/home/ubuntu/.claude/jobs/e7d81c08/tmp/live.json"))
    body = "\n".join(
        getattr(c, "content", "") or "" for c in StatusLayout(_cog(), data).walk_children()
    )
    assert "📢" not in body
