from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .client import AlteriosConfig, AlteriosConfigError, AlteriosRequestError, redact_sensitive
from .delivery_evidence import validate_delivery_evidence
from .gitea_workboard import GiteaClient, GiteaConfig
from .project_health import run_project_health
from .replay_smoke import run_replay_smoke
from .runtime_info import build_runtime_fingerprint, collect_alterios_mcp_process_snapshot
from .tool_profiles import allowed_tool_names
from .ux_contract import UX_CONTRACT_VERSION


LIVE_TASK_PREFLIGHT_SCHEMA_VERSION = 1
KNOWN_SCENARIO_TOOLS = {
    "alterios_create_material_module",
    "alterios_create_report_tab",
    "alterios_create_process_flow",
    "alterios_fast_live_bulk_manual_script",
    "alterios_fast_live_bulk_process",
    "alterios_fast_live_bulk_delete",
    "alterios_clone_shared_content_type",
    "alterios_ensure_project_icons",
    "alterios_ensure_project_icon_library",
    "typed_write",
}


def run_live_task_preflight(
    *,
    profile: str,
    project_id: str,
    scenario_tool: str | None = None,
    delivery_evidence: dict[str, Any] | None = None,
    expected_fingerprint: str | None = None,
    include_project_health: bool = True,
    refresh_health: bool = False,
    health_cache_ttl_seconds: int | None = None,
    allow_cached_health: bool = True,
    require_clean_health: bool = True,
    include_replay_smoke: bool = True,
    include_live_replay: bool = False,
    require_delivery_evidence: bool = True,
    verify_gitea_evidence: bool = True,
    required_agent_roles: list[str] | None = None,
    allow_closed_work_item: bool = False,
    gitea_dotenv_path: str | None = None,
    artifacts_dir: str | None = None,
) -> dict[str, Any]:
    """Return a read-only go/no-go preflight for an Alterios live task."""
    target_profile = profile.strip()
    target_project_id = project_id.strip()
    if not target_profile:
        raise ValueError("profile is required for live task preflight.")
    if not target_project_id:
        raise ValueError("project_id is required for live task preflight.")

    checks: list[dict[str, Any]] = []
    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    checks.append(
        _target_check(
            profile=target_profile,
            project_id=target_project_id,
            blockers=blockers,
            warnings=warnings,
            include_project_health=include_project_health,
        )
    )
    checks.append(
        _runtime_check(
            expected_fingerprint=expected_fingerprint,
            blockers=blockers,
        )
    )
    checks.append(
        _delivery_evidence_check(
            delivery_evidence=delivery_evidence,
            require_delivery_evidence=require_delivery_evidence,
            verify_gitea_evidence=verify_gitea_evidence,
            required_agent_roles=required_agent_roles,
            allow_closed_work_item=allow_closed_work_item,
            gitea_dotenv_path=gitea_dotenv_path,
            blockers=blockers,
            warnings=warnings,
        )
    )
    checks.append(_scenario_check(scenario_tool=scenario_tool, warnings=warnings))

    if include_project_health:
        checks.append(
            _project_health_check(
                profile=target_profile,
                project_id=target_project_id,
                refresh=refresh_health,
                cache_ttl_seconds=health_cache_ttl_seconds,
                allow_cached_health=allow_cached_health,
                require_clean_health=require_clean_health,
                artifacts_dir=artifacts_dir,
                blockers=blockers,
                warnings=warnings,
            )
        )
    else:
        checks.append({"name": "project_health", "ok": True, "skipped": True, "reason": "include_project_health=false"})

    if include_replay_smoke:
        checks.append(
            _replay_smoke_check(
                profile=target_profile,
                project_id=target_project_id,
                include_live=include_live_replay,
                artifacts_dir=artifacts_dir,
                blockers=blockers,
            )
        )
    else:
        checks.append({"name": "replay_smoke", "ok": True, "skipped": True, "reason": "include_replay_smoke=false"})

    ok = not blockers
    payload = {
        "kind": "alterios_live_task_preflight",
        "schema_version": LIVE_TASK_PREFLIGHT_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "readonly": True,
        "target": {"profile": target_profile, "project_id": target_project_id},
        "scenario_tool": (scenario_tool or "").strip() or None,
        "summary": {
            "ok": ok,
            "status": "ready" if ok else "blocked",
            "check_count": len(checks),
            "blocker_count": len(blockers),
            "warning_count": len(warnings),
        },
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
        "next_actions": _next_actions(ok=ok, blockers=blockers, scenario_tool=scenario_tool),
    }
    return redact_sensitive(payload)


