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


# The page loops to total; 100 reaches back about ten days, not thirty.
def test_it_keeps_paging_until_it_has_them_all() -> None:
    pages = {0: _page(100, 258, 0), 100: _page(100, 258, 100), 200: _page(58, 258, 200)}
    rows, seen = _run(pages)
    assert len(rows) == 258
    assert len(seen) == 3


def test_one_page_is_enough_when_that_is_all_there_is() -> None:
    rows, seen = _run({0: _page(12, 12, 0)})
    assert len(rows) == 12
    assert len(seen) == 1


def test_it_stops_rather_than_looping_when_a_page_fails() -> None:
    rows, seen = _run({0: _page(100, 258, 0), 100: None})
    assert len(rows) == 100
    assert len(seen) == 2


def test_ids_are_not_duplicated_across_pages() -> None:
    pages = {0: _page(100, 258, 0), 100: _page(100, 258, 100), 200: _page(58, 258, 200)}
    rows, _ = _run(pages)
    assert len({r["id"] for r in rows}) == 258
