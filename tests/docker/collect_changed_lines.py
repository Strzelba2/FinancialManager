#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

CODE_SUFFIXES = (".py", ".ts", ".tsx")
PRODUCTION_PREFIXES = (
    "stock/app/",
    "wallet/app/",
    "session/userauth/",
    "session/utils/",
    "next-ui/src/",
)


def run_git(root: Path, args: list[str]) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def is_production_code(path: str) -> bool:
    if not path.endswith(CODE_SUFFIXES):
        return False
    if "/tests/" in path or path.startswith("tests/"):
        return False
    return any(path.startswith(prefix) for prefix in PRODUCTION_PREFIXES)


def diff_command() -> tuple[list[str], str]:
    explicit_base = os.environ.get("COVERAGE_DIFF_BASE")
    if explicit_base:
        return ["diff", "--unified=0", "--no-ext-diff", f"{explicit_base}...HEAD", "--"], explicit_base

    github_base = os.environ.get("GITHUB_BASE_REF")
    if github_base:
        base = f"origin/{github_base}"
        return ["diff", "--unified=0", "--no-ext-diff", f"{base}...HEAD", "--"], base

    return ["diff", "--unified=0", "--no-ext-diff", "HEAD", "--"], "HEAD"


def parse_diff(diff_text: str) -> dict[str, set[int]]:
    changed: dict[str, set[int]] = {}
    current_file: str | None = None
    new_lineno: int | None = None

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            if not is_production_code(current_file):
                current_file = None
            elif current_file not in changed:
                changed[current_file] = set()
            new_lineno = None
            continue

        if line.startswith("+++ /dev/null"):
            current_file = None
            new_lineno = None
            continue

        if current_file is None:
            continue

        if line.startswith("@@"):
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            new_lineno = int(match.group(1)) if match else None
            continue

        if new_lineno is None:
            continue

        if line.startswith("+") and not line.startswith("+++"):
            changed[current_file].add(new_lineno)
            new_lineno += 1
        elif line.startswith("-") and not line.startswith("---"):
            continue
        else:
            new_lineno += 1

    return changed


def add_untracked_files(root: Path, changed: dict[str, set[int]]) -> None:
    try:
        untracked = run_git(root, ["ls-files", "--others", "--exclude-standard"]).splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return

    for rel_path in untracked:
        if not is_production_code(rel_path):
            continue
        path = root / rel_path
        try:
            line_count = len(path.read_text(encoding="utf-8").splitlines())
        except UnicodeDecodeError:
            line_count = len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
        except OSError:
            continue
        changed.setdefault(rel_path, set()).update(range(1, line_count + 1))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Repository root.")
    parser.add_argument(
        "--output",
        default="tests/artifacts/coverage-changed-lines.json",
        help="Output JSON path.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)

    command, base = diff_command()
    payload: dict[str, object] = {
        "schema_version": 1,
        "base": base,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": {},
        "error": None,
    }

    try:
        diff_text = run_git(root, command)
        changed = parse_diff(diff_text)
        add_untracked_files(root, changed)
        payload["files"] = {
            path: sorted(lines)
            for path, lines in sorted(changed.items())
            if lines
        }
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        payload["error"] = f"Changed-code coverage input could not be generated: {exc}"

    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
