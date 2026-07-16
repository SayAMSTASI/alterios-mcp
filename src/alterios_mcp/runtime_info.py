from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .ux_contract import UX_CONTRACT_VERSION


PROCESS_STARTED_AT = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
MCP_TOOL_SCHEMA_VERSION = "2026-07-16.1"


def build_runtime_fingerprint(
    *,
    package_root: str | Path | None = None,
    tool_count: int | None = None,
) -> dict[str, Any]:
    root = Path(package_root).resolve() if package_root else Path(__file__).resolve().parent
    current = _capture_identity(root)
    loaded = current if package_root is not None else _LOADED_IDENTITY
    identity = {
        "package_version": __version__,
        "tool_schema_version": MCP_TOOL_SCHEMA_VERSION,
        "ux_contract_version": UX_CONTRACT_VERSION,
        "source_hashes": loaded["source_hashes"],
        "skills_hash": loaded["skills_hash"],
        "git_commit": loaded["git"].get("commit"),
        "tool_count": tool_count,
    }
    fingerprint = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "readonly": True,
        "package_version": __version__,
        "tool_schema_version": MCP_TOOL_SCHEMA_VERSION,
        "ux_contract_version": UX_CONTRACT_VERSION,
        "python_executable": str(Path(sys.executable).resolve()),
        "package_root": str(root),
        "process": {"pid": os.getpid(), "started_at": PROCESS_STARTED_AT},
        "git": loaded["git"],
        "source_hashes": loaded["source_hashes"],
        "skills_hash": loaded["skills_hash"],
        "tool_count": tool_count,
        "fingerprint": fingerprint,
        "stale": loaded["source_hashes"] != current["source_hashes"] or loaded["skills_hash"] != current["skills_hash"],
        "disk": current,
    }


def _capture_identity(root: Path) -> dict[str, Any]:
    repo_root = root.parent.parent
    return {
        "source_hashes": {
            path.relative_to(root).as_posix(): _sha256_file(path)
            for path in sorted(root.rglob("*.py"))
            if path.is_file()
        },
        "skills_hash": _tree_hash(repo_root / "skills"),
        "git": _git_state(repo_root),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_hash(root: Path) -> str | None:
    if not root.is_dir():
        return None
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _git_state(repo_root: Path) -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=5,
            check=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_root,
                text=True,
                encoding="utf-8",
                capture_output=True,
                timeout=5,
                check=True,
            ).stdout.strip()
        )
        return {"available": True, "commit": commit, "dirty": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"available": False, "commit": None, "dirty": None}


_LOADED_IDENTITY = _capture_identity(Path(__file__).resolve().parent)


def main() -> None:
    parser = argparse.ArgumentParser(description="Print the active Alterios MCP runtime fingerprint.")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build_runtime_fingerprint(), ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
