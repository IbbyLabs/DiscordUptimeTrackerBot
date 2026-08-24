import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("BOT_TOKEN", "x")
os.environ.setdefault("STATUS_API_URL", "http://localhost/api")

from i18n import translator_for


def test_a_locale_gets_its_own_decimal_mark():
    # A translated sentence carrying an English decimal point reads as a
    # mistake, the same way "98.1 percent" would to an English reader.
    assert translator_for("de").decimal(98.1) == "98,1"
    assert translator_for("fr").decimal(98.1) == "98,1"
    assert translator_for("tr").decimal(98.1) == "98,1"


def test_english_and_no_locale_are_unchanged():
    assert translator_for(None).decimal(98.1) == "98.1"
    assert translator_for("en-GB").decimal(98.1) == "98.1"


def test_an_unknown_locale_falls_back_rather_than_raising():
    assert translator_for("zz-ZZ").decimal(98.1) == "98.1"


def test_the_uptime_line_reads_correctly_in_each_locale():
    _ = translator_for("tr")
    assert _("uptime {percent}%").format(percent=_.decimal(98.1)) == "%98,1 çalışma süresi"
    _ = translator_for(None)
    assert _("uptime {percent}%").format(percent=_.decimal(98.1)) == "uptime 98.1%"
