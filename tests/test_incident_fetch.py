import asyncio
from typing import Any, cast

import status_api


def _page(rows, total, offset):
    return {
        "incidents": [
            {
                "id": f"i{offset + n}",
                "service": {"id": "svc", "name": "A Service", "group": "Group"},
                "state": "DOWN",
                "openedAt": "2026-08-01T00:00:00.000Z",
                "closedAt": "2026-08-01T01:00:00.000Z",
                "error": "HTTP 503",
                "events": [],
            }
            for n in range(rows)
        ],
        "total": total,
        "limit": 100,
        "offset": offset,
    }


def _fake_get(pages, seen):
    async def _get(url, what):
        seen.append(url)
        offset = 0
        if "offset=" in url:
            offset = int(url.split("offset=")[1].split("&")[0])
        return pages.get(offset)
    return _get


def _run(pages):
    seen: list[str] = []
    original = status_api._get_json
    status_api._get_json = cast(Any, _fake_get(pages, seen))
    try:
        rows = asyncio.run(status_api.fetch_incidents("https://x.test/v1/incidents"))
    finally:
        status_api._get_json = original
    return rows, seen


# The panel shows ten, so a wider fetch buys nothing and costs requests against
# our own Worker. One request, and the largest page it serves.
def test_it_makes_exactly_one_request() -> None:
    rows, seen = _run({0: _page(100, 258, 0), 100: _page(100, 258, 100)})
    assert len(seen) == 1
    assert len(rows) == 100


def test_it_asks_for_the_largest_page() -> None:
    _, seen = _run({0: _page(100, 258, 0)})
    assert "limit=100" in seen[0]
    assert "offset=" not in seen[0]


def test_a_failed_request_leaves_the_panel_empty_rather_than_erroring() -> None:
    rows, seen = _run({0: None})
    assert rows == []
    assert len(seen) == 1


def test_a_service_without_the_label_reads_unknown() -> None:
    assert status_api.service_state({"last": {"state": "DOWN"}}) == "UNKNOWN"
    assert status_api.service_state({}) == "UNKNOWN"


def test_the_label_wins_when_both_are_there() -> None:
    svc = {"displayState": "MAINTENANCE", "last": {"state": "UP"}}
    assert status_api.service_state(svc) == "MAINTENANCE"


def test_a_held_service_reads_down_beneath_its_label() -> None:
    assert status_api.service_state({"displayState": "RECOVERING"}) == "DOWN"
