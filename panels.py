"""What the three persistent panels say.

Kept apart from the cog because each one is a rendering decision — what counts,
what it is called, what an empty one reads as — rather than part of the refresh
loop that delivers them.
"""

from typing import Any

from incidents import format_page_incidents

OUTAGE_RED = 0xD90429
HEALTHY_GREEN = 0x2A9D8F
MAINTENANCE_AMBER = 0xF77F00
HISTORY_BLURPLE = 0x5865F2

PanelSpec = tuple[str, str, list[str], int]


def build_panel_specs(
    cog: Any, data: dict[str, Any], incidents: list[dict[str, Any]]
) -> list[PanelSpec]:
    """One spec per panel: its key, heading, body lines and accent."""

    outages = cog.active_outages(data)
    issues = cog.known_issues(data)
    return [
        (
            "outages",
            f"## 🔴 Active outages\n{len(outages)} not responding"
            if outages else "## 🟢 Active outages",
            [cog.outage_line(service) for service in outages] or ["Everything is responding."],
            OUTAGE_RED if outages else HEALTHY_GREEN,
        ),
        (
            "known_issues",
            f"## 🛠️ Known issues\n{len(issues)} with a stated reason"
            if issues else "## 🛠️ Known issues",
            [cog.known_issue_line(service) for service in issues]
            or ["Nothing is in maintenance."],
            MAINTENANCE_AMBER,
        ),
        (
            "history",
            "## 📡 Incident history",
            format_page_incidents(incidents),
            HISTORY_BLURPLE,
        ),
    ]
