from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .client import AlteriosClient, AlteriosConfig, AlteriosConfigError, AlteriosRequestError, redact_sensitive, safe_error
from .discovery import discover_readonly
from .form_surface import analyze_form_surface
from .stimulsoft_layout import analyze_stimulsoft_layout
from .write_control import (
    ControlledWriteError,
    WriteOperation,
    assert_write_allowed,
    build_write_audit,
    classify_rest_write_risk,
    controlled_write_result,
)
from .write_plan import assert_plan_matches_audit, load_write_plan


def run_replay_smoke(
    *,
    profile: str | None = None,
    project_id: str | None = None,
    include_live: bool = False,
    expected_tool_count_min: int = 75,
    artifacts_dir: str | None = None,
) -> dict[str, Any]:
    """Run a reproducible read-only/local smoke suite for MCP updates."""
    target_profile = (profile or "local-smoke").strip()
    target_project_id = (project_id or "local-project").strip()
    checks: list[dict[str, Any]] = []
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    old_artifacts_dir = os.environ.get("ALTERIOS_MCP_ARTIFACTS_DIR")
    try:
        if artifacts_dir:
            os.environ["ALTERIOS_MCP_ARTIFACTS_DIR"] = artifacts_dir
        else:
            temp_dir = tempfile.TemporaryDirectory(prefix="alterios-mcp-smoke-")
            os.environ["ALTERIOS_MCP_ARTIFACTS_DIR"] = temp_dir.name

        checks.append(_tool_registry_check(expected_tool_count_min=expected_tool_count_min))
        checks.append(_write_gate_and_plan_check(profile=target_profile, project_id=target_project_id))
        checks.append(_form_surface_check())
        checks.append(_stimulsoft_layout_check())
        checks.append(_risk_classification_check())
        checks.append(
            _live_readonly_check(profile=target_profile, project_id=target_project_id)
            if include_live
            else {"name": "live_readonly_discovery", "ok": True, "skipped": True, "reason": "include_live=false"}
        )
    finally:
        if old_artifacts_dir is None:
            os.environ.pop("ALTERIOS_MCP_ARTIFACTS_DIR", None)
        else:
            os.environ["ALTERIOS_MCP_ARTIFACTS_DIR"] = old_artifacts_dir
        if temp_dir is not None:
            temp_dir.cleanup()

    failed = [check for check in checks if not check.get("ok")]
    skipped = [check for check in checks if check.get("skipped")]
    payload = {
        "kind": "alterios_replay_smoke",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "readonly": True,
        "include_live": include_live,
        "target": {"profile": target_profile, "project_id": target_project_id},
        "summary": {
            "ok": not failed,
            "check_count": len(checks),
            "failed_count": len(failed),
            "skipped_count": len(skipped),
            "failed_checks": [check.get("name") for check in failed],
        },
        "checks": checks,
    }
    return redact_sensitive(payload)


def _tool_registry_check(*, expected_tool_count_min: int) -> dict[str, Any]:
    server_path = Path(__file__).with_name("server.py")
    source = server_path.read_text(encoding="utf-8")
    tool_count = len(re.findall(r"^@mcp\.tool\(\)", source, flags=re.MULTILINE))
    return {
        "name": "mcp_tool_registry",
        "ok": tool_count >= expected_tool_count_min,
        "tool_count": tool_count,
        "expected_tool_count_min": expected_tool_count_min,
        "server_path": str(server_path),
    }


