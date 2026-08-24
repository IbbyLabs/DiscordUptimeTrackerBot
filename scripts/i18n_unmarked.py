"""String literals in the shipped source that no translation call wraps.

The catalogue checks compare code against a `.po`, so their input is the set of
strings someone already marked. This reads every literal instead, which is the
only way an unmarked string is visible to a check at all.

Extraction of what *is* marked comes from babel, the same tool that writes the
catalogues, matched per call site: the same words can be marked in one place and
plain in another, and matching on the text alone calls both of them done.

    python scripts/i18n_unmarked.py
"""

from __future__ import annotations

import ast
import io
import re
import sys
from pathlib import Path

from babel.messages.extract import DEFAULT_KEYWORDS, extract_from_file

ROOT = Path(__file__).resolve().parents[1]
# The two files that write to a guild. Others say nothing a member reads.
SOURCES = ("cogs/uptime.py", "ui/status_layout.py")
KEYWORDS = {**DEFAULT_KEYWORDS, "_L": None}

LOG_OBJECT = re.compile(r"^(log|logger|logging)$")
LOG_METHOD = {"debug", "info", "warning", "error", "exception", "critical"}

# A literal in one of these positions is addressing data, not saying anything.
KEY_METHODS = {
    "get", "setdefault", "pop", "getattr", "hasattr", "startswith", "endswith",
    "split", "join", "strip", "rstrip", "lstrip", "replace", "count", "index", "find",
}
KEY_KWARGS = {"custom_id", "name", "value", "key"}

# Literals that are deliberately English. A payload field name, a state the page
# publishes, a class name, the brand, or a key whose value must not move when a
# catalogue loads. Adding to this list is a decision; a new string arriving
# without one fails the check.
ALLOWED = {
    # what the status page publishes, read by name
    "affectedServices", "changedAt", "coverageStart", "degradedReason", "downSince",
    "generatedAt", "hideFromStatusPage", "historyLimit", "historyTimeline",
    "includeHistory", "includeTimeline", "requiresAuth", "serviceId", "startedAt",
    "updatedAt", "upSince", "uptimePercent", "uptimeWindows", "windowEnd",
    "windowStart",
    # our own identifiers and Discord syntax
    "DiscordUptimeTrackerBot", "HostLayout", "StatusLayout", "UptimeCog", "<:emoji:",
    " • v",
    # the brand
    "IbbyLabs",
    # compared by control flow, so a catalogue must not move them
    "All Systems Operational", "Unknown Service",
    # panel and setting names, and the config attributes they inherit from
    "history", "known_issues", "outages", "locale", "status_emoji", "status_page_url",
    "LOCALE", "STATUS_EMOJI", "STATUS_PAGE_URL",
    # states the page publishes
    "UP", "DOWN", "DEGRADED", "MAINTENANCE", "RECOVERING", "UNKNOWN",
    # window keys, and the compact labels that name them on the uptime line
    "h1", "h12", "h24", "d7", "d30", "recent", "uptime_window_",
    "1h", "12h", "24h", "7d", "30d",
    # Discord timestamp syntax, units and format specs
    "<t:", ":R>", "ms", "ms)\n", ".1f", ".2f",
}


def _parents(tree: ast.AST) -> dict[int, ast.AST]:
    out: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            out[id(child)] = node
    return out


def _addresses_data(node: ast.AST, parents: dict[int, ast.AST]) -> bool:
    """True when the literal names something rather than saying it."""

    up = parents.get(id(node))
    if isinstance(up, (ast.Subscript, ast.Compare)):
        return True
    if isinstance(up, ast.Dict) and any(key is node for key in up.keys):
        return True
    if isinstance(up, ast.keyword) and up.arg in KEY_KWARGS:
        return True
    if isinstance(up, ast.Call):
        name = getattr(up.func, "attr", None) or getattr(up.func, "id", None)
        if name in KEY_METHODS:
            return True
    if isinstance(up, (ast.Tuple, ast.List)):
        return isinstance(parents.get(id(up)), ast.Compare)
    return False


def _skipped(tree: ast.AST) -> set[int]:
    """Nodes inside a translation call or a logger call."""

    out: set[int] = set()

    class Mark(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            hit = name in KEYWORDS or name in LOG_METHOD
            if not hit and isinstance(func, ast.Attribute):
                value = func.value
                hit = isinstance(value, ast.Name) and bool(LOG_OBJECT.match(value.id))
            if hit:
                for sub in ast.walk(node):
                    out.add(id(sub))
            self.generic_visit(node)

    Mark().visit(tree)
    return out


def _docstrings(tree: ast.AST) -> set[int]:
    out: set[int] = set()
    kinds = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, kinds):
            continue
        body = getattr(node, "body", None)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            out.add(id(body[0].value))
    return out


def marked_sites(path: Path) -> set[tuple[int, str]]:
    """(line, message) for everything babel extracts from this file."""

    found: set[tuple[int, str]] = set()
    for lineno, message, _comments, _ctx in extract_from_file(
        "python", str(path), keywords=KEYWORDS
    ):
        parts = message if isinstance(message, tuple) else (message,)
        for part in parts:
            if part:
                found.add((lineno, part))
    return found


def unmarked(path: Path) -> list[tuple[int, str]]:
    """Literals with no marking at their own call site, minus the allowed set."""

    tree = ast.parse(io.open(path, encoding="utf-8").read())
    skip = _skipped(tree) | _docstrings(tree)
    parents = _parents(tree)
    sites = marked_sites(path)
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in skip:
            continue
        value = node.value
        if not value.strip() or value in ALLOWED:
            continue
        # A type annotation arrives as a string; so do a format spec and a URL.
        if not re.search(r"[A-Za-z]", value) or "|" in value:
            continue
        # A printf spec is a percent against its conversion; "% uptime" is a
        # percentage sign in a sentence and belongs in the catalogue.
        if re.match(r"^%\S", value) or value.startswith("http"):
            continue
        if _addresses_data(node, parents):
            continue
        # babel reports the line of the call, which can sit one above its argument.
        if any(abs(node.lineno - line) <= 1 and value == text for line, text in sites):
            continue
        found.append((node.lineno, value))
    return sorted(found)


def scan(root: Path = ROOT) -> dict[str, list[tuple[int, str]]]:
    return {name: unmarked(root / name) for name in SOURCES}


def main() -> int:
    total = 0
    for name, hits in scan().items():
        total += len(hits)
        print(f"=== {name}: {len(hits)} ===")
        for line, value in hits:
            print(f"  {line:5}  {value!r}")
    if total:
        print(
            f"\n{total} unmarked. Wrap it for translation, or add it to ALLOWED in"
            f" {Path(__file__).name} with a reason.",
            file=sys.stderr,
        )
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
