"""The board says when the page has stopped updating.

A board that cannot refresh does not read as broken, it reads as current — the
exact failure that made us delete XRDBBOT's frozen panels. The page decides
staleness at 360 seconds and publishes the verdict; working it out here would
be a second copy of that rule.
"""

import os
from types import SimpleNamespace
from typing import Any, cast

os.environ.setdefault("BOT_TOKEN", "x")
os.environ.setdefault("STATUS_API_URL", "http://localhost/api")

import status_api
from cogs.uptime import UptimeCog


def _cog():
    cog = UptimeCog.__new__(UptimeCog)
    cast(Any, cog).bot = SimpleNamespace(
        version="1.2.3",
        config=SimpleNamespace(
            STATUS_PAGE_URL="https://default.example/",
            STATUS_EMOJI="🟢",
            BRAND_NAME="Uptime Tracker",
            BRAND_NAME_OVERRIDE=None,
        ),
    )
    return cog


FRESH = {"generatedAt": "2026-08-22T18:48:16.000Z",
         "freshness": {"ageSeconds": 135, "staleAfterSeconds": 360, "stale": False}}
STALE = {"generatedAt": "2026-08-22T17:00:00.000Z",
         "freshness": {"ageSeconds": 3600, "staleAfterSeconds": 360, "stale": True}}


def test_a_fresh_payload_says_nothing_about_staleness() -> None:
    assert _cog().staleness_line(cast(Any, FRESH)) is None


def test_a_stale_payload_says_so_with_the_numbers() -> None:
    line = _cog().staleness_line(cast(Any, STALE))
    assert line is not None
    assert "60m" in line
    assert "6m" in line


def test_the_verdict_is_the_pages_not_ours() -> None:
    # Old but not stale by the page's own rule: we must not overrule it.
    data = {"freshness": {"ageSeconds": 300, "staleAfterSeconds": 360, "stale": False}}
    assert _cog().staleness_line(cast(Any, data)) is None
    assert status_api.freshness(data)["stale"] is False


def test_a_payload_without_freshness_makes_no_claim() -> None:
    assert status_api.freshness({}) is None
    assert _cog().staleness_line(cast(Any, {})) is None


# Stamping the board with our own clock turns a payload that stopped arriving
# into one that looks freshly delivered.
def test_a_missing_timestamp_is_not_replaced_with_now() -> None:
    assert _cog().last_updated_unix(cast(Any, {})) is None
    assert _cog().last_updated_unix(cast(Any, {"generatedAt": "not-a-date"})) is None


def test_a_real_timestamp_is_read_from_the_payload() -> None:
    assert _cog().last_updated_unix(cast(Any, FRESH)) == 1787424496


# staleAfterSeconds is the threshold for calling data old. The payload publishes
# no check interval, and naming 360s as one told the reader two checks had been
# missed where six had.
def test_the_line_names_the_threshold_and_not_a_check_interval() -> None:
    line = _cog().staleness_line(cast(Any, STALE))
    assert line is not None
    assert "treated as out of date" in line
    assert "checked every" not in line, "360s is not the interval between checks"


def test_both_numbers_still_reach_the_reader() -> None:
    line = _cog().staleness_line(cast(Any, STALE))
    assert "60m" in line, "how long it has been"
    assert "6m" in line, "the threshold it passed"
