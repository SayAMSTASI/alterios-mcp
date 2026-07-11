from __future__ import annotations

import subprocess
from pathlib import Path


SENSITIVE_LITERALS = (
    "lims." + "artx.ru",
    "lims." + "vniimt.local",
    "4e247a6b-55ef-4665-b88c-" + "3c156fee19ba",
    "40466687-b093-4d80-b4f2-" + "ba0ed0245bfa",
)


def test_tracked_files_do_not_contain_real_system_addresses() -> None:
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    offenders: list[str] = []
    for rel_path in completed.stdout.splitlines():
        path = root / rel_path
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for literal in SENSITIVE_LITERALS:
            if literal in text:
                offenders.append(f"{rel_path}: {literal}")

    assert offenders == []
