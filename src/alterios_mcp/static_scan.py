from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from .services import SERVICES


COMMON_IGNORED_DIR_NAMES = frozenset({".git", ".venv", "__pycache__", "node_modules"})
GENERATED_IGNORED_DIR_NAMES = frozenset({"artifacts", "data", "dist", "build", "outputs", "site", "work"})
DEFAULT_IGNORED_DIR_NAMES = COMMON_IGNORED_DIR_NAMES | GENERATED_IGNORED_DIR_NAMES

SCANNED_EXTENSIONS = frozenset(
    {
        ".bash",
        ".bat",
        ".c",
        ".cfg",
        ".cmd",
        ".conf",
        ".cpp",
        ".cs",
        ".css",
        ".csv",
        ".go",
        ".h",
        ".hpp",
        ".htm",
        ".html",
        ".ini",
        ".java",
        ".js",
        ".json",
        ".jsonl",
        ".jsx",
        ".kt",
        ".kts",
        ".less",
        ".md",
        ".mdx",
        ".mjs",
        ".php",
        ".ps1",
        ".py",
        ".rb",
        ".rs",
        ".rst",
        ".sass",
        ".scala",
        ".scss",
        ".sh",
        ".sql",
        ".svelte",
        ".swift",
        ".toml",
        ".ts",
        ".tsx",
        ".txt",
        ".vue",
        ".xml",
        ".yaml",
        ".yml",
        ".zsh",
    }
)

SCANNED_FILENAMES = frozenset(
    {
        ".env",
        ".env.example",
        "Dockerfile",
        "Makefile",
    }
)

_QUOTED_API_PATH_RE = re.compile(r"""(?P<quote>["'`])(?P<value>/api/[^"'`\r\n]*)(?P=quote)""")
_LIKELY_SERVICE_RE = re.compile(
    r"""(?P<quote>["'`])(?P<value>(?:get|list|create|update|delete|start|"""
    r"""reassign|message|upload|notify|write)[A-Z][A-Za-z0-9_]{2,})(?P=quote)"""
)
_KNOWN_SERVICE_RE = re.compile(
    r"\b(?P<value>" + "|".join(re.escape(name) for name in sorted(SERVICES, key=len, reverse=True)) + r")\b"
)


def scan_directory(
    target_dir: str | Path,
    *,
    include_generated: bool = False,
) -> dict[str, Any]:
    root = Path(target_dir).resolve()
    if not root.exists():
        raise FileNotFoundError(str(root))
    if not root.is_dir():
        raise NotADirectoryError(str(root))

    files_scanned: list[str] = []
    api_occurrences: dict[str, list[dict[str, Any]]] = {}
    service_occurrences: dict[str, list[dict[str, Any]]] = {}
    seen_services: set[tuple[str, str, int, int]] = set()

    ignored_dir_names = COMMON_IGNORED_DIR_NAMES if include_generated else DEFAULT_IGNORED_DIR_NAMES
    for file_path in _iter_scannable_files(root, ignored_dir_names):
        relative_path = file_path.relative_to(root).as_posix()
        files_scanned.append(relative_path)
        text = file_path.read_text(encoding="utf-8", errors="replace")

        for match in _QUOTED_API_PATH_RE.finditer(text):
            value = match.group("value")
            api_occurrences.setdefault(value, []).append(_occurrence(relative_path, text, match.start("value")))

        for match in _KNOWN_SERVICE_RE.finditer(text):
            _add_service_occurrence(service_occurrences, seen_services, match.group("value"), relative_path, text, match.start("value"))

        for match in _LIKELY_SERVICE_RE.finditer(text):
            _add_service_occurrence(service_occurrences, seen_services, match.group("value"), relative_path, text, match.start("value"))

    return {
        "root": str(root),
        "ignored_dir_names": sorted(ignored_dir_names),
        "files_scanned": files_scanned,
        "api_paths": [
            {"value": value, "occurrences": sorted(occurrences, key=_occurrence_sort_key)}
            for value, occurrences in sorted(api_occurrences.items())
        ],
        "services": [
            {
                "name": name,
                "known": name in SERVICES,
                "occurrences": sorted(occurrences, key=_occurrence_sort_key),
            }
            for name, occurrences in sorted(service_occurrences.items())
        ],
    }


def _iter_scannable_files(root: Path, ignored_dir_names: frozenset[str]) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in ignored_dir_names)
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            if _is_scannable_file(path):
                files.append(path)
    return files


def _is_scannable_file(path: Path) -> bool:
    return path.name in SCANNED_FILENAMES or path.suffix.lower() in SCANNED_EXTENSIONS


def _add_service_occurrence(
    occurrences_by_name: dict[str, list[dict[str, Any]]],
    seen: set[tuple[str, str, int, int]],
    name: str,
    relative_path: str,
    text: str,
    offset: int,
) -> None:
    occurrence = _occurrence(relative_path, text, offset)
    key = (name, occurrence["file"], occurrence["line"], occurrence["column"])
    if key in seen:
        return
    seen.add(key)
    occurrences_by_name.setdefault(name, []).append(occurrence)


def _occurrence(relative_path: str, text: str, offset: int) -> dict[str, Any]:
    line_start = text.rfind("\n", 0, offset) + 1
    return {
        "file": relative_path,
        "line": text.count("\n", 0, offset) + 1,
        "column": offset - line_start + 1,
    }


def _occurrence_sort_key(occurrence: dict[str, Any]) -> tuple[str, int, int]:
    return (occurrence["file"], occurrence["line"], occurrence["column"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Statically scan a tree for Alterios API paths and service calls.")
    parser.add_argument("root", help="Directory to scan.")
    parser.add_argument(
        "--include-generated",
        action="store_true",
        help="Also scan generated/work directories such as artifacts, data, outputs, site, and work.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    try:
        payload = scan_directory(args.root, include_generated=args.include_generated)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"root: {payload['root']}")
        print(f"files scanned: {len(payload['files_scanned'])}")
        print(f"api paths: {len(payload['api_paths'])}")
        print(f"services: {len(payload['services'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
