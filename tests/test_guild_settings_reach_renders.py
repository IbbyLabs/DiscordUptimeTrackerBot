"""Guards that a per-guild setting has a reader everywhere it is meant to apply.

A setting with no reader looks identical to a setting that works: the guild sets
it, nothing errors, and the default keeps rendering. Both tests below fail on a
new unrouted site rather than on a named one, so neither carries an allowlist to
fall out of date.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_uptime_embed import build_cog
from tests.test_guild_emoji_render import _data

ROOT = Path(__file__).resolve().parents[1]
# Walked, not listed. Rendering happens wherever someone puts it, and a guard
# scoped to the two files that render today says nothing about the third.
RENDER_SOURCES = sorted(
    path
    for directory in ("cogs", "ui")
    for path in (ROOT / directory).rglob("*.py")
    if path.name != "__init__.py"
)
PER_GUILD_CONFIG = ("STATUS_PAGE_URL", "STATUS_EMOJI")


def test_the_walk_finds_the_render_files():
    """A walk that matches nothing passes every guard below it."""
    names = {p.name for p in RENDER_SOURCES}
    assert "uptime.py" in names, names
    assert len(RENDER_SOURCES) >= 2, names


def _source_lines():
    for path in RENDER_SOURCES:
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            yield path.relative_to(ROOT).as_posix(), number, line


def test_config_defaults_are_only_read_as_a_fallback():
    """`config.X` on the render path must sit behind `or`, never stand alone.

    A bare read is a site the guild override cannot reach. Writing the fallback
    form is what routes it, so satisfying this test is the fix.
    """
    offenders = []
    for name, number, line in _source_lines():
        for field in PER_GUILD_CONFIG:
            for match in re.finditer(rf"[\w.]*\bconfig\.{field}\b", line):
                before = line[: match.start()].rstrip()
                if not before.endswith("or"):
                    offenders.append(f"{name}:{number}: {line.strip()}")
    assert not offenders, "unrouted config read on the render path:\n" + "\n".join(offenders)


def test_every_view_build_passes_the_guilds_settings():
    """Routing the builders is half the job; the callers have to hand them over."""
    joined = "\n".join(p.read_text() for p in RENDER_SOURCES)
    calls = re.findall(
        r"(?<!class )\b(?:Status|Alert)Layout\(((?:[^()]|\([^()]*\))*)\)", joined, re.S
    )
    calls = [c for c in calls if c.strip()]
    assert calls, "found no view builds to check, the pattern has drifted"
    missing = [c for c in calls if "guild_render_settings" not in c and "**settings" not in c]
    assert not missing, "view built without the guild's settings:\n" + "\n\n".join(missing)


def test_page_url_override_reaches_every_link_in_the_view():
    from ui.status_layout import StatusLayout

    view = StatusLayout(
        build_cog(), _data(), group_name="Core", page_url="https://guild.example"
    )
    body = "\n".join(getattr(c, "content", "") or "" for c in view.walk_children())
    body += "\n" + "\n".join(
        str(getattr(c, "url", "") or "") for c in view.walk_children()
    )
    assert "https://guild.example" in body
    assert "status.example.com" not in body
