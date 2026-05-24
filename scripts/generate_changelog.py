from __future__ import annotations

import argparse
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def commit_subjects(previous_tag: str | None) -> list[str]:
    git_args = ["log", "--format=%s"]
    if previous_tag:
        git_args.append(f"{previous_tag}..HEAD")
    output = run_git(git_args)
    return [line.strip() for line in output.splitlines() if line.strip()]


def release_section(version: str, previous_tag: str | None, subjects: list[str]) -> str:
    release_date = datetime.now(UTC).date().isoformat()
    lines = [f"## {version} - {release_date}", ""]
    if previous_tag:
        lines.append(f"Changes since {previous_tag}:")
    else:
        lines.append("Initial tracked release changes:")
    lines.append("")
    if subjects:
        lines.extend(f"- {subject}" for subject in subjects)
    else:
        lines.append("- No application commits found since the previous release")
    return "\n".join(lines).strip() + "\n"


def update_changelog(changelog_path: Path, section: str) -> None:
    header = "# Changelog\n\n"
    if changelog_path.exists():
        existing = changelog_path.read_text(encoding="utf-8")
        if existing.startswith(header):
            body = existing[len(header):].lstrip()
        else:
            body = existing.lstrip()
    else:
        body = ""
    new_content = header + section
    if body:
        new_content += "\n" + body.rstrip() + "\n"
    changelog_path.write_text(new_content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--previous-tag")
    parser.add_argument("--changelog", required=True)
    parser.add_argument("--notes-file", required=True)
    args = parser.parse_args()

    subjects = commit_subjects(args.previous_tag)
    section = release_section(args.version, args.previous_tag, subjects)

    changelog_path = Path(args.changelog)
    notes_path = Path(args.notes_file)
    update_changelog(changelog_path, section)
    notes_path.write_text(section, encoding="utf-8")


if __name__ == "__main__":
    main()