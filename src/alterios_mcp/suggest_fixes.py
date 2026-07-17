from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any

from .client import redact_sensitive
from .doctor import run_doctor


SOLUTION_CATALOG: dict[str, list[dict[str, Any]]] = {
    "python": [
        {
            "id": "create-supported-venv",
            "recommended": True,
            "title": "Create a new virtual environment with Python 3.11 or newer",
            "command": "py -3.13 -m venv <venv>; <venv>\\Scripts\\python.exe -m pip install <release-wheel>",
            "risk": "low",
            "requires_restart": True,
        },
        {
            "id": "select-existing-python",
            "recommended": False,
            "title": "Point the release manager to another installed Python",
            "command": ".\\manage_release.ps1 -Action Install -PythonCommand <python-3.11-or-newer>",
            "risk": "low",
            "requires_restart": True,
        },
    ],
    "console_scripts": [
        {
            "id": "managed-update",
            "recommended": True,
            "title": "Repair the installation with the managed updater",
            "command": "$env:LOCALAPPDATA\\alterios-mcp\\manage_release.ps1 -Action Update",
            "risk": "low",
            "requires_restart": True,
        },
        {
            "id": "force-reinstall-wheel",
            "recommended": False,
            "title": "Force reinstall a verified release wheel",
            "command": "<venv>\\Scripts\\python.exe -m pip install --force-reinstall <release-wheel>",
            "risk": "medium",
            "requires_restart": True,
        },
    ],
    "dotenv": [
        {
            "id": "configure-existing-dotenv",
            "recommended": True,
            "title": "Point MCP to an existing private dotenv file",
            "command": "$env:ALTERIOS_DOTENV_PATH='<private-env-path>'; alterios-doctor --require-config --json",
            "risk": "low",
            "requires_restart": True,
        },
        {
            "id": "create-private-dotenv",
            "recommended": False,
            "title": "Create a private config from .env.example and fill only required profile values",
            "command": "Copy-Item .env.example <private-env-path>",
            "risk": "medium",
            "requires_restart": True,
        },
    ],
    "profiles": [
        {
            "id": "repair-profile-variables",
            "recommended": True,
            "title": "Complete the profile variables reported as missing",
            "command": "alterios-doctor --dotenv-path <private-env-path> --require-config --json",
            "risk": "low",
            "requires_restart": True,
        },
        {
            "id": "use-single-profile",
            "recommended": False,
            "title": "Temporarily select one complete profile while other profiles are repaired",
            "command": "$env:ALTERIOS_PROFILE='<profile>'; alterios-doctor --require-config --json",
            "risk": "medium",
            "requires_restart": True,
        },
    ],
    "tool_profile": [
        {
            "id": "select-live-profile",
            "recommended": True,
            "title": "Use the standard live tool profile",
            "command": "$env:ALTERIOS_MCP_TOOL_PROFILE='live'; alterios-doctor --json",
            "risk": "low",
            "requires_restart": True,
        },
        {
            "id": "select-discovery-profile",
            "recommended": False,
            "title": "Use the smaller read-oriented discovery profile",
            "command": "$env:ALTERIOS_MCP_TOOL_PROFILE='discovery'; alterios-doctor --json",
            "risk": "low",
            "requires_restart": True,
        },
    ],
    "runtime_source": [
        {
            "id": "restart-mcp-client",
            "recommended": True,
            "title": "Restart the MCP client to load the installed package and registry",
            "command": "alterios-runtime-info --processes --pretty",
            "risk": "low",
            "requires_restart": True,
        },
        {
            "id": "managed-reinstall",
            "recommended": False,
            "title": "Reinstall the current release and run release smoke",
            "command": "$env:LOCALAPPDATA\\alterios-mcp\\manage_release.ps1 -Action Update",
            "risk": "medium",
            "requires_restart": True,
        },
    ],
    "startup_import": [
        {
            "id": "inspect-runtime",
            "recommended": True,
            "title": "Inspect startup timing and duplicate MCP instances",
            "command": "alterios-doctor --processes --strict-startup --json",
            "risk": "low",
            "requires_restart": False,
        },
        {
            "id": "repair-release-install",
            "recommended": False,
            "title": "Repair package dependencies from the latest release",
            "command": "$env:LOCALAPPDATA\\alterios-mcp\\manage_release.ps1 -Action Update",
            "risk": "medium",
            "requires_restart": True,
        },
    ],
    "process_hygiene": [
        {
            "id": "restart-single-client",
            "recommended": True,
            "title": "Close duplicate MCP clients and start one client instance",
            "command": "alterios-runtime-info --processes --pretty",
            "risk": "low",
            "requires_restart": True,
        },
        {
            "id": "cleanup-stale-instances",
            "recommended": False,
            "title": "Review and clean stale Alterios MCP instances",
            "command": "alterios-runtime-info --processes --cleanup-stale --keep-newest 1 --pretty",
            "risk": "medium",
            "requires_restart": True,
        },
    ],
}


