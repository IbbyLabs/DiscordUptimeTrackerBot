"""Incident-level alerting.

An outage is one incident rather than a stream of per-service events: it opens
once, names each affected service once, and closes once. A service the incident
has already named stays out of the channel when it flaps, and the panel carries
it instead.
"""

from datetime import datetime, timezone
from typing import Any

AlertChange = dict[str, Any]


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
            messages.append(("## All clear\nEvery affected service is responding again.", back))
        if incident_id:
            await db.close_incident(incident_id)

    return messages


def format_incident_history(incidents: list[dict[str, Any]]) -> list[str]:
    """One line per incident, newest first.

    An open incident is named as ongoing rather than given an end, and the
    services are the ones the incident recorded rather than whatever is down
    now.
    """

    if not incidents:
        return ["No incidents recorded yet."]

    lines: list[str] = []
    for incident in incidents:
        services = [str(row["name"]) for row in incident.get("services", [])]
        shown = ", ".join(services[:5]) or "no services recorded"
        if len(services) > 5:
            shown += f" and {len(services) - 5} more"
        opened = _stamp(str(incident.get("opened_at") or ""))
        closed = incident.get("closed_at")
        when = f"{opened} to {_stamp(str(closed))}" if closed else f"{opened}, ongoing"
        marker = "🟢" if closed else "🔴"
        lines.append(f"{marker} {when}\n-# {shown}")
    return lines


def _stamp(value: str) -> str:
    """SQLite's CURRENT_TIMESTAMP is UTC without a zone, so one is added."""

    for shape in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            moment = datetime.strptime(value, shape).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        return f"<t:{int(moment.timestamp())}:f>"
    return value or "unknown"
