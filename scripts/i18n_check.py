"""What the source asks to be translated, and what a catalogue answers with.

Shared by the guard tests and usable by hand:

    python scripts/i18n_check.py

Extraction is babel's, the same tool that writes the catalogues, so the two
cannot disagree about what counts as a message.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from babel.messages.extract import DEFAULT_KEYWORDS, extract_from_dir

# _L wraps command metadata, which Discord localises rather than gettext. The
# strings still belong in the catalogue, so extraction has to know the name.
KEYWORDS = {**DEFAULT_KEYWORDS, "_L": None}
from babel.messages.pofile import read_po

ROOT = Path(__file__).resolve().parents[1]
LOCALE_DIR = ROOT / "locales"
DOMAIN = "messages"
# Skip anything that is not shipped source.
EXCLUDE = ("tests", "scripts", ".venv", "locales", "__pycache__")

PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def source_msgids(root: Path = ROOT) -> set[str]:
    """Every string the source marks for translation."""

    found: set[str] = set()
    for filename, _lineno, message, _comments, _ctx in extract_from_dir(
        str(root),
        method_map=[("**.py", "python")],
        options_map={"**.py": {}},
        keywords=KEYWORDS,
    ):
        if any(part in Path(filename).parts for part in EXCLUDE):
            continue
        if isinstance(message, tuple):
            found.update(m for m in message if m)
        elif message:
            found.add(message)
    return found


def catalogue_path(locale: str, locale_dir: Path = LOCALE_DIR) -> Path:
    return locale_dir / locale / "LC_MESSAGES" / f"{DOMAIN}.po"


def catalogues(locale_dir: Path = LOCALE_DIR) -> list[str]:
    if not locale_dir.is_dir():
        return []
    return sorted(d.name for d in locale_dir.iterdir() if catalogue_path(d.name, locale_dir).is_file())


def catalogue_entries(locale: str, locale_dir: Path = LOCALE_DIR) -> dict[str, list[str]]:
    """msgid -> every translated form, singular and plural."""

    with catalogue_path(locale, locale_dir).open("rb") as handle:
        catalog = read_po(handle)
    out: dict[str, list[str]] = {}
    for message in catalog:
        if not message.id:
            continue
        ids = message.id if isinstance(message.id, tuple) else (message.id,)
        strings = message.string if isinstance(message.string, tuple) else (message.string,)
        out[ids[0]] = [s for s in strings if s]
    return out


def placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text))


def main() -> int:
    ids = source_msgids()
    print(f"source marks {len(ids)} messages")
    for locale in catalogues():
        entries = catalogue_entries(locale)
        missing = ids - set(entries)
        stale = set(entries) - ids
        print(f"  {locale}: {len(entries)} entries, {len(missing)} missing, {len(stale)} stale")
    return 0


if __name__ == "__main__":
    sys.exit(main())