def build_solution_options(doctor_payload: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    for check in doctor_payload.get("checks") or []:
        if check.get("status") not in {"fail", "warn"}:
            continue
        check_name = str(check.get("name") or "unknown")
        options = [dict(option) for option in SOLUTION_CATALOG.get(check_name, _fallback_options())]
        issues.append(
            {
                "check": check_name,
                "status": check.get("status"),
                "summary": check.get("summary"),
                "options": options,
            }
        )

    if not issues:
        maintenance = [
            {
                "id": "verify-release",
                "recommended": True,
                "title": "Run the complete local release smoke before live work",
                "command": "alterios-release-smoke --json",
                "risk": "low",
                "requires_restart": False,
            },
            {
                "id": "check-for-update",
                "recommended": False,
                "title": "Check whether a newer GitHub Release is available",
                "command": "$env:LOCALAPPDATA\\alterios-mcp\\manage_release.ps1 -Action Check",
                "risk": "low",
                "requires_restart": False,
            },
        ]
    else:
        maintenance = []

    return redact_sensitive(
        {
            "kind": "alterios_mcp_solution_options",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "readonly": True,
            "summary": {
                "ok": not issues,
                "status": "ready" if not issues else "action_required",
                "issue_count": len(issues),
                "option_count": sum(len(item["options"]) for item in issues) + len(maintenance),
            },
            "issues": issues,
            "maintenance_options": maintenance,
            "doctor": doctor_payload.get("summary") or {},
        }
    )


def _fallback_options() -> list[dict[str, Any]]:
    return [
        {
            "id": "collect-diagnostics",
            "recommended": True,
            "title": "Collect sanitized diagnostics and compare with the administrator guide",
            "command": "alterios-doctor --processes --json",
            "risk": "low",
            "requires_restart": False,
        },
        {
            "id": "repair-release-install",
            "recommended": False,
            "title": "Repair the package from the latest verified release",
            "command": "$env:LOCALAPPDATA\\alterios-mcp\\manage_release.ps1 -Action Update",
            "risk": "medium",
            "requires_restart": True,
        },
    ]


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# Alterios MCP solution options",
        "",
        f"- status: {summary.get('status')}",
        f"- issues: {summary.get('issue_count', 0)}",
        f"- options: {summary.get('option_count', 0)}",
    ]
    for issue in payload.get("issues") or []:
        lines.extend(["", f"## {issue.get('check')} ({issue.get('status')})", "", str(issue.get("summary") or "")])
        for option in issue.get("options") or []:
            marker = "recommended" if option.get("recommended") else "alternative"
            lines.extend(
                [
                    "",
                    f"- **{option.get('title')}** ({marker}, risk: {option.get('risk')})",
                    f"  `{option.get('command')}`",
                ]
            )
    if payload.get("maintenance_options"):
        lines.extend(["", "## No blocking issues", ""])
        for option in payload["maintenance_options"]:
            lines.append(f"- **{option.get('title')}**: `{option.get('command')}`")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose Alterios MCP and propose safe solution options.")
    parser.add_argument("--dotenv-path", help="Private Alterios dotenv path. Defaults to ALTERIOS_DOTENV_PATH.")
    parser.add_argument("--require-config", action="store_true")
    parser.add_argument("--skip-console-scripts", action="store_true")
    parser.add_argument("--skip-startup-benchmark", action="store_true")
    parser.add_argument("--startup-budget-seconds", type=float, default=2.0)
    parser.add_argument("--strict-startup", action="store_true")
    parser.add_argument("--processes", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    doctor_payload = run_doctor(
        dotenv_path=args.dotenv_path,
        require_config=args.require_config,
        require_console_scripts=not args.skip_console_scripts,
        measure_startup=not args.skip_startup_benchmark,
        startup_budget_seconds=args.startup_budget_seconds,
        strict_startup=args.strict_startup,
        include_processes=args.processes,
    )
    payload = build_solution_options(doctor_payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else render_markdown(payload), end="\n" if args.json else "")
    return 0 if (payload.get("summary") or {}).get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
