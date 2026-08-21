import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracker_db import GUILD_SETTING_FIELDS, TrackerDatabase


def _run(coro):
    return asyncio.run(coro)


def _db():
    path = os.path.join(tempfile.mkdtemp(), "tracker.db")
    db = TrackerDatabase(path)
    _run(db.init())
    return db


def test_unset_guild_returns_none():
    db = _db()
    assert _run(db.get_guild_settings("1")) is None


def test_setting_round_trips():
    db = _db()
    _run(db.set_guild_setting("1", "status_emoji", "🟢"))
    assert _run(db.get_guild_settings("1"))["status_emoji"] == "🟢"


def test_unset_field_stays_null_so_it_inherits():
    """A guild that sets one field must not pin the others to a value."""
    db = _db()
    _run(db.set_guild_setting("1", "status_emoji", "🟢"))
    row = _run(db.get_guild_settings("1"))
    assert row["status_page_url"] is None
    # Every column the row carries, so a new one without a reader is caught here.
    assert set(row) == set(GUILD_SETTING_FIELDS)


def test_second_write_updates_rather_than_duplicating():
    db = _db()
    _run(db.set_guild_setting("1", "status_emoji", "🟢"))
    _run(db.set_guild_setting("1", "status_emoji", "🔵"))
    assert _run(db.get_guild_settings("1"))["status_emoji"] == "🔵"
    assert len(_run(db.list_guild_settings())) == 1


def test_unknown_field_is_refused():
    """The column name cannot be bound, so it is whitelisted rather than interpolated."""
    db = _db()
    try:
        _run(db.set_guild_setting("1", "status_emoji = 'x', guild_id", "y"))
    except ValueError:
        return
    raise AssertionError("an unknown field was accepted")


def test_guilds_do_not_share_settings():
    db = _db()
    _run(db.set_guild_setting("1", "status_emoji", "🟢"))
    _run(db.set_guild_setting("2", "status_emoji", "🔴"))
    assert _run(db.get_guild_settings("1"))["status_emoji"] == "🟢"
    assert _run(db.get_guild_settings("2"))["status_emoji"] == "🔴"
