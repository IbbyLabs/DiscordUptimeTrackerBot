"""Incident-level alerting.

An outage is one incident rather than a stream of per-service events: it opens
once, names each affected service once, and closes once. A service the incident
has already named stays out of the channel when it flaps, and the panel carries
it instead.
"""

from datetime import datetime
from typing import Any

AlertChange = dict[str, Any]


# Services whose transitions are not announced. Both forms are listed because a
# status source can rename a service without changing its id, or the reverse.
_ALERT_SUPPRESSED_NAMES = {
    "webstreamr",
    "webstreamer",
    "webstreamer mbg",
}
_ALERT_SUPPRESSED_IDS = {
    "webstreamr",
    "webstreamer",
    "webstreamr_mbg",
    "webstreamrmbg",
    "webstreamer_mbg",
}


def _alert_filter_name(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _alert_filter_id(value: object) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return "_".join(part for part in normalized.split("_") if part)


def is_alert_suppressed(service: dict[str, object]) -> bool:
    return (
        _alert_filter_name(service.get("name")) in _ALERT_SUPPRESSED_NAMES
        or _alert_filter_id(service.get("id")) in _ALERT_SUPPRESSED_IDS
    )


def is_alertable_transition(previous_state: object, current_state: object) -> bool:
    """Crossing the DOWN boundary, in either direction.

    DOWN is the state where the check got no answer; every other reported state
    means it answered. UNKNOWN is unmeasured and maintenance is planned, so
    neither is a verdict about availability on either side of the change.
    """

    previous = str(previous_state or "").strip().upper()
    current = str(current_state or "").strip().upper()
    if not previous or not current:
        return False
    if {previous, current} & {"UNKNOWN", "MAINTENANCE"}:
        return False
    return (previous == "DOWN") != (current == "DOWN")


def normalise_page_incidents(payload: Any) -> list[dict[str, Any]]:
    """The status page's own incident records, in the shape the panel renders.

    Taken from the page rather than rebuilt locally: it holds outages that
    started before this bot did, and the times they actually began.
    """

    items = payload.get("incidents") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []

    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        service = item.get("service") if isinstance(item.get("service"), dict) else {}
        opened = str(item.get("openedAt") or "")
        if not opened:
            continue
        rows.append({
            "id": str(item.get("id") or ""),
            "service_id": str(service.get("id") or ""),
            "name": str(service.get("name") or service.get("id") or "Unknown service"),
            "group": str(service.get("group") or ""),
            "state": str(item.get("state") or "").upper(),
            "opened_at": opened,
            "closed_at": str(item.get("closedAt")) if item.get("closedAt") else None,
            "error": str(item.get("error") or "").strip(),
            "events": [
                {
                    "state": str(event.get("state") or "").upper(),
                    "duration": str(event.get("duration") or "").strip(),
                    "error": str(event.get("error") or "").strip(),
                }
                for event in (item.get("events") or [])
                if isinstance(event, dict)
            ],
        })
    # Newest first, since a reader asking what happened means recently.
    rows.sort(key=lambda row: row["opened_at"], reverse=True)
    return rows


def format_page_incidents(rows: list[dict[str, Any]], limit: int = 10) -> list[str]:
    """One line per incident, ongoing ones first and newest within that."""

    if not rows:
        return ["No incidents recorded yet."]

    ongoing = [r for r in rows if not r["closed_at"]]
    closed = [r for r in rows if r["closed_at"]]
    lines: list[str] = []
    for row in (ongoing + closed)[:limit]:
        marker = "🔴" if not row["closed_at"] else "🟢"
        where = f" ({row['group']})" if row["group"] else ""
        when = _iso_stamp(row["opened_at"])
        if row["closed_at"]:
            when = f"{when} to {_iso_stamp(row['closed_at'])}"
        else:
            when = f"{when}, ongoing"
        line = f"{marker} **{row['name']}**{where}\n-# {when}"
        chain = _event_chain(row)
        if chain:
            line += f"\n-# {chain}"
        lines.append(line)
    return lines


def _event_chain(row: dict[str, Any]) -> str:
    """How the incident went, not just when it started.

    An outage that degrades before it fails opens earlier than it goes down,
    and the chain is the only place that difference is visible.
    """

    events = row.get("events") or []
    parts: list[str] = []
    for event in events:
        state = event.get("state") or "?"
        duration = event.get("duration")
        piece = f"{state} {duration}" if duration and duration != "0s" else state
        if event.get("error"):
            piece += f" ({event['error']})"
        parts.append(piece)
    if not parts:
        return row.get("error") or ""
    return " → ".join(parts)


def _iso_stamp(value: str) -> str:
    """An ISO timestamp as Discord's own, so it reads in the reader's zone."""

    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return str(value)
    return f"<t:{int(moment.timestamp())}:f>"


def alertable_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The incidents worth announcing.

    A suppressed service still appears in the history panel — it did go down —
    but it does not ring a channel. The noisiest service on the page accounts
    for nine of the last fifty incidents.
    """

    return [
        row for row in rows
        if not is_alert_suppressed({"name": row.get("name"), "id": row.get("service_id")})
    ]


def plan_page_incident_alerts(
    *,
    announced: dict[str, dict[str, bool]],
    rows: list[dict[str, Any]],
    anything_still_down: bool,
) -> dict[str, Any]:
    """What to announce, given the page's incidents and what we have said.

    The page owns which incidents exist; this owns which have been spoken about.
    An incident we have never seen and which is already closed is history rather
    than news, so it is recorded silently.
    """

    to_open: list[dict[str, Any]] = []
    to_close: list[dict[str, Any]] = []
    silent: list[str] = []

    for row in rows:
        incident_id = row["id"]
        if not incident_id:
            continue
        state = announced.get(incident_id)
        ongoing = row["closed_at"] is None

        if state is None:
            if ongoing:
                to_open.append(row)
            else:
                # Opened and closed between two cycles, or before we ever
                # looked. Announcing both ends at once says nothing useful.
                silent.append(incident_id)
            continue

        if ongoing and not state["opened"]:
            to_open.append(row)
        elif not ongoing and not state["closed"]:
            to_close.append(row)

    # Taken from the status payload rather than from these rows. The incident
    # list is paged, so an outage running longer than the page's window falls
    # off it — and an all-clear derived from a truncated list is a false one.
    return {
        "open": to_open,
        "close": to_close,
        "silent": silent,
        "all_clear": bool(to_close) and not anything_still_down,
    }


def build_page_incident_messages(plan: dict[str, Any]) -> list[tuple[str, list[str]]]:
    """The announcements for one cycle, as heading and body lines."""

    messages: list[tuple[str, list[str]]] = []

    opened = plan["open"]
    if opened:
        verb = "service is" if len(opened) == 1 else "services are"
        messages.append((
            f"## 🔴 Outage started\n{len(opened)} {verb} not responding.",
            [_incident_line(row, "🔴") for row in opened],
        ))

    closed = plan["close"]
    if closed:
        if plan["all_clear"]:
            heading = "## 🟢 All clear\nEvery service is responding again."
        else:
            verb = "service is" if len(closed) == 1 else "services are"
            heading = f"## 🟢 Back up\n{len(closed)} {verb} responding again."
        messages.append((heading, [_incident_line(row, "🟢") for row in closed]))

    return messages


def _incident_line(row: dict[str, Any], marker: str) -> str:
    where = f" ({row['group']})" if row.get("group") else ""
    started = _iso_stamp(row["opened_at"])
    if row.get("closed_at"):
        return f"{marker} **{row['name']}**{where}\n-# down from {started} to {_iso_stamp(row['closed_at'])}"
    return f"{marker} **{row['name']}**{where}\n-# since {started}"
