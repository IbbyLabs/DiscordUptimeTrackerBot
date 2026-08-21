import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_uptime_embed import build_cog


def _data(state="UP"):
    return {
        "source": {"name": "Status Tracker"},
        "summary": {"up": 1, "down": 0, "degraded": 0},
        "services": [
            {
                "group": "Core",
                "name": "Alpha",
                "url": "https://a.example",
                "hideFromStatusPage": False,
                "requiresAuth": False,
                "uptimePercent": 100,
                "last": {"state": state, "latency": 10},
            }
        ],
    }


def _render(healthy=None, state="UP"):
    embed = build_cog().create_status_embed(_data(state), summary_mode=False, healthy=healthy)
    parts = [embed.description or ""]
    parts += [f.name or "" for f in embed.fields]
    parts += [str(f.value or "") for f in embed.fields]
    return "\n".join(parts)


def test_default_uses_the_instance_emoji():
    assert "🟣" in _render()


def test_override_reaches_the_rendered_output():
    """The point of the whole change: a guild's emoji appears where the default did."""
    out = _render(healthy="🟢")
    assert "🟢" in out
    assert "🟣" not in out


def test_override_does_not_repaint_a_failure():
    """DOWN is fixed red. A regression guard, not evidence for the change."""
    out = _render(healthy="🟢", state="DOWN")
    assert "🔴" in out
