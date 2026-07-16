from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .ux_contract import UX_CONTRACT_VERSION


PROCESS_STARTED_AT = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
MCP_TOOL_SCHEMA_VERSION = "2026-07-16.1"
ALTERIOS_MCP_COMMAND_RE = re.compile(
    r"(?:^|[\\/\s\"'])alterios-mcp(?:\.exe)?(?:$|[\s\"'])|-m\s+alterios_mcp\.server",
    re.IGNORECASE,
)
RUNTIME_INFO_COMMAND_RE = re.compile(r"alterios-runtime-info|runtime_info", re.IGNORECASE)


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


def collect_alterios_mcp_processes() -> list[dict[str, Any]]:
    """Return local OS processes that look like running Alterios MCP servers."""
    rows = _process_rows()
    current_pid = os.getpid()
    processes: list[dict[str, Any]] = []
    for row in rows:
        command_line = str(row.get("command_line") or "")
        if not _is_alterios_mcp_command(command_line):
            continue
        pid = _coerce_int(row.get("pid"))
        processes.append(
            {
                "pid": pid,
                "name": row.get("name"),
                "created_at": row.get("created_at"),
                "command": _redact_process_command(command_line),
                "current_process": pid == current_pid if pid is not None else False,
            }
        )
    return sorted(processes, key=_process_sort_key, reverse=True)


def cleanup_alterios_mcp_processes(
    *,
    keep_newest: int = 1,
    dry_run: bool = True,
) -> dict[str, Any]:
    if keep_newest < 0:
        raise ValueError("keep_newest must be >= 0.")
    processes = collect_alterios_mcp_processes()
    current_pid = os.getpid()
    kept = processes[:keep_newest]
    candidates = [
        process
        for process in processes[keep_newest:]
        if process.get("pid") is not None and process.get("pid") != current_pid
    ]
    stopped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    if not dry_run:
        for process in candidates:
            pid = int(process["pid"])
            try:
                _terminate_process(pid)
                stopped.append(process)
            except (OSError, subprocess.SubprocessError) as exc:
                errors.append({"pid": pid, "error": str(exc)})
    return {
        "dry_run": dry_run,
        "keep_newest": keep_newest,
        "process_count": len(processes),
        "kept": kept,
        "planned_stop": candidates,
        "stopped": stopped,
        "errors": errors,
        "ok": not errors,
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


def _process_rows() -> list[dict[str, Any]]:
    if os.name == "nt":
        return _windows_process_rows()
    return _posix_process_rows()


def _windows_process_rows() -> list[dict[str, Any]]:
    command = (
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,Name,CreationDate,CommandLine | "
        "ConvertTo-Json -Depth 3 -Compress"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=15,
        check=True,
    )
    if not completed.stdout.strip():
        return []
    payload = json.loads(completed.stdout)
    items = payload if isinstance(payload, list) else [payload]
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "pid": item.get("ProcessId"),
                "name": item.get("Name"),
                "created_at": item.get("CreationDate"),
                "command_line": item.get("CommandLine"),
            }
        )
    return rows


def _posix_process_rows() -> list[dict[str, Any]]:
    completed = subprocess.run(
        ["ps", "-eo", "pid=,comm=,lstart=,args="],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=15,
        check=True,
    )
    rows: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        parts = line.strip().split(None, 7)
        if len(parts) < 8:
            continue
        rows.append(
            {
                "pid": parts[0],
                "name": parts[1],
                "created_at": " ".join(parts[2:7]),
                "command_line": parts[7],
            }
        )
    return rows


def _is_alterios_mcp_command(command_line: str) -> bool:
    if not command_line:
        return False
    if RUNTIME_INFO_COMMAND_RE.search(command_line):
        return False
    return bool(ALTERIOS_MCP_COMMAND_RE.search(command_line))


def _redact_process_command(command_line: str) -> str:
    redacted = re.sub(
        r"(?i)(token|password|secret|api[_-]?key|cookie|authorization)=([^\s]+)",
        r"\1=<redacted>",
        command_line,
    )
    return redacted[:500]


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _process_sort_key(process: dict[str, Any]) -> tuple[str, int]:
    return (str(process.get("created_at") or ""), int(process.get("pid") or 0))


def _terminate_process(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=10,
            check=True,
        )
        return
    os.kill(pid, signal.SIGTERM)


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
    parser.add_argument("--processes", action="store_true", help="Include local alterios-mcp process inventory.")
    parser.add_argument(
        "--cleanup-stale",
        action="store_true",
        help="Stop duplicate alterios-mcp processes after keeping the newest N processes.",
    )
    parser.add_argument("--keep-newest", type=int, default=1, help="How many newest alterios-mcp processes to keep.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute cleanup. Without this flag cleanup is a dry-run plan.",
    )
    args = parser.parse_args()
    payload = build_runtime_fingerprint()
    if args.processes or args.cleanup_stale:
        payload["process_hygiene"] = cleanup_alterios_mcp_processes(
            keep_newest=args.keep_newest,
            dry_run=not args.apply,
        ) if args.cleanup_stale else {
            "process_count": len(collect_alterios_mcp_processes()),
            "processes": collect_alterios_mcp_processes(),
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
