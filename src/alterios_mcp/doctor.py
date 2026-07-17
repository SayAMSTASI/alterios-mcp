from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .client import configured_profiles, redact_sensitive, safe_error
from .runtime_info import build_runtime_fingerprint, collect_alterios_mcp_process_snapshot
from .tool_profiles import normalize_tool_profile


MINIMUM_PYTHON = (3, 11)
CONSOLE_SCRIPTS = (
    "alterios-mcp",
    "alterios-doctor",
    "alterios-suggest-fixes",
    "alterios-replay-smoke",
    "alterios-release-smoke",
)


def run_doctor(
    *,
    dotenv_path: str | None = None,
    require_config: bool = False,
    require_console_scripts: bool = True,
    measure_startup: bool = True,
    startup_budget_seconds: float = 2.0,
    strict_startup: bool = False,
    include_processes: bool = False,
) -> dict[str, Any]:
    """Inspect a local Alterios MCP installation without calling Alterios."""
    if startup_budget_seconds <= 0:
        raise ValueError("startup_budget_seconds must be positive.")

    checks: list[dict[str, Any]] = []
    checks.append(
        _check(
            "python",
            "pass" if sys.version_info >= MINIMUM_PYTHON else "fail",
            f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            minimum="3.11",
            executable=str(Path(sys.executable).resolve()),
        )
    )
    checks.append(_check("package", "pass", f"alterios-mcp {__version__}", version=__version__))

    script_paths = {name: _console_script_path(name) for name in CONSOLE_SCRIPTS}
    missing_scripts = [name for name, path in script_paths.items() if path is None]
    script_status = "fail" if require_console_scripts and missing_scripts else ("warn" if missing_scripts else "pass")
    checks.append(
        _check(
            "console_scripts",
            script_status,
            "Console entry points are installed." if not missing_scripts else "Some console entry points are unavailable.",
            paths=script_paths,
            missing=missing_scripts,
        )
    )

    effective_dotenv = dotenv_path or os.environ.get("ALTERIOS_DOTENV_PATH")
    if effective_dotenv:
        dotenv_exists = Path(effective_dotenv).expanduser().is_file()
        checks.append(
            _check(
                "dotenv",
                "pass" if dotenv_exists else "fail",
                "Private dotenv file is available." if dotenv_exists else "Configured dotenv file was not found.",
                configured=True,
                exists=dotenv_exists,
            )
        )
    else:
        checks.append(
            _check(
                "dotenv",
                "fail" if require_config else "warn",
                "ALTERIOS_DOTENV_PATH is not configured; environment-only profiles will still be inspected.",
                configured=False,
                exists=False,
            )
        )

    try:
        profile_matrix = configured_profiles(
            dotenv_path=effective_dotenv if effective_dotenv else None,
        )
        profile_summaries = [
            {
                "profile": item.get("profile"),
                "selected": bool(item.get("selected")),
                "missing_for_instance_call": list(item.get("missing_for_instance_call") or []),
                "missing_for_project_call": list(item.get("missing_for_project_call") or []),
                "has_project_default": bool(item.get("has_project_default")),
            }
            for item in profile_matrix.get("profiles") or []
            if isinstance(item, dict)
        ]
        usable_profiles = [item for item in profile_summaries if not item["missing_for_instance_call"]]
        profiles_status = "pass" if usable_profiles else ("fail" if require_config else "warn")
        checks.append(
            _check(
                "profiles",
                profiles_status,
                f"Configured profiles: {len(profile_summaries)}; usable for instance calls: {len(usable_profiles)}.",
                selected_profile=profile_matrix.get("selected_profile"),
                profiles=profile_summaries,
            )
        )
    except (OSError, ValueError) as exc:
        checks.append(_check("profiles", "fail", "Profile configuration could not be loaded.", error=safe_error(str(exc))))

    try:
        tool_profile = normalize_tool_profile()
        checks.append(_check("tool_profile", "pass", f"Active tool profile: {tool_profile}.", profile=tool_profile))
    except ValueError as exc:
        checks.append(_check("tool_profile", "fail", "Tool profile is invalid.", error=safe_error(str(exc))))

    checks.append(
        _check(
            "write_gates",
            "pass",
            "Write gates inspected; no write was executed.",
            write_enabled=os.environ.get("ALTERIOS_MCP_ALLOW_WRITE") == "1",
            dangerous_write_enabled=os.environ.get("ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE") == "1",
        )
    )

    runtime = build_runtime_fingerprint()
    checks.append(
        _check(
            "runtime_source",
            "fail" if runtime.get("stale") else "pass",
            "Loaded source matches disk." if not runtime.get("stale") else "Loaded source differs from files on disk; restart MCP.",
            fingerprint=runtime.get("fingerprint"),
            stale=bool(runtime.get("stale")),
        )
    )

    if measure_startup:
        checks.append(
            _startup_check(
                budget_seconds=startup_budget_seconds,
                strict=strict_startup,
            )
        )
    else:
        checks.append(_check("startup_import", "skip", "Startup benchmark disabled by caller."))

    if include_processes:
        try:
            snapshot = collect_alterios_mcp_process_snapshot(refresh=True)
            instances = snapshot.get("instances") or []
            duplicate_count = max(0, len(instances) - 1)
            checks.append(
                _check(
                    "process_hygiene",
                    "fail" if duplicate_count else "pass",
                    f"Logical MCP instances: {len(instances)}; duplicates: {duplicate_count}.",
                    process_count=len(snapshot.get("processes") or []),
                    instance_count=len(instances),
                    duplicate_instance_count=duplicate_count,
                    scan_duration_ms=(snapshot.get("cache") or {}).get("scan_duration_ms"),
                )
            )
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            checks.append(_check("process_hygiene", "fail", "Process inventory failed.", error=safe_error(str(exc))))
    else:
        checks.append(_check("process_hygiene", "skip", "OS process inventory disabled by caller."))

    failed = [check for check in checks if check["status"] == "fail"]
    warnings = [check for check in checks if check["status"] == "warn"]
    payload = {
        "kind": "alterios_mcp_doctor",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "readonly": True,
        "summary": {
            "ok": not failed,
            "status": "failed" if failed else ("warning" if warnings else "ready"),
            "check_count": len(checks),
            "failed_count": len(failed),
            "warning_count": len(warnings),
            "failed_checks": [check["name"] for check in failed],
            "warning_checks": [check["name"] for check in warnings],
        },
        "checks": checks,
    }
    return redact_sensitive(payload)


