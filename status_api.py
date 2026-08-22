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
def service_state(service: dict[str, Any]) -> str:
    """The label the status page resolved for this service.

    RECOVERING sits over a service that is still held down, so counting and
    listing treat it as DOWN, exactly as the page does.
    """

    label = str(service.get("displayState") or "").upper()
    if label == "RECOVERING":
        return "DOWN"
    return label or "UNKNOWN"


def service_unstable(service: dict[str, Any]) -> bool:
    """Answering, but still inside its recovery hold."""

    return service.get("unstable") is True


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

    # One request. 100 is the largest page the endpoint serves and costs the
    # same as asking for fewer, so it buys the widest window available for it.
    # majorOnly applies the status page's own 30-minute rule and merges
    # neighbouring outages, so the panel renders the page's list rather than a
    # second copy of the rule.
    separator = "&" if "?" in url else "?"
    return normalise_page_incidents(
        await _get_json(
            f"{url}{separator}limit={INCIDENT_PAGE_SIZE}&majorOnly=true", "incidents"
        )
    )
