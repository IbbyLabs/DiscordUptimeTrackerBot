"""What the three persistent panels say.

Kept apart from the cog because each one is a rendering decision — what counts,
what it is called, what an empty one reads as — rather than part of the refresh
loop that delivers them.
"""

from typing import Any

import time

from incidents import format_page_incidents, major_incidents

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
    bulletin = cog.bulletin(data)
    specs: list[PanelSpec] = [
        (
            "outages",
            f"## 🔴 Active outages\n{len(outages)} not responding"
            if outages else "## 🟢 Active outages",
            [cog.outage_line(service) for service in outages] or ["Everything is responding."],
            OUTAGE_RED if outages else HEALTHY_GREEN,
        ),
    ]
    # Only when it has something to say. A panel reading "nothing is in
    # maintenance" is one nobody reads on the day it matters.
    if issues or bulletin:
        lines = list(cog.bulletin_lines(bulletin)) if bulletin else []
        if lines and issues:
            lines.append("")
        lines.extend(cog.known_issue_line(service) for service in issues)
        heading = f"## 🛠️ Known issues\n{len(issues)} with a stated reason" if issues \
            else "## 🛠️ Known issues"
        specs.append(("known_issues", heading, lines, MAINTENANCE_AMBER))
    specs.append(
        (
            "history",
            "## 📡 Incident history",
            format_page_incidents(major_incidents(incidents, int(time.time() * 1000))),
            HISTORY_BLURPLE,
        )
    )
    return specs
