"""Reads of the status service.

Two routes on one host: the board's payload and the incident record. Both fail
to nothing rather than raising, so a refresh cycle degrades instead of dying.
"""

import asyncio
import logging
from typing import Any

import aiohttp

from incidents import normalise_page_incidents

log = logging.getLogger("uptimebot.status_api")

TIMEOUT_SECONDS = 10
_NETWORK_ERRORS = (aiohttp.ClientError, asyncio.TimeoutError, ValueError)


# The largest page the endpoint serves.
INCIDENT_PAGE_SIZE = 100
# Bounds the loop if total never agrees with what comes back.
INCIDENT_PAGE_CAP = 20


async def _get_json(url: str, what: str) -> Any:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)
            ) as response:
                if response.status != 200:
                    log.error("Failed to fetch %s: HTTP %s", what, response.status)
                    return None
                return await response.json()
    except _NETWORK_ERRORS as exc:
        log.error("Error fetching %s: %s", what, exc)
        return None


async def fetch_status(url: str) -> dict[str, Any] | None:
    payload = await _get_json(url, "status")
    if not isinstance(payload, dict):
        if payload is not None:
            log.error("Unexpected status payload type: %s", type(payload).__name__)
        return None
    return payload


async def fetch_incidents(url: str) -> list[dict[str, Any]]:
    """The status page's incident records, newest first.

    Empty on failure, so the panel says it has no history rather than the
    command failing in front of someone.
    """

    separator = "&" if "?" in url else "?"
    collected: list[dict[str, Any]] = []
    offset = 0

    # One page of 100 reaches back about ten days. The window the panel claims
    # is 30, so it takes every page the endpoint reports.
    for _ in range(INCIDENT_PAGE_CAP):
        payload = await _get_json(
            f"{url}{separator}limit={INCIDENT_PAGE_SIZE}&offset={offset}", "incidents"
        )
        rows = normalise_page_incidents(payload)
        if not rows:
            if payload is None and collected:
                log.warning(
                    "Incident history stops at %s records: a page did not answer",
                    len(collected),
                )
            break

        collected.extend(rows)
        offset += len(rows)

        total = payload.get("total") if isinstance(payload, dict) else None
        if not isinstance(total, int) or offset >= total:
            break
    else:
        log.warning("Incident history stopped at the %s page cap", INCIDENT_PAGE_CAP)

    return collected
