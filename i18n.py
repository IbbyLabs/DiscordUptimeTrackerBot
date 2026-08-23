"""Translating what the bot says to a guild, in the guild's own language.

English lives in the source and is what a missing catalogue falls back to, so a
locale nobody has translated still renders rather than failing.
"""

from __future__ import annotations

import gettext
from functools import lru_cache
from pathlib import Path

DOMAIN = "messages"
LOCALE_DIR = Path(__file__).resolve().parent / "locales"

# Discord hands out BCP-47 ("pt-BR"); gettext wants a directory ("pt_BR").
def _candidates(locale: str) -> list[str]:
    tag = locale.replace("-", "_")
    parts = [tag]
    if "_" in tag:
        parts.append(tag.split("_", 1)[0])
    return parts


class Translator:
    """One guild's language, as a callable so call sites read as `_("text")`."""

    def __init__(self, translations: gettext.NullTranslations, locale: str | None):
        self._t = translations
        self.locale = locale

    def __call__(self, message: str) -> str:
        return self._t.gettext(message)

    def ngettext(self, singular: str, plural: str, n: int) -> str:
        return self._t.ngettext(singular, plural, n)


@lru_cache(maxsize=64)
def translator_for(locale: str | None) -> Translator:
    """The translator for a Discord locale, English when there is no catalogue."""

    if not locale:
        return Translator(gettext.NullTranslations(), None)
    try:
        found = gettext.translation(
            DOMAIN, localedir=str(LOCALE_DIR), languages=_candidates(locale)
        )
    except FileNotFoundError:
        return Translator(gettext.NullTranslations(), None)
    return Translator(found, locale)


def available_locales() -> list[str]:
    """Locales with a compiled catalogue on disk."""

    if not LOCALE_DIR.is_dir():
        return []
    return sorted(
        d.name
        for d in LOCALE_DIR.iterdir()
        if (d / "LC_MESSAGES" / f"{DOMAIN}.mo").is_file()
    )