def _write_gate_and_plan_check(*, profile: str, project_id: str) -> dict[str, Any]:
    operation = WriteOperation(
        name="replay_smoke_write_plan",
        kind="replay_smoke",
        risk_level="write",
        summary="Local smoke write-plan contract check; does not call Alterios.",
        method="PATCH",
        path="smoke://write-plan",
        target_ids=("content-1",),
        request={"contentId": "content-1", "token": "secret-token"},
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=True,
        write_enabled=False,
    )
    gate_blocked = False
    try:
        assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=False)
    except ControlledWriteError:
        gate_blocked = True

    result = controlled_write_result(
        audit=audit,
        response={"ok": True, "token": "secret-token"},
    )
    plan = result.get("plan") or {}
    plan_id = str(plan.get("plan_id") or "")
    loaded = load_write_plan(plan_id=plan_id, profile=profile, project_id=project_id)
    matched = assert_plan_matches_audit(plan_id=plan_id, audit=audit.as_dict())
    mismatch_blocked = False
    changed_audit = audit.as_dict()
    changed_audit["operation"] = {**changed_audit["operation"], "request": {"contentId": "content-2"}}
    try:
        assert_plan_matches_audit(plan_id=plan_id, audit=changed_audit)
    except ValueError:
        mismatch_blocked = True

    serialized = json.dumps(loaded, ensure_ascii=False, sort_keys=True)
    sensitive_values_are_redacted = "secret-token" not in serialized and "<redacted>" in serialized
    return {
        "name": "write_gate_and_plan",
        "ok": bool(gate_blocked and plan_id and matched and mismatch_blocked and sensitive_values_are_redacted),
        "gate_blocked_without_env": gate_blocked,
        "plan_id_created": bool(plan_id),
        "plan_status": loaded.get("status"),
        "plan_match_ok": bool(matched),
        "plan_mismatch_blocked": mismatch_blocked,
        "sensitive_values_are_redacted": sensitive_values_are_redacted,
    }


def _form_surface_check() -> dict[str, Any]:
    clean = analyze_form_surface(
        {
            "_id": "form-1",
            "name": "Smoke form",
            "pageTitle": "Smoke form",
            "tabs": [
                {
                    "rows": [
                        {
                            "cells": [
                                {
                                    "type": "view_data_list",
                                    "styles": {"width": "100%"},
                                    "params": {"viewId": "view-1", "openId": True},
                                    "displaying": {"fields": {"name": {"title": "Name"}}},
                                    "valueActionContainers": [
                                        {"title": "Edit", "iconId": "edit", "actions": [{"type": "forms"}]},
                                        {"title": "View", "iconId": "visibility", "actions": [{"type": "forms"}]},
                                        {"title": "Delete", "iconId": "delete", "actions": [{"type": "data_managing"}]},
                                    ],
                                }
                            ]
                        }
                    ]
                }
            ],
        }
    )
    broken = analyze_form_surface(
        {
            "name": "Broken form",
            "tabs": [{"rows": [{"cells": [{"type": "view_data_list", "styles": {}, "displaying": {"fields": {}}}, {}]}]}],
        }
    )
    return {
        "name": "form_surface_validator",
        "ok": clean.get("ok") is True
        and broken.get("ok") is False
        and "missing_view_source" in (broken.get("issues_by_code") or {}),
        "clean_issue_count": clean.get("issue_count"),
        "broken_issue_codes": broken.get("issues_by_code"),
    }


def _stimulsoft_layout_check() -> dict[str, Any]:
    clean = analyze_stimulsoft_layout(
        {
            "Pages": {
                "0": {
                    "Ident": "StiDashboard",
                    "Width": 400,
                    "Height": 240,
                    "Components": {
                        "0": {"Ident": "StiTextElement", "Name": "Title", "ClientRectangle": "10,10,180,30"},
                        "1": {"Ident": "StiTextElement", "Name": "Metric", "ClientRectangle": "10,60,120,40"},
                    },
                }
            }
        }
    )
    overlap = analyze_stimulsoft_layout(
        {
            "Pages": {
                "0": {
                    "Width": 200,
                    "Height": 100,
                    "Components": {
                        "0": {"Ident": "StiText", "Name": "Left", "ClientRectangle": "10,10,80,20"},
                        "1": {"Ident": "StiText", "Name": "Right", "ClientRectangle": "50,10,80,20"},
                    },
                }
            }
        }
    )
    return {
        "name": "stimulsoft_layout_validator",
        "ok": clean.get("ok") is True and "component_overlap" in (overlap.get("issues_by_code") or {}),
        "clean_issue_count": clean.get("issue_count"),
        "overlap_issue_codes": overlap.get("issues_by_code"),
        "render_evidence": {
            "status": "not_collected",
            "note": "This smoke checks static template geometry; browser/PDF/image render proof remains a separate Stage 17 task.",
        },
    }


