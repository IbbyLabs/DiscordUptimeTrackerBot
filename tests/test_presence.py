import os

os.environ.setdefault("BOT_TOKEN", "x")
os.environ.setdefault("STATUS_API_URL", "http://localhost/api")

from bot import presence_text


# What it is tracking, rather than how recently we deployed.
def test_a_healthy_estate_reports_the_count() -> None:
    assert presence_text(63, 0, 0) == "All 63 services up"


def test_anything_down_outranks_everything_else() -> None:
    assert presence_text(61, 2, 5) == "2 services down"


def test_degraded_shows_when_nothing_is_down() -> None:
    assert presence_text(60, 0, 3) == "3 services degraded"


def test_one_service_is_not_plural() -> None:
    assert presence_text(62, 1, 0) == "1 service down"
    assert presence_text(62, 0, 1) == "1 service degraded"


# Before the first cycle there is no payload, and inventing a count would read
# as a measurement.
def test_before_the_first_check_it_says_so() -> None:
    assert presence_text(0, 0, 0) == "Waiting for the first check"
