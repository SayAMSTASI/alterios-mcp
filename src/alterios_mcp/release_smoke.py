from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any

from . import __version__
from .doctor import run_doctor
from .replay_smoke import run_replay_smoke
from .tool_profiles import ADMIN_SECURITY_WRITE_TOOL_NAMES, RAW_WRITE_ESCAPE_HATCH_TOOL_NAMES, allowed_tool_names
from .tools import all_tool_names


def run_release_smoke(
    *,
    profile: str | None = None,
    project_id: str | None = None,
    include_live: bool = False,
    require_console_scripts: bool = True,
    measure_startup: bool = True,
) -> dict[str, Any]:
    """Run package-level checks used before publishing a release artifact."""
    names = tuple(all_tool_names())
    profile_names = {
        name: allowed_tool_names(names, name)
        for name in ("full", "live", "discovery", "admin")
    }
    profile_contract = {
        "name": "tool_profiles",
        "ok": (
            len(profile_names["full"]) == len(names)
            and not (set(profile_names["live"]) & RAW_WRITE_ESCAPE_HATCH_TOOL_NAMES)
            and not (set(profile_names["discovery"]) & RAW_WRITE_ESCAPE_HATCH_TOOL_NAMES)
            and ADMIN_SECURITY_WRITE_TOOL_NAMES <= set(profile_names["admin"])
            and "alterios_diagnose_report_viewer" in profile_names["live"]
            and "alterios_diagnose_report_viewer" in profile_names["discovery"]
        ),
        "tool_count": len(names),
        "profile_counts": {name: len(items) for name, items in profile_names.items()},
    }
    doctor = run_doctor(
        require_config=False,
        require_console_scripts=require_console_scripts,
        measure_startup=measure_startup,
        strict_startup=False,
        include_processes=False,
    )
    replay = run_replay_smoke(
        profile=profile,
        project_id=project_id,
        include_live=include_live,
        expected_tool_count_min=len(names),
    )
    checks = [
        {"name": "doctor", "ok": bool((doctor.get("summary") or {}).get("ok")), "details": doctor.get("summary")},
        profile_contract,
        {"name": "replay_smoke", "ok": bool((replay.get("summary") or {}).get("ok")), "details": replay.get("summary")},
    ]
    failed = [check for check in checks if not check.get("ok")]
    return {
        "kind": "alterios_mcp_release_smoke",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "readonly": True,
        "package_version": __version__,
        "summary": {
            "ok": not failed,
            "status": "ready" if not failed else "failed",
            "check_count": len(checks),
            "failed_count": len(failed),
            "failed_checks": [check["name"] for check in failed],
        },
        "checks": checks,
        "doctor": doctor,
        "replay": replay,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# Alterios MCP release smoke",
        "",
        f"- version: {payload.get('package_version')}",
        f"- status: {summary.get('status')}",
        f"- failed: {summary.get('failed_count', 0)}",
        "",
        "| Check | Status |",
        "|---|---|",
    ]
    for check in payload.get("checks") or []:
        lines.append(f"| `{check.get('name')}` | {'ok' if check.get('ok') else 'failed'} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local package checks before an Alterios MCP release.")
    parser.add_argument("--profile")
    parser.add_argument("--project-id")
    parser.add_argument("--include-live", action="store_true")
    parser.add_argument("--skip-console-scripts", action="store_true")
    parser.add_argument("--skip-startup-benchmark", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = run_release_smoke(
        profile=args.profile,
        project_id=args.project_id,
        include_live=args.include_live,
        require_console_scripts=not args.skip_console_scripts,
        measure_startup=not args.skip_startup_benchmark,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else render_markdown(payload), end="\n" if args.json else "")
    return 0 if (payload.get("summary") or {}).get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
