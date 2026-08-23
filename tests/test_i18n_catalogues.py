"""The two things that can be checked about a translation without reading it.

Neither says a line means the right thing — only a speaker can. They say the
catalogue answers the same questions the source asks, and that answering cannot
crash.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.i18n_check import (
    catalogue_entries,
    catalogues,
    compiled_entries,
    placeholders,
    source_msgids,
)

from babel.messages.catalog import Catalog
from babel.messages.mofile import write_mo

PO_HEADER = 'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n'


def _fixture(tmp_path: Path, source: str, po_body: str) -> Path:
    (tmp_path / "app.py").write_text(source)
    messages = tmp_path / "locales" / "xx" / "LC_MESSAGES"
    messages.mkdir(parents=True)
    (messages / "messages.po").write_text(PO_HEADER + po_body)
    return tmp_path


def test_every_shipped_catalogue_answers_every_message_the_source_asks() -> None:
    ids = source_msgids()
    for locale in catalogues():
        entries = catalogue_entries(locale)
        missing = ids - set(entries)
        stale = set(entries) - ids
        assert not missing, f"{locale} has no translation for {sorted(missing)[:5]}"
        assert not stale, (
            f"{locale} still translates {sorted(stale)[:5]}, which the source "
            f"no longer says"
        )


def test_a_translation_carries_exactly_the_placeholders_of_its_message() -> None:
    """Both directions. Inventing one raises; dropping one loses the value.

    `"{count} services down"` rendered as `"uslugi niedostepne"` formats without
    complaint and quietly costs the reader the number, which is the half nobody
    who needs the translation can see.
    """

    for locale in catalogues():
        for msgid, strings in catalogue_entries(locale).items():
            expected = placeholders(msgid)
            for translated in strings:
                found = placeholders(translated)
                assert found == expected, (
                    f"{locale}: {translated!r} uses {sorted(found)} where "
                    f"{msgid!r} supplies {sorted(expected)}"
                )
                translated.format(**{name: "x" for name in expected})


# The two above pass on an empty tree, so here is the proof they bite.
def test_the_drift_guard_catches_a_message_with_no_translation(tmp_path) -> None:
    root = _fixture(tmp_path, '_("hello there")\n', '')
    ids = source_msgids(root)
    entries = catalogue_entries("xx", root / "locales")
    assert "hello there" in ids
    assert "hello there" not in entries


def test_the_drift_guard_catches_a_translation_the_source_dropped(tmp_path) -> None:
    root = _fixture(
        tmp_path, "x = 1\n", 'msgid "gone"\nmsgstr "zniknelo"\n'
    )
    stale = set(catalogue_entries("xx", root / "locales")) - source_msgids(root)
    assert stale == {"gone"}


def test_the_placeholder_guard_catches_a_renamed_field(tmp_path) -> None:
    root = _fixture(
        tmp_path,
        '_("{count} down")\n',
        'msgid "{count} down"\nmsgstr "{cont} niedostepne"\n',
    )
    entries = catalogue_entries("xx", root / "locales")
    extra = placeholders(entries["{count} down"][0]) - placeholders("{count} down")
    assert extra == {"cont"}


def test_the_placeholder_guard_catches_a_dropped_field(tmp_path) -> None:
    root = _fixture(
        tmp_path,
        '_("{count} down")\n',
        'msgid "{count} down"\nmsgstr "niedostepne"\n',
    )
    entries = catalogue_entries("xx", root / "locales")
    assert placeholders(entries["{count} down"][0]) != placeholders("{count} down")


# The bot loads messages.mo and the two guards above read messages.po, so a
# catalogue edited and not recompiled passes them while serving the old wording.
def test_the_compiled_catalogue_matches_the_po_it_came_from() -> None:
    for locale in catalogues():
        assert compiled_entries(locale) == catalogue_entries(locale), (
            f"{locale}: messages.mo does not match messages.po, so the bot "
            f"serves something the checks above never saw. Recompile it."
        )


def test_the_compile_guard_catches_a_po_nobody_recompiled(tmp_path) -> None:
    root = _fixture(tmp_path, '_("hello there")\n', 'msgid "hello there"\nmsgstr "bonjour"\n')
    messages = root / "locales" / "xx" / "LC_MESSAGES"
    stale = Catalog(locale="xx")
    stale.add("hello there", "an older wording")
    with (messages / "messages.mo").open("wb") as handle:
        write_mo(handle, stale)
    locales = root / "locales"
    assert compiled_entries("xx", locales) != catalogue_entries("xx", locales)


def test_the_compile_guard_passes_when_they_agree(tmp_path) -> None:
    root = _fixture(tmp_path, '_("hello there")\n', 'msgid "hello there"\nmsgstr "bonjour"\n')
    messages = root / "locales" / "xx" / "LC_MESSAGES"
    fresh = Catalog(locale="xx")
    fresh.add("hello there", "bonjour")
    with (messages / "messages.mo").open("wb") as handle:
        write_mo(handle, fresh)
    locales = root / "locales"
    assert compiled_entries("xx", locales) == catalogue_entries("xx", locales)
