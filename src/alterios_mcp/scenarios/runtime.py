from __future__ import annotations

from .._support import *

def alterios_config(profile: str | None = None) -> dict[str, Any]:
    """Return redacted Alterios configuration and missing required values."""
    config = AlteriosConfig.from_env(profile=profile)
    return {
        "config": config.redacted(),
        "missing_for_instance_call": config.missing_for_instance_call(),
        "missing_for_project_call": config.missing_for_project_call(),
        "missing_for_script_call": config.missing_for_script_call(),
        "write_enabled": _write_enabled(),
    }

def alterios_runtime_info(
    expected_fingerprint: str | None = None,
    include_processes: bool = False,
    refresh_processes: bool = False,
    process_cache_ttl_seconds: int = 15,
    include_process_details: bool = False,
) -> dict[str, Any]:
    """Return the active MCP source/skills/tool-schema fingerprint and stale-process status."""
    started = time.perf_counter()
    runtime = _runtime_fingerprint()
    source_hashes = runtime.pop("source_hashes", {})
    disk = runtime.get("disk") if isinstance(runtime.get("disk"), dict) else {}
    disk_source_hashes = disk.pop("source_hashes", {}) if isinstance(disk, dict) else {}
    runtime["source_summary"] = {
        "loaded_file_count": len(source_hashes),
        "disk_file_count": len(disk_source_hashes),
        "loaded_digest": _hash_mapping(source_hashes),
        "disk_digest": _hash_mapping(disk_source_hashes),
    }
    expected = (expected_fingerprint or "").strip()
    runtime["expected_fingerprint"] = expected or None
    runtime["matches_expected"] = not expected or runtime["fingerprint"] == expected
    if include_processes:
        snapshot = collect_alterios_mcp_process_snapshot(
            refresh=refresh_processes,
            cache_ttl_seconds=process_cache_ttl_seconds,
        )
        processes = snapshot["processes"]
        instances = snapshot["instances"]
        duplicate_process_count = sum(int(item.get("process_count") or 0) for item in instances[1:])
        runtime["process_hygiene"] = {
            "process_count": len(processes),
            "instance_count": len(instances),
            "duplicate_instance_count": max(0, len(instances) - 1),
            "duplicate_process_count": duplicate_process_count,
            "cache": snapshot["cache"],
            "cleanup_command": "alterios-runtime-info --processes --cleanup-stale --keep-newest 1 --apply --pretty",
        }
        if include_process_details:
            runtime["process_hygiene"].update({"processes": processes, "instances": instances})
    runtime["ok"] = not runtime["stale"] and runtime["matches_expected"]
    if include_processes and runtime["process_hygiene"]["duplicate_process_count"]:
        runtime["ok"] = False
    runtime["timing_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return runtime


def _hash_mapping(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()

def alterios_ux_contract() -> dict[str, Any]:
    """Return the active machine-readable Alterios UX contract."""
    return {
        "readonly": True,
        "version": UX_CONTRACT_VERSION,
        "blocking_form_issue_codes": sorted(BLOCKING_FORM_ISSUE_CODES),
        "blocking_module_issue_codes": sorted(BLOCKING_MODULE_ISSUE_CODES),
        "scenario_apply_requires": list(SCENARIO_APPLY_REQUIRES),
        "printable_report_default": PRINTABLE_REPORT_DEFAULT,
    }

def _resource_fingerprint(resource: dict[str, Any], keys: tuple[str, ...]) -> str:
    payload = {key: resource.get(key) for key in keys}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()

def alterios_tool_profile() -> dict[str, Any]:
    """Return the active MCP tool profile and filtered registry summary."""
    profile = _ACTIVE_TOOL_PROFILE or build_tool_profile_summary(_decorated_tool_names())
    return {"readonly": True, **profile}

def alterios_verify_delivery_evidence(
    work_item_ref: str,
    agent_handoff_refs: list[str],
    required_roles: list[str] | None = None,
    allow_closed: bool = False,
    dotenv_path: str | None = None,
) -> dict[str, Any]:
    """Verify a private Gitea work item and structured agent handoff comments."""
    receipt = _verify_delivery_evidence(
        work_item_ref=work_item_ref,
        handoff_refs=agent_handoff_refs,
        required_roles=required_roles,
        allow_closed=allow_closed,
        dotenv_path=dotenv_path,
    )
    return {"readonly": True, **receipt}

def alterios_live_task_preflight(
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
) -> dict[str, Any]:
    """Run a fast read-only go/no-go preflight before an Alterios live write task."""
    return run_live_task_preflight(
        profile=profile,
        project_id=project_id,
        scenario_tool=scenario_tool,
        delivery_evidence=delivery_evidence,
        expected_fingerprint=expected_fingerprint,
        include_project_health=include_project_health,
        refresh_health=refresh_health,
        health_cache_ttl_seconds=health_cache_ttl_seconds,
        allow_cached_health=allow_cached_health,
        require_clean_health=require_clean_health,
        include_replay_smoke=include_replay_smoke,
        include_live_replay=include_live_replay,
        require_delivery_evidence=require_delivery_evidence,
        verify_gitea_evidence=verify_gitea_evidence,
        required_agent_roles=required_agent_roles,
        allow_closed_work_item=allow_closed_work_item,
        gitea_dotenv_path=gitea_dotenv_path,
    )

def alterios_list_profiles(profile: str | None = None) -> dict[str, Any]:
    """Return configured Alterios instance profiles with redacted settings and missing values."""
    return configured_profiles(selected_profile=profile)

__all__ = ['alterios_config', 'alterios_runtime_info', 'alterios_ux_contract', 'alterios_tool_profile', 'alterios_verify_delivery_evidence', 'alterios_live_task_preflight', 'alterios_list_profiles']