def _risk_classification_check() -> dict[str, Any]:
    cases = {
        "PATCH /api/reports": classify_rest_write_risk("PATCH", "/api/reports"),
        "DELETE /api/contents/1": classify_rest_write_risk("DELETE", "/api/contents/1"),
        "POST /api/users": classify_rest_write_risk("POST", "/api/users"),
    }
    expected = {
        "PATCH /api/reports": "write",
        "DELETE /api/contents/1": "destructive",
        "POST /api/users": "security",
    }
    return {
        "name": "write_risk_classifier",
        "ok": cases == expected,
        "cases": cases,
    }


def _live_readonly_check(*, profile: str, project_id: str) -> dict[str, Any]:
    if not profile or not project_id:
        return {"name": "live_readonly_discovery", "ok": True, "skipped": True, "reason": "profile/project_id required"}
    try:
        config = AlteriosConfig.from_env(profile=profile).with_project_id(project_id)
        missing = config.missing_for_project_call()
        if missing:
            return {
                "name": "live_readonly_discovery",
                "ok": True,
                "skipped": True,
                "reason": "missing live configuration",
                "missing": missing,
            }
        client = AlteriosClient(config)
        discovery = discover_readonly(client)
    except (AlteriosConfigError, AlteriosRequestError) as exc:
        return {"name": "live_readonly_discovery", "ok": False, "skipped": False, "error": safe_error(str(exc))}
    routes = [route for route in discovery.get("routes") or [] if isinstance(route, dict)]
    ok_routes = [route for route in routes if route.get("ok")]
    failed = [
        {
            "name": route.get("name"),
            "method": route.get("method"),
            "path": route.get("path"),
            "status_code": route.get("status_code"),
            "error": safe_error(route.get("error")) if route.get("error") else None,
        }
        for route in routes
        if not route.get("ok")
    ]
    return {
        "name": "live_readonly_discovery",
        "ok": bool(routes) and len(ok_routes) == len(routes),
        "skipped": False,
        "route_count": len(routes),
        "ok_route_count": len(ok_routes),
        "failed_routes": failed,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# Alterios MCP replay smoke",
        "",
        f"- status: {'OK' if summary.get('ok') else 'FAILED'}",
        f"- checks: {summary.get('check_count', 0)}",
        f"- failed: {summary.get('failed_count', 0)}",
        f"- skipped: {summary.get('skipped_count', 0)}",
        "",
        "| Check | Status | Details |",
        "|---|---|---|",
    ]
    for check in payload.get("checks") or []:
        status = "skipped" if check.get("skipped") else ("ok" if check.get("ok") else "failed")
        details = []
        for key in ("tool_count", "plan_status", "clean_issue_count", "route_count", "ok_route_count"):
            if key in check:
                details.append(f"{key}={check[key]}")
        if check.get("reason"):
            details.append(f"reason={check['reason']}")
        lines.append(f"| `{check.get('name')}` | {status} | {'; '.join(details)} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local/read-only Alterios MCP replay smoke checks.")
    parser.add_argument("--profile", help="Alterios profile for local target labels and optional live discovery.")
    parser.add_argument("--project-id", help="Alterios project id for local target labels and optional live discovery.")
    parser.add_argument("--include-live", action="store_true", help="Also run read-only Alterios discovery.")
    parser.add_argument("--expected-tool-count-min", type=int, default=75)
    parser.add_argument("--artifacts-dir", help="Directory for temporary write-plan smoke artifacts.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    args = parser.parse_args(argv)
    payload = run_replay_smoke(
        profile=args.profile,
        project_id=args.project_id,
        include_live=args.include_live,
        expected_tool_count_min=args.expected_tool_count_min,
        artifacts_dir=args.artifacts_dir,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_markdown(payload), end="")
    return 0 if (payload.get("summary") or {}).get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
