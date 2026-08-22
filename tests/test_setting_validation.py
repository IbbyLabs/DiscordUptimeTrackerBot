import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cogs.uptime import _SETTING_DEFAULTS, _SETTING_LABELS, validate_guild_setting
from tracker_db import GUILD_SETTING_FIELDS


def test_the_three_field_lists_agree():
    """A field in one list and not another is a setting that half exists."""
    assert set(GUILD_SETTING_FIELDS) == set(_SETTING_DEFAULTS)
    assert set(GUILD_SETTING_FIELDS) == set(_SETTING_LABELS)


def test_a_valid_url_is_accepted():
    cleaned, error = validate_guild_setting("status_page_url", "  https://status.example.com  ")
    assert (cleaned, error) == ("https://status.example.com", None)


def test_a_url_without_a_scheme_is_refused():
    """Discord rejects the embed outright, so every render for the guild would fail."""
    cleaned, error = validate_guild_setting("status_page_url", "status.example.com")
    assert cleaned is None
    assert error


def test_a_non_http_scheme_is_refused():
    for value in ("javascript:alert(1)", "file:///etc/passwd", "ftp://example.com"):
        cleaned, error = validate_guild_setting("status_page_url", value)
        assert cleaned is None, value
        assert error, value


def test_an_overlong_emoji_is_refused():
    cleaned, error = validate_guild_setting("status_emoji", "x" * 65)
    assert cleaned is None
    assert error


def test_an_emoji_is_accepted():
    assert validate_guild_setting("status_emoji", "🟢") == ("🟢", None)


# Fixed rather than configured: an operator cannot point the board at something
# that does not answer in the shape it expects.
def test_the_status_urls_ignore_the_environment(monkeypatch) -> None:
    import importlib

    monkeypatch.setenv("STATUS_API_URL", "https://wrong.example/v1/status")
    monkeypatch.setenv("STATUS_PAGE_URL", "https://wrong.example/")
    monkeypatch.setenv("INCIDENTS_API_URL", "https://wrong.example/v1/incidents")
    monkeypatch.setenv("BOT_TOKEN", "x")

    import config as config_module
    importlib.reload(config_module)
    cfg = config_module.Config()

    assert "wrong.example" not in cfg.STATUS_API_URL
    assert "wrong.example" not in cfg.STATUS_PAGE_URL
    assert "wrong.example" not in cfg.INCIDENTS_API_URL
    assert cfg.STATUS_API_URL.endswith("/v1/status")
    assert cfg.INCIDENTS_API_URL.endswith("/v1/incidents")
