"""What the source says without asking for it to be translated.

The catalogue guards read a `.po`, so the strings they can see are the ones
somebody already marked. Nothing there can report a sentence nobody wrapped,
which is how a board ended up half English in a guild set to another language.
"""

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.i18n_unmarked import SOURCES, scan, unmarked

CASE = '''
def render(_, data, lines):
    lines.append({expr})
    return lines
'''


def _case(tmp_path: Path, expr: str) -> list[tuple[int, str]]:
    path = tmp_path / "case.py"
    io.open(path, "w", encoding="utf-8").write(CASE.format(expr=expr))
    return unmarked(path)


def test_nothing_a_member_reads_is_left_unmarked() -> None:
    found = {name: hits for name, hits in scan().items() if hits}
    assert not found, f"unmarked strings: {found}"


def test_every_source_a_guild_reads_is_covered() -> None:
    for name in SOURCES:
        assert (Path(__file__).resolve().parents[1] / name).is_file()


def test_it_reports_a_sentence_nobody_marked(tmp_path) -> None:
    hits = _case(tmp_path, '"The board could not be refreshed."')
    assert [text for _line, text in hits] == ["The board could not be refreshed."]


def test_it_reports_a_sentence_inside_an_f_string(tmp_path) -> None:
    hits = _case(tmp_path, 'f"{len(lines)} panels removed."')
    assert [text for _line, text in hits] == [" panels removed."]


def test_it_stays_quiet_once_the_sentence_is_marked(tmp_path) -> None:
    assert _case(tmp_path, '_("The board could not be refreshed.")') == []


def test_a_field_name_is_not_a_sentence(tmp_path) -> None:
    assert _case(tmp_path, 'data["affectedServices"]') == []


def test_a_state_compared_against_is_not_a_sentence(tmp_path) -> None:
    assert _case(tmp_path, '"UP" if data.get("state") == "DOWN" else "DEGRADED"') == []
