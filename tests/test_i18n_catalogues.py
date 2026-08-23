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
    catalogue_forms,
    placeholder_faults,
    placeholders,
    source_msgids,
)

from babel.messages.catalog import Catalog
from babel.messages.mofile import write_mo

PO_HEADER = 'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
# Three forms, so a fixture can hold a plural entry whose first form is the one
# a count of one selects.
PLURAL_HEADER = (
    'msgid ""\nmsgstr ""\n'
    '"Content-Type: text/plain; charset=UTF-8\\n"\n'
    '"Plural-Forms: nplurals=3; plural=(n==1 ? 0 : n%10>=2 && n%10<=4 ? 1 : 2);\\n"\n\n'
)


def _fixture(tmp_path: Path, source: str, po_body: str, header: str = PO_HEADER) -> Path:
    (tmp_path / "app.py").write_text(source)
    messages = tmp_path / "locales" / "xx" / "LC_MESSAGES"
    messages.mkdir(parents=True)
    (messages / "messages.po").write_text(header + po_body)
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


def test_a_translation_never_invents_a_placeholder_and_drops_one_only_in_a_singular() -> None:
    """The two directions are not the same fault and are not treated alike.

    An invented name raises at render time. A dropped name costs the reader a
    value, which is only acceptable in a plural entry's first form: several
    languages carry a count of one in the grammar rather than in a numeral.
    """

    for locale in catalogues():
        for msgid, forms in catalogue_forms(locale).items():
            faults = placeholder_faults(msgid, forms)
            assert not faults, f"{locale}: " + "; ".join(faults)
            supplied = {name: "x" for name in placeholders(msgid)}
            for _index, _plural, text in forms:
                text.format(**supplied)


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
    forms = catalogue_forms("xx", root / "locales")
    faults = placeholder_faults("{count} down", forms["{count} down"])
    assert faults and "drops" in faults[0]


PLURAL_SOURCE = '_.ngettext("{count} down", "{count} down", n)\n'


def test_a_plural_first_form_may_carry_the_count_in_its_grammar(tmp_path) -> None:
    root = _fixture(
        tmp_path,
        PLURAL_SOURCE,
        'msgid "{count} down"\nmsgid_plural "{count} down"\n'
        'msgstr[0] "niedostepna"\n'
        'msgstr[1] "{count} niedostepne"\n'
        'msgstr[2] "{count} niedostepnych"\n',
        header=PLURAL_HEADER,
    )
    forms = catalogue_forms("xx", root / "locales")
    assert placeholder_faults("{count} down", forms["{count} down"]) == []


def test_a_later_plural_form_may_not_drop_the_count(tmp_path) -> None:
    root = _fixture(
        tmp_path,
        PLURAL_SOURCE,
        'msgid "{count} down"\nmsgid_plural "{count} down"\n'
        'msgstr[0] "niedostepna"\n'
        'msgstr[1] "niedostepne"\n'
        'msgstr[2] "{count} niedostepnych"\n',
        header=PLURAL_HEADER,
    )
    forms = catalogue_forms("xx", root / "locales")
    faults = placeholder_faults("{count} down", forms["{count} down"])
    assert len(faults) == 1 and "drops" in faults[0]


def test_a_plural_form_may_not_invent_a_placeholder(tmp_path) -> None:
    root = _fixture(
        tmp_path,
        PLURAL_SOURCE,
        'msgid "{count} down"\nmsgid_plural "{count} down"\n'
        'msgstr[0] "{cont} niedostepna"\n'
        'msgstr[1] "{count} niedostepne"\n'
        'msgstr[2] "{count} niedostepnych"\n',
        header=PLURAL_HEADER,
    )
    forms = catalogue_forms("xx", root / "locales")
    faults = placeholder_faults("{count} down", forms["{count} down"])
    assert any("cont" in f and "uses" in f for f in faults)


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