def _startup_check(*, budget_seconds: float, strict: bool) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [sys.executable, "-c", "import alterios_mcp.server"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=max(10.0, budget_seconds * 5),
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return _check("startup_import", "fail", "Server import benchmark failed.", error=safe_error(str(exc)))
    duration = round(time.perf_counter() - started, 3)
    if completed.returncode != 0:
        return _check(
            "startup_import",
            "fail",
            "Server import failed in a clean subprocess.",
            duration_seconds=duration,
            error=safe_error(completed.stderr.strip()),
        )
    within_budget = duration <= budget_seconds
    return _check(
        "startup_import",
        "pass" if within_budget else ("fail" if strict else "warn"),
        f"Server import completed in {duration:.3f} seconds (budget {budget_seconds:.3f}).",
        duration_seconds=duration,
        budget_seconds=budget_seconds,
        within_budget=within_budget,
        strict=strict,
    )


def _console_script_path(name: str) -> str | None:
    resolved = shutil.which(name)
    if resolved:
        return str(Path(resolved).resolve())
    scripts_dir = Path(sys.executable).resolve().parent
    candidates = [scripts_dir / name]
    if os.name == "nt":
        candidates.insert(0, scripts_dir / f"{name}.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def _check(name: str, status: str, summary: str, **details: Any) -> dict[str, Any]:
    return {"name": name, "status": status, "ok": status in {"pass", "skip", "warn"}, "summary": summary, **details}


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# Alterios MCP doctor",
        "",
        f"- status: {summary.get('status')}",
        f"- failed: {summary.get('failed_count', 0)}",
        f"- warnings: {summary.get('warning_count', 0)}",
        "",
        "| Check | Status | Summary |",
        "|---|---|---|",
    ]
    for check in payload.get("checks") or []:
        lines.append(f"| `{check.get('name')}` | {check.get('status')} | {check.get('summary')} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose a local Alterios MCP installation without writing data.")
    parser.add_argument("--dotenv-path", help="Private Alterios dotenv path. Defaults to ALTERIOS_DOTENV_PATH.")
    parser.add_argument("--require-config", action="store_true", help="Fail when no usable Alterios profile is configured.")
    parser.add_argument("--skip-console-scripts", action="store_true", help="Do not require installed console entry points.")
    parser.add_argument("--skip-startup-benchmark", action="store_true")
    parser.add_argument("--startup-budget-seconds", type=float, default=2.0)
    parser.add_argument("--strict-startup", action="store_true", help="Fail instead of warn when startup exceeds the budget.")
    parser.add_argument("--processes", action="store_true", help="Include the slower local process inventory.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    args = parser.parse_args(argv)
    payload = run_doctor(
        dotenv_path=args.dotenv_path,
        require_config=args.require_config,
        require_console_scripts=not args.skip_console_scripts,
        measure_startup=not args.skip_startup_benchmark,
        startup_budget_seconds=args.startup_budget_seconds,
        strict_startup=args.strict_startup,
        include_processes=args.processes,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else render_markdown(payload), end="\n" if args.json else "")
    return 0 if (payload.get("summary") or {}).get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
