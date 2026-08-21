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


def plan_incident_alerts(
    *,
    incident_open: bool,
    seen_keys: set[str],
    down_keys: set[str],
    newly_down: list[tuple[str, str]],
    newly_up: list[tuple[str, str]],
    present_keys: set[str],
) -> dict[str, Any]:
    """What one refresh cycle should announce.

    Everything a cycle observes arrives together, which is the batching: several
    services failing in the same cycle produce one message rather than a timer.
    """

    opening = not incident_open and bool(newly_down)
    joined = [(key, name) for key, name in newly_down if key not in seen_keys]
    rejoined = [(key, name) for key, name in newly_down if key in seen_keys]
    recovered = [(key, name) for key, name in newly_up if key in down_keys]

    still_down = set(down_keys)
    still_down.update(key for key, _ in newly_down)
    still_down.difference_update(key for key, _ in newly_up)

    # A service can leave the payload mid-incident: hidden, renamed, or moved to
    # another group, since the key carries the group and name. It has not
    # recovered, but it can no longer be observed, so it cannot hold the incident
    # open. An empty payload is a failed fetch rather than every service leaving,
    # and prunes nothing.
    vanished: set[str] = set()
    if present_keys:
        vanished = still_down - present_keys
        still_down -= vanished

    closing = (incident_open or opening) and not still_down

    return {
        "opening": opening,
        "closing": closing,
        "opened_with": joined if opening else [],
        "joined": [] if opening else joined,
        "rejoined": rejoined,
        "recovered": recovered,
        "vanished": vanished,
        "still_down": still_down,
    }


def _plural(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


async def build_incident_messages(
    db: Any,
    changes: list[AlertChange],
    present_keys: set[str],
    still_down_elsewhere: int = 0,
) -> list[tuple[str, list[AlertChange]]]:
    """Turn a cycle's changes into announcements, recording the incident.

    The database is updated whether or not a message goes out, so an install
    with no alert channel still has an accurate incident.
    """

    if db is None:
        return []

    by_key = {str(change["key"]): change for change in changes}
    newly_down = [
        (str(c["key"]), str(c["name"])) for c in changes if str(c["state"]).upper() == "DOWN"
    ]
    newly_up = [
        (str(c["key"]), str(c["name"])) for c in changes if str(c["state"]).upper() != "DOWN"
    ]

    incident = await db.get_open_incident()
    rows = await db.list_incident_services(int(incident["id"])) if incident else []
    plan = plan_incident_alerts(
        incident_open=incident is not None,
        seen_keys={str(row["service_key"]) for row in rows},
        down_keys={str(row["service_key"]) for row in rows if row["recovered_at"] is None},
        newly_down=newly_down,
        newly_up=newly_up,
        present_keys=present_keys,
    )

    incident_id = await db.open_incident() if plan["opening"] else (
        int(incident["id"]) if incident else 0
    )
    if incident_id:
        await db.add_incident_services(incident_id, list(newly_down))
        await db.mark_incident_services_down(incident_id, [k for k, _ in plan["rejoined"]])
        await db.mark_incident_services_recovered(incident_id, [k for k, _ in plan["recovered"]])

    def group_for(pairs: list[tuple[str, str]]) -> list[AlertChange]:
        return [by_key[key] for key, _ in pairs if key in by_key]

    messages: list[tuple[str, list[AlertChange]]] = []

    if plan["opening"]:
        affected = group_for(plan["opened_with"])
        verb = _plural(len(affected), "service is", "services are")
        messages.append((f"## Outage started\n{len(affected)} {verb} not responding.", affected))
    elif plan["joined"]:
        affected = group_for(plan["joined"])
        verb = _plural(len(affected), "service has", "services have")
        messages.append((f"## Outage spreading\n{len(affected)} more {verb} gone down.", affected))

    back = group_for(plan["recovered"])
    if back and not plan["closing"]:
        verb = _plural(len(back), "service is", "services are")
        messages.append((f"## Back up\n{len(back)} {verb} responding again.", back))

    if plan["closing"]:
        if back:
            # The incident's own services, not the estate. Others can be down
            # from before it opened, and calling that all clear is a false
            # statement to anyone looking at the board.
            if still_down_elsewhere:
                noun = "service is" if still_down_elsewhere == 1 else "services are"
                heading = (
                    "## Outage resolved\nThe services this outage affected are responding"
                    f" again. {still_down_elsewhere} other {noun} still down."
                )
            else:
                heading = "## All clear\nEvery service is responding again."
            messages.append((heading, back))
        if incident_id:
            await db.close_incident(incident_id)

    return messages


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

    still_open = [r for r in rows if r["closed_at"] is None]
    return {
        "open": to_open,
        "close": to_close,
        "silent": silent,
        "all_clear": bool(to_close) and not still_open,
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
