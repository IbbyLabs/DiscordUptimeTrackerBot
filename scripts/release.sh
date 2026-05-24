#!/usr/bin/env bash

set -euo pipefail

usage() {
    echo "Usage: bash scripts/release.sh [patch|minor|major] [--dry-run]"
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
    usage
    exit 1
fi

bump_type="$1"
dry_run="false"

if [[ $# -eq 2 ]]; then
    if [[ "$2" != "--dry-run" ]]; then
        usage
        exit 1
    fi
    dry_run="true"
fi

if [[ "$bump_type" != "patch" && "$bump_type" != "minor" && "$bump_type" != "major" ]]; then
    usage
    exit 1
fi

if ! command -v git >/dev/null 2>&1; then
    echo "git is required"
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required"
    exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
    echo "gh is required to create a GitHub release"
    exit 1
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

notes_file="$(mktemp)"
cleanup() {
    rm -f "$notes_file"
}
trap cleanup EXIT

if [[ -n "$(git status --porcelain)" ]]; then
    if [[ "$dry_run" == "true" ]]; then
        echo "Dry run: working tree is not clean, skipping release safety stop."
    else
        echo "Working tree is not clean. Commit or stash changes before releasing."
        exit 1
    fi
fi

current_branch="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$current_branch" != "main" ]]; then
    if [[ "$dry_run" == "true" ]]; then
        echo "Dry run: current branch is $current_branch, release would require main."
    else
        echo "Release script must be run from main. Current branch: $current_branch"
        exit 1
    fi
fi

previous_tag=""
if git describe --tags --abbrev=0 >/dev/null 2>&1; then
    previous_tag="$(git describe --tags --abbrev=0)"
fi

current_version="$(tr -d '[:space:]' < VERSION)"
if [[ ! "$current_version" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
    echo "VERSION must contain a semantic version like 0.1.0"
    exit 1
fi

major="${BASH_REMATCH[1]}"
minor="${BASH_REMATCH[2]}"
patch="${BASH_REMATCH[3]}"

case "$bump_type" in
    patch)
        patch=$((patch + 1))
        ;;
    minor)
        minor=$((minor + 1))
        patch=0
        ;;
    major)
        major=$((major + 1))
        minor=0
        patch=0
        ;;
esac

next_version="$major.$minor.$patch"
tag="v$next_version"
commit_message="chore(release): $tag"

run_cmd() {
    echo "+ $*"
    if [[ "$dry_run" == "false" ]]; then
        "$@"
    fi
}

echo "Preparing release $tag"
if [[ -n "$previous_tag" ]]; then
    echo "Previous release tag: $previous_tag"
else
    echo "No previous release tag found. Using full commit history."
fi

run_cmd git pull --ff-only origin main
run_cmd python3 -m pytest -q
run_cmd pyright
run_cmd python3 -m compileall -q .

if [[ "$dry_run" == "true" ]]; then
    echo "+ update VERSION to $next_version"
else
    printf '%s\n' "$next_version" > VERSION
fi

if [[ "$dry_run" == "true" ]]; then
    echo "+ python3 scripts/generate_changelog.py --version $next_version --previous-tag ${previous_tag:-<none>} --changelog CHANGELOG.md --notes-file $notes_file"
else
    changelog_args=(
        python3
        scripts/generate_changelog.py
        --version
        "$next_version"
        --changelog
        CHANGELOG.md
        --notes-file
        "$notes_file"
    )
    if [[ -n "$previous_tag" ]]; then
        changelog_args+=(--previous-tag "$previous_tag")
    fi
    "${changelog_args[@]}"
fi

run_cmd git add VERSION CHANGELOG.md
run_cmd git commit -m "$commit_message"
run_cmd git tag -a "$tag" -m "$tag"
run_cmd git push origin main
run_cmd git push origin "$tag"
run_cmd gh release create "$tag" --notes-file "$notes_file" --title "$tag"

echo "Release complete: $tag"
echo "Docker publish workflow will run from the GitHub release event."
