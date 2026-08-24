import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("BOT_TOKEN", "x")
os.environ.setdefault("STATUS_API_URL", "http://localhost/api")

from cogs.uptime import UptimeCog
from tracker_db import GUILD_SETTING_FIELDS


def _set_choice_values() -> set[str]:
    """The values /tracker set offers, read off the decorated command."""
    command = UptimeCog.set_setting
    for param in command.parameters:
        if param.name == "field":
            return {choice.value for choice in param.choices}
    raise AssertionError("/tracker set has no 'field' parameter")


def test_every_setting_can_be_changed():
    # /tracker settings lists GUILD_SETTING_FIELDS, so a field missing from the
    # choices below is shown to an operator with no way to change it. `locale`
    # shipped like that: thirteen languages, and the control that picks them
    # was unreachable.
    missing = set(GUILD_SETTING_FIELDS) - _set_choice_values()
    assert not missing, f"displayed by /tracker settings but not offered by /tracker set: {sorted(missing)}"


def test_no_choice_points_at_a_setting_that_does_not_exist():
    unknown = _set_choice_values() - set(GUILD_SETTING_FIELDS)
    assert not unknown, f"offered by /tracker set but not a real setting: {sorted(unknown)}"
