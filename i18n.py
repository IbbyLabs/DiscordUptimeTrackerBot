"""Translating what the bot says to a guild, in the guild's own language.

English lives in the source and is what a missing catalogue falls back to, so a
locale nobody has translated still renders rather than failing.
"""

from __future__ import annotations

import gettext

from babel.core import UnknownLocaleError
from babel.numbers import format_decimal
from functools import lru_cache
from pathlib import Path

import discord

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

    def decimal(self, value: float, places: int = 1) -> str:
        """A number in this locale's own notation.

        Half of Europe writes 98,1 where English writes 98.1, and a translated
        sentence carrying an English decimal point reads as a mistake rather
        than as a style.
        """

        if not self.locale:
            return f"{value:.{places}f}"
        try:
            return format_decimal(
                value, format="#,##0." + "0" * places if places else "#,##0",
                locale=self.locale.replace("-", "_"),
            )
        except (UnknownLocaleError, ValueError):
            return f"{value:.{places}f}"


# Cached for the life of the process. A recompiled catalogue needs a restart to
# take effect; call translator_for.cache_clear() if a reload command is ever added.
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


def has_catalogue(locale: str) -> bool:
    """Whether a locale resolves to a catalogue on disk.

    Uses the same candidate list as translator_for, so what is accepted and
    what is loaded cannot drift apart.
    """

    if not locale:
        return False
    have = set(available_locales())
    return any(candidate in have for candidate in _candidates(locale))


def available_locales() -> list[str]:
    """Locales with a compiled catalogue on disk."""

    if not LOCALE_DIR.is_dir():
        return []
    return sorted(
        d.name
        for d in LOCALE_DIR.iterdir()
        if (d / "LC_MESSAGES" / f"{DOMAIN}.mo").is_file()
    )


class AppCommandTranslator(discord.app_commands.Translator):
    """Command names and descriptions, which Discord localises rather than us.

    These are uploaded at sync time and shown in the viewer's own Discord
    language. The guild `locale` setting does not reach them; it governs what
    the bot writes in a message.
    """

    async def translate(
        self,
        string: discord.app_commands.locale_str,
        locale: discord.Locale,
        context: discord.app_commands.TranslationContextTypes,
    ) -> str | None:
        translated = translator_for(str(locale))(string.message)
        return translated if translated != string.message else None
