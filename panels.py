"""What the three persistent panels say.

Kept apart from the cog because each one is a rendering decision — what counts,
what it is called, what an empty one reads as — rather than part of the refresh
loop that delivers them.
"""

from typing import Any

from i18n import Translator, translator_for
from incidents import format_page_incidents

OUTAGE_RED = 0xD90429
HEALTHY_GREEN = 0x2A9D8F
MAINTENANCE_AMBER = 0xF77F00
HISTORY_BLURPLE = 0x5865F2

PanelSpec = tuple[str, str, list[str], int]


def _outage_heading(not_responding: int, recovering: int, _: Translator) -> str:
    """Say what is true of each, rather than counting them all as one thing."""

    parts = []
    if not_responding:
        # The board's own summary says this; the same words keep one vocabulary.
        parts.append(
            _.ngettext(
                "{count} service not responding",
                "{count} services not responding",
                not_responding,
            ).format(count=not_responding)
        )
    if recovering:
        parts.append(_("{count} recovering").format(count=recovering))
    if not parts:
        return "## 🟢 " + _("Active outages")
    icon = "🔴" if not_responding else "🟡"
    return f"## {icon} " + _("Active outages") + "\n" + " · ".join(parts)


def _outage_accent(not_responding: int, recovering: int) -> int:
    if not_responding:
        return OUTAGE_RED
    return MAINTENANCE_AMBER if recovering else HEALTHY_GREEN


def build_panel_specs(
    cog: Any,
    data: dict[str, Any],
    incidents: list[dict[str, Any]],
    translate: Translator | None = None,
) -> list[PanelSpec]:
    """One spec per panel: its key, heading, body lines and accent."""

    _ = translate or translator_for(None)

    outages = cog.active_outages(data)
    recovering = cog.recovering_services(data)
    not_responding = len(outages) - len(recovering)
    issues = cog.known_issues(data)
    bulletin = cog.bulletin(data)
    specs: list[PanelSpec] = [
        (
            "outages",
            _outage_heading(not_responding, len(recovering), _),
            [cog.outage_line(service, _) for service in outages]
            or [_("Everything is responding.")],
            _outage_accent(not_responding, len(recovering)),
        ),
    ]
    # Only when it has something to say. A panel reading "nothing is in
    # maintenance" is one nobody reads on the day it matters.
    if issues or bulletin:
        lines = list(cog.bulletin_lines(bulletin, _)) if bulletin else []
        if lines and issues:
            lines.append("")
        lines.extend(cog.known_issue_line(service, _) for service in issues)
        heading = "## 🛠️ " + _("Known issues")
        if issues:
            heading += "\n" + _("{count} with a stated reason").format(count=len(issues))
        specs.append(("known_issues", heading, lines, MAINTENANCE_AMBER))
    specs.append(
        (
            "history",
            "## 📡 " + _("Incident history"),
            format_page_incidents(incidents, translate=_),
            HISTORY_BLURPLE,
        )
    )
    return specs
