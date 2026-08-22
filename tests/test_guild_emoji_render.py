import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_uptime_embed import build_cog
from ui.status_layout import StatusLayout


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
                "displayState": state, "last": {"state": state, "latency": 10},
            }
        ],
    }


def layout_text(view) -> str:
    return "\n".join(getattr(child, "content", "") for child in view.walk_children())


def _render(healthy=None, state="UP", group_name="Core"):
    cog = build_cog()
    return layout_text(
        StatusLayout(cog, _data(state), healthy=healthy, group_name=group_name)
    )


def test_default_uses_the_instance_emoji():
    assert "🟣" in _render()


def test_override_reaches_the_rendered_output():
    """The point of the whole change: a guild's emoji appears where the default did."""
    out = _render(healthy="🟢")
    assert "🟢" in out
    assert "🟣" not in out


def test_override_does_not_repaint_a_failure():
    """DOWN is fixed red. A regression guard, not evidence for the change."""
    assert "🔴" in _render(healthy="🟢", state="DOWN")


def test_the_summary_board_honours_it_too():
    """The detail page and the board are built by different branches."""
    cog = build_cog()
    out = layout_text(StatusLayout(cog, _data(), healthy="🟢"))
    assert "🟢" in out
    assert "🟣" not in out