def _target_check(
    *,
    profile: str,
    project_id: str,
    blockers: list[dict[str, str]],
    warnings: list[dict[str, str]],
    include_project_health: bool,
) -> dict[str, Any]:
    try:
        config = AlteriosConfig.from_env(profile=profile).with_project_id(project_id)
    except AlteriosConfigError as exc:
        blockers.append({"code": "config_error", "message": str(exc)})
        return {"name": "target_context", "ok": False, "error": str(exc)}

    missing = config.missing_for_project_call()
    if missing and include_project_health:
        blockers.append(
            {
                "code": "missing_project_config",
                "message": "Project health requires configured Alterios base URL and token.",
            }
        )
    elif missing:
        warnings.append(
            {
                "code": "missing_project_config",
                "message": "Project health is skipped; live reads would need configured Alterios base URL and token.",
            }
        )
    return {
        "name": "target_context",
        "ok": not (missing and include_project_health),
        "profile": profile,
        "project_id": project_id,
        "missing_for_project_call": missing,
    }


def _runtime_check(*, expected_fingerprint: str | None, blockers: list[dict[str, str]]) -> dict[str, Any]:
    runtime = build_runtime_fingerprint(tool_count=_server_tool_count())
    expected = (expected_fingerprint or "").strip()
    matches_expected = not expected or runtime["fingerprint"] == expected
    snapshot = collect_alterios_mcp_process_snapshot(cache_ttl_seconds=15)
    processes = snapshot["processes"]
    instances = snapshot["instances"]
    duplicate_instance_count = max(0, len(instances) - 1)
    ok = not runtime["stale"] and matches_expected and duplicate_instance_count == 0
    if runtime["stale"]:
        blockers.append({"code": "runtime_stale", "message": "Running MCP code/skills fingerprint is stale."})
    if not matches_expected:
        blockers.append({"code": "runtime_fingerprint_mismatch", "message": "Runtime fingerprint does not match expected_fingerprint."})
    if duplicate_instance_count:
        blockers.append({"code": "duplicate_mcp_processes", "message": "Duplicate alterios-mcp processes are running."})
    return {
        "name": "runtime_freshness",
        "ok": ok,
        "fingerprint": runtime["fingerprint"],
        "expected_fingerprint": expected or None,
        "matches_expected": matches_expected,
        "stale": runtime["stale"],
        "git": runtime.get("git"),
        "tool_schema_version": runtime.get("tool_schema_version"),
        "ux_contract_version": runtime.get("ux_contract_version"),
            "process_hygiene": {
                "process_count": len(processes),
                "instance_count": len(instances),
                "duplicate_instance_count": duplicate_instance_count,
                "duplicate_process_count": duplicate_instance_count,
                "cache": snapshot["cache"],
                "cleanup_command": "alterios-runtime-info --processes --cleanup-stale --keep-newest 1 --apply --pretty",
            },
    }


