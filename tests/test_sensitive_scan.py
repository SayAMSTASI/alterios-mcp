from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_public_tree_has_no_project_data_or_secrets() -> None:
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, "scripts/check_public_tree.py"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
