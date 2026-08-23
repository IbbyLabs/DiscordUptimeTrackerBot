"""Every render that takes the per-guild settings must accept all of them.

`guild_render_settings` returns a dict that call sites spread with `**`, and its
docstring says adding a key "reaches every render without touching them". That
only holds while every consumer accepts the new key. The constructors take
explicit keyword arguments and no `**kwargs`, so a key none of them declares is
a TypeError at render time — in production, on the first board drawn.
"""

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cogs.uptime import UptimeCog
from ui.status_layout import (
    AboutLayout,
    HostLayout,
    IncidentHistoryLayout,
    PanelLayout,
    StatusLayout,
)

# The classes `**settings` is spread into.
CONSUMERS = (StatusLayout, HostLayout, AboutLayout, PanelLayout, IncidentHistoryLayout)


def _keys_returned_by_guild_render_settings() -> set[str]:
    source = inspect.getsource(UptimeCog.guild_render_settings)
    return {
        line.split('"')[1]
        for line in source.splitlines()
        if line.strip().startswith('"') and ":" in line
    }


def test_every_consumer_accepts_every_setting() -> None:
    keys = _keys_returned_by_guild_render_settings()
    assert keys, "found no settings keys; the parser needs updating"
    for cls in CONSUMERS:
        params = inspect.signature(cls.__init__).parameters
        takes_kwargs = any(
            p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
        )
        if takes_kwargs:
            continue
        missing = keys - set(params)
        assert not missing, (
            f"{cls.__name__} does not accept {sorted(missing)}; spreading the "
            f"settings into it raises TypeError when a board is drawn"
        )