def _delivery_evidence_check(
    *,
    delivery_evidence: dict[str, Any] | None,
    require_delivery_evidence: bool,
    verify_gitea_evidence: bool,
    required_agent_roles: list[str] | None,
    allow_closed_work_item: bool,
    gitea_dotenv_path: str | None,
    blockers: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    evidence = dict(delivery_evidence or {})
    work_item_ref = str(evidence.get("work_item_ref") or "").strip()
    handoffs = [str(item).strip() for item in evidence.get("agent_handoff_refs") or [] if str(item).strip()]
    ux_contract_version = str(evidence.get("ux_contract_version") or "").strip()
    missing: list[str] = []
    if not work_item_ref:
        missing.append("work_item_ref")
    if not handoffs:
        missing.append("agent_handoff_refs")
    if ux_contract_version != UX_CONTRACT_VERSION:
        missing.append("ux_contract_version")

    if missing and require_delivery_evidence:
        blockers.append(
            {
                "code": "delivery_evidence_missing",
                "message": "Live scenario apply requires work item, agent handoffs, and current UX contract version.",
            }
        )
    elif missing:
        warnings.append(
            {
                "code": "delivery_evidence_missing",
                "message": "Delivery evidence is incomplete; apply tools may still block later.",
            }
        )
    receipt: dict[str, Any] | None = None
    if not missing and verify_gitea_evidence:
        receipt = _verify_gitea_delivery_evidence(
            work_item_ref=work_item_ref,
            handoff_refs=handoffs,
            required_agent_roles=required_agent_roles,
            allow_closed_work_item=allow_closed_work_item,
            gitea_dotenv_path=gitea_dotenv_path,
        )
        if not receipt.get("ok"):
            blockers.append(
                {
                    "code": "delivery_evidence_unverified",
                    "message": "Private Gitea work item or structured agent handoffs could not be verified.",
                }
            )
    return {
        "name": "delivery_evidence",
        "ok": (not missing or not require_delivery_evidence) and (receipt is None or bool(receipt.get("ok"))),
        "required": require_delivery_evidence,
        "gitea_verification_required": verify_gitea_evidence,
        "missing": missing,
        "work_item_ref": work_item_ref or None,
        "agent_handoff_count": len(handoffs),
        "ux_contract_version": ux_contract_version or None,
        "expected_ux_contract_version": UX_CONTRACT_VERSION,
        "verification_receipt": receipt,
    }


def _verify_gitea_delivery_evidence(
    *,
    work_item_ref: str,
    handoff_refs: list[str],
    required_agent_roles: list[str] | None,
    allow_closed_work_item: bool,
    gitea_dotenv_path: str | None,
) -> dict[str, Any]:
    config = GiteaConfig.from_env(gitea_dotenv_path or ".env")
    missing = config.missing_for_repo_call()
    if missing:
        return {
            "ok": False,
            "fingerprint": None,
            "verified_roles": [],
            "verified_comment_ids": [],
            "blockers": [{"code": "gitea_config_missing", "missing": missing}],
        }
    configured_roles = os.environ.get("ALTERIOS_MCP_REQUIRED_AGENT_ROLES", "analyst,implementer,verifier")
    roles = required_agent_roles or [role.strip() for role in configured_roles.split(",") if role.strip()]
    return validate_delivery_evidence(
        client=GiteaClient(config),
        work_item_ref=work_item_ref,
        handoff_refs=handoff_refs,
        required_roles=roles,
        allow_closed=allow_closed_work_item,
    )


def _scenario_check(*, scenario_tool: str | None, warnings: list[dict[str, str]]) -> dict[str, Any]:
    tool = (scenario_tool or "").strip()
    if not tool:
        warnings.append({"code": "scenario_tool_missing", "message": "No scenario_tool was provided; preflight is generic."})
        return {"name": "scenario_tool", "ok": True, "warning": "missing", "known": sorted(KNOWN_SCENARIO_TOOLS)}
    known = tool in KNOWN_SCENARIO_TOOLS
    if not known:
        warnings.append({"code": "scenario_tool_unknown", "message": f"Scenario tool {tool!r} is not in the known fast-live list."})
    return {"name": "scenario_tool", "ok": True, "scenario_tool": tool, "known": known}


def _project_health_check(
    *,
    profile: str,
    project_id: str,
    refresh: bool,
    cache_ttl_seconds: int | None,
    allow_cached_health: bool,
    require_clean_health: bool,
    artifacts_dir: str | None,
    blockers: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    try:
        health = run_project_health(
            profile=profile,
            project_id=project_id,
            refresh=refresh,
            use_cache=True,
            write_cache=True,
            cache_ttl_seconds=cache_ttl_seconds,
            include_processes=True,
            include_report_templates=False,
            artifacts_dir=artifacts_dir,
        )
    except (AlteriosConfigError, AlteriosRequestError, ValueError, OSError) as exc:
        blockers.append({"code": "project_health_failed", "message": str(exc)})
        return {"name": "project_health", "ok": False, "error": str(exc)}

    source = str(health.get("source") or "")
    summary = health.get("summary") or {}
    cache = health.get("cache") or {}
    health_ok = bool(summary.get("ok"))
    if source == "cache" and not allow_cached_health:
        blockers.append({"code": "project_health_cache_not_allowed", "message": "Project health used cache, but live refresh is required."})
    elif source == "cache":
        warnings.append(
            {
                "code": "project_health_cache",
                "message": (
                    "Project health used a fresh cached inventory "
                    f"(age={cache.get('age_seconds')}s, ttl={cache.get('ttl_seconds')}s)."
                ),
            }
        )
    if require_clean_health and not health_ok:
        blockers.append({"code": "project_health_errors", "message": "Project health contains blocking errors."})
    return {
        "name": "project_health",
        "ok": (health_ok or not require_clean_health) and (allow_cached_health or source != "cache"),
        "source": source,
        "summary": summary,
        "cache": cache,
        "diff_cache": health.get("diff_cache"),
        "cache_write": health.get("cache_write"),
    }


def _replay_smoke_check(
    *,
    profile: str,
    project_id: str,
    include_live: bool,
    artifacts_dir: str | None,
    blockers: list[dict[str, str]],
) -> dict[str, Any]:
    smoke = run_replay_smoke(
        profile=profile,
        project_id=project_id,
        include_live=include_live,
        expected_tool_count_min=75,
        artifacts_dir=artifacts_dir,
    )
    summary = smoke.get("summary") or {}
    ok = bool(summary.get("ok"))
    if not ok:
        blockers.append({"code": "replay_smoke_failed", "message": "Replay smoke has failed checks."})
    return {
        "name": "replay_smoke",
        "ok": ok,
        "include_live": include_live,
        "summary": summary,
    }


def _next_actions(*, ok: bool, blockers: list[dict[str, str]], scenario_tool: str | None) -> list[str]:
    if ok:
        tool = (scenario_tool or "the target write tool").strip()
        return [
            f"Run {tool} with dry_run=true and review the returned plan_id.",
            "Apply only with dry_run=false, the same plan_id, current delivery_evidence, and ALTERIOS_MCP_ALLOW_WRITE=1.",
            "Record readback/UI evidence in the private work item or local project workspace.",
        ]
    actions = []
    codes = {item["code"] for item in blockers}
    if "runtime_stale" in codes or "duplicate_mcp_processes" in codes:
        actions.append("Refresh runtime: restart Codex/MCP or run alterios-runtime-info cleanup, then rerun preflight.")
    if "missing_project_config" in codes or "project_health_failed" in codes:
        actions.append("Fix profile/project configuration or run with a valid cache/refresh target.")
    if "project_health_errors" in codes:
        actions.append("Repair project health errors or explicitly narrow the write to a safe non-structural change.")
    if "delivery_evidence_missing" in codes:
        actions.append("Create/update private work item and add agent handoff refs plus current ux_contract_version.")
    if "delivery_evidence_unverified" in codes:
        actions.append("Fix the private Gitea issue or structured analyst/implementer/verifier handoffs, then rerun preflight.")
    if "replay_smoke_failed" in codes:
        actions.append("Fix MCP smoke failures before live write.")
    return actions or ["Resolve blockers and rerun preflight."]


def _server_tool_count() -> int | None:
    try:
        source = Path(__file__).with_name("server.py").read_text(encoding="utf-8")
    except OSError:
        return None
    names = re.findall(
        r"^@mcp\.tool\(\)\s*\r?\ndef\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        source,
        flags=re.MULTILINE,
    )
    return len(allowed_tool_names(names))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a fast read-only preflight before Alterios live writes.")
    parser.add_argument("--profile", required=True, help="Explicit Alterios profile.")
    parser.add_argument("--project-id", required=True, help="Explicit Alterios project/workspace id.")
    parser.add_argument("--scenario-tool", help="Target scenario or typed write tool.")
    parser.add_argument("--work-item-ref", help="Private Gitea/local work item reference.")
    parser.add_argument("--agent-handoff-ref", action="append", default=[], help="Agent handoff reference. Repeatable.")
    parser.add_argument("--ux-contract-version", default=UX_CONTRACT_VERSION, help="Expected UX contract version in delivery evidence.")
    parser.add_argument("--expected-fingerprint", help="Expected runtime fingerprint.")
    parser.add_argument("--refresh-health", action="store_true", help="Refresh live project inventory instead of using cache when possible.")
    parser.add_argument("--health-cache-ttl-seconds", type=int, default=None, help="Maximum age of cached project health inventory.")
    parser.add_argument("--no-project-health", action="store_true", help="Skip project health.")
    parser.add_argument("--no-replay-smoke", action="store_true", help="Skip replay smoke.")
    parser.add_argument("--include-live-replay", action="store_true", help="Include read-only live discovery in replay smoke.")
    parser.add_argument("--no-delivery-evidence-required", action="store_true", help="Warn instead of blocking on missing delivery evidence.")
    parser.add_argument("--no-gitea-evidence", action="store_true", help="Skip remote Gitea evidence verification.")
    parser.add_argument("--required-agent-role", action="append", default=[], help="Required verified handoff role. Repeatable.")
    parser.add_argument("--allow-closed-work-item", action="store_true", help="Allow a closed Gitea work item.")
    parser.add_argument("--gitea-dotenv-path", help="Private dotenv path for Gitea configuration.")
    parser.add_argument("--no-clean-health-required", action="store_true", help="Warn through health summary but do not block on health errors.")
    parser.add_argument("--no-cached-health", action="store_true", help="Block if project health uses cached inventory.")
    parser.add_argument("--artifacts-dir", help="Override local artifacts root.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    args = parser.parse_args(argv)

    delivery_evidence = {
        "work_item_ref": args.work_item_ref,
        "agent_handoff_refs": args.agent_handoff_ref,
        "ux_contract_version": args.ux_contract_version,
    }
    payload = run_live_task_preflight(
        profile=args.profile,
        project_id=args.project_id,
        scenario_tool=args.scenario_tool,
        delivery_evidence=delivery_evidence,
        expected_fingerprint=args.expected_fingerprint,
        include_project_health=not args.no_project_health,
        refresh_health=args.refresh_health,
        health_cache_ttl_seconds=args.health_cache_ttl_seconds,
        allow_cached_health=not args.no_cached_health,
        require_clean_health=not args.no_clean_health_required,
        include_replay_smoke=not args.no_replay_smoke,
        include_live_replay=args.include_live_replay,
        require_delivery_evidence=not args.no_delivery_evidence_required,
        verify_gitea_evidence=not args.no_gitea_evidence,
        required_agent_roles=args.required_agent_role or None,
        allow_closed_work_item=args.allow_closed_work_item,
        gitea_dotenv_path=args.gitea_dotenv_path,
        artifacts_dir=args.artifacts_dir,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True))
    return 0 if (payload.get("summary") or {}).get("ok") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
