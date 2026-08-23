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
    catalogue_plurals,
    placeholder_faults,
    placeholders,
    source_msgids,
    source_plurals,
)

from babel.messages.catalog import Catalog
from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po

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
        plurals = catalogue_plurals(locale)
        for msgid, forms in catalogue_forms(locale).items():
            faults = placeholder_faults(msgid, forms, plurals.get(msgid))
            assert not faults, f"{locale}: " + "; ".join(faults)
            # The call site supplies every name either msgid can ask for.
            supplied = {
                name: "x" for name in placeholders(msgid) | placeholders(plurals.get(msgid) or "")
            }
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


# A catalogue is keyed by a plural message's singular, so its own plural form is
# carried along unchecked. Rewording one in the source leaves every catalogue
# describing a sentence the bot no longer has.
def test_a_catalogue_records_the_plural_the_source_asks_for() -> None:
    wanted = source_plurals()
    for locale in catalogues():
        have = catalogue_plurals(locale)
        for singular, plural in wanted.items():
            assert have.get(singular) == plural, (
                f"{locale}: {singular!r} has plural {have.get(singular)!r}, "
                f"the source says {plural!r}"
            )


def test_the_plural_guard_catches_a_reworded_plural(tmp_path) -> None:
    root = _fixture(
        tmp_path,
        '_.ngettext("{n} down", "{n} are down", n)\n',
        'msgid "{n} down"\nmsgid_plural "{n} down"\n'
        'msgstr[0] "niedostepna"\nmsgstr[1] "{n} niedostepne"\nmsgstr[2] "{n} niedostepnych"\n',
        header=PLURAL_HEADER,
    )
    assert source_plurals(root)["{n} down"] == "{n} are down"
    assert catalogue_plurals("xx", root / "locales")["{n} down"] == "{n} down"


# An unnumbered singular beside a numbered plural is the ordinary English shape
# — "Last check", "Last {n} checks". Reading only the singular makes every later
# form look like it invented the number.
UNNUMBERED_SINGULAR = (
    'msgid "Last check"\nmsgid_plural "Last {n} checks"\n'
    'msgstr[0] "Ostatnia kontrola"\n'
    'msgstr[1] "Ostatnie {n} kontrole"\n'
    'msgstr[2] "Ostatnich {n} kontroli"\n'
)


def test_a_plural_may_number_forms_its_singular_does_not(tmp_path) -> None:
    root = _fixture(
        tmp_path,
        '_.ngettext("Last check", "Last {n} checks", n)\n',
        UNNUMBERED_SINGULAR,
        header=PLURAL_HEADER,
    )
    locales = root / "locales"
    forms = catalogue_forms("xx", locales)
    plurals = catalogue_plurals("xx", locales)
    assert placeholder_faults("Last check", forms["Last check"], plurals["Last check"]) == []


def test_invention_is_still_caught_when_the_msgids_differ(tmp_path) -> None:
    root = _fixture(
        tmp_path,
        '_.ngettext("Last check", "Last {n} checks", n)\n',
        UNNUMBERED_SINGULAR.replace('msgstr[1] "Ostatnie {n} kontrole"', 'msgstr[1] "Ostatnie {m} kontrole"'),
        header=PLURAL_HEADER,
    )
    locales = root / "locales"
    faults = placeholder_faults(
        "Last check", catalogue_forms("xx", locales)["Last check"], catalogue_plurals("xx", locales)["Last check"]
    )
    assert any("'m'" in f and "uses" in f for f in faults)


def test_a_later_form_still_may_not_drop_the_plural_number(tmp_path) -> None:
    root = _fixture(
        tmp_path,
        '_.ngettext("Last check", "Last {n} checks", n)\n',
        UNNUMBERED_SINGULAR.replace('msgstr[2] "Ostatnich {n} kontroli"', 'msgstr[2] "Ostatnich kontroli"'),
        header=PLURAL_HEADER,
    )
    locales = root / "locales"
    faults = placeholder_faults(
        "Last check", catalogue_forms("xx", locales)["Last check"], catalogue_plurals("xx", locales)["Last check"]
    )
    assert len(faults) == 1 and "drops" in faults[0]


# A language whose nouns do not inflect still has a plural rule, and the header
# has to state the one CLDR gives rather than the one the words suggest.
def test_every_catalogue_declares_the_plural_rule_cldr_gives() -> None:
    import io

    from scripts.i18n_check import LOCALE_DIR, catalogue_path

    for locale in catalogues():
        found = read_po(io.open(catalogue_path(locale, LOCALE_DIR), encoding="utf-8"), locale=locale)
        expected = Catalog(locale=locale)
        assert (found.num_plurals, str(found.plural_expr)) == (
            expected.num_plurals,
            str(expected.plural_expr),
        ), (
            f"{locale}: Plural-Forms says nplurals={found.num_plurals} "
            f"plural={found.plural_expr}, CLDR says nplurals={expected.num_plurals} "
            f"plural={expected.plural_expr}. A wrong rule picks the wrong form for "
            f"some counts even when the forms read alike."
        )
