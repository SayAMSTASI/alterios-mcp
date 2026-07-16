from __future__ import annotations

from .._support import *
from .processes import alterios_create_process_flow
from .reports import alterios_create_report_tab
from .runtime import _resource_fingerprint
from .views_forms import alterios_create_material_module

def alterios_fast_live_write(
    scenario_tool: str,
    scenario_args: dict[str, Any],
    delivery_evidence: dict[str, Any],
    profile: str,
    project_id: str,
    expected_runtime_fingerprint: str | None = None,
    dry_run: bool = True,
    plan_id: str | None = None,
    refresh_health: bool = False,
    health_cache_ttl_seconds: int | None = None,
    allow_cached_health: bool = True,
    require_clean_health: bool = True,
    include_replay_smoke: bool = False,
) -> dict[str, Any]:
    """Plan or apply one approved scenario through the fast live-write workflow."""
    return run_fast_live_write(
        scenario_tool=scenario_tool,
        scenario_args=scenario_args,
        profile=profile,
        project_id=project_id,
        delivery_evidence=delivery_evidence,
        expected_runtime_fingerprint=expected_runtime_fingerprint,
        dry_run=dry_run,
        plan_id=plan_id,
        refresh_health=refresh_health,
        health_cache_ttl_seconds=health_cache_ttl_seconds,
        allow_cached_health=allow_cached_health,
        require_clean_health=require_clean_health,
        include_replay_smoke=include_replay_smoke,
        scenario_runners={
            "alterios_create_material_module": alterios_create_material_module,
            "alterios_create_report_tab": alterios_create_report_tab,
            "alterios_create_process_flow": alterios_create_process_flow,
        },
    )

def _fast_bulk_preflight(
    *,
    scenario_tool: str,
    delivery_evidence: dict[str, Any],
    profile: str,
    project_id: str,
    expected_runtime_fingerprint: str | None,
    dry_run: bool,
    refresh_health: bool,
    health_cache_ttl_seconds: int | None,
    allow_cached_health: bool,
    require_clean_health: bool,
    include_replay_smoke: bool,
) -> tuple[dict[str, Any], str]:
    preflight = run_live_task_preflight(
        profile=profile,
        project_id=project_id,
        scenario_tool=scenario_tool,
        delivery_evidence=delivery_evidence,
        expected_fingerprint=expected_runtime_fingerprint,
        include_project_health=True,
        refresh_health=refresh_health,
        health_cache_ttl_seconds=health_cache_ttl_seconds,
        allow_cached_health=allow_cached_health,
        require_clean_health=require_clean_health,
        include_replay_smoke=include_replay_smoke,
        include_live_replay=False,
        require_delivery_evidence=True,
        verify_gitea_evidence=dry_run,
        required_agent_roles=None,
        allow_closed_work_item=False,
        gitea_dotenv_path=None,
        artifacts_dir=None,
    )
    runtime_check = next(
        (item for item in preflight.get("checks", []) if item.get("name") == "runtime_freshness"),
        {},
    )
    fingerprint = str(runtime_check.get("fingerprint") or expected_runtime_fingerprint or "").strip()
    return preflight, fingerprint

def _blocked_fast_bulk_result(
    *,
    kind: str,
    profile: str,
    project_id: str,
    preflight: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "mode": "plan" if dry_run else "apply",
        "status": "blocked",
        "target": {"profile": profile, "project_id": project_id},
        "preflight": preflight,
    }

def alterios_fast_live_bulk_manual_script(
    script_id: str,
    selected_content_ids: list[str],
    delivery_evidence: dict[str, Any],
    profile: str,
    project_id: str,
    expected_count: int,
    expected_content_type_id: str,
    shared_args: dict[str, Any] | None = None,
    content_arg_name: str = "contentId",
    expected_script_name: str | None = None,
    expected_script_active: bool = True,
    max_count: int = 100,
    readback_content: bool = True,
    stop_on_error: bool = True,
    expected_runtime_fingerprint: str | None = None,
    dry_run: bool = True,
    plan_id: str | None = None,
    refresh_health: bool = False,
    health_cache_ttl_seconds: int | None = None,
    allow_cached_health: bool = True,
    require_clean_health: bool = True,
    include_replay_smoke: bool = False,
) -> dict[str, Any]:
    """Plan or execute one reviewed manual script for selected content rows."""
    if not looks_like_uuid(script_id):
        raise ValueError("script_id must be a saved manual script UUID.")
    normalized_content_type_id = str(expected_content_type_id or "").strip()
    if not normalized_content_type_id:
        raise ValueError("expected_content_type_id is required for bulk manual-script execution.")
    normalized_arg_name = str(content_arg_name or "").strip()
    if not normalized_arg_name:
        raise ValueError("content_arg_name must not be empty.")
    normalized_shared_args = dict(shared_args or {})
    if normalized_arg_name in normalized_shared_args:
        raise ValueError("shared_args must not contain content_arg_name; it is assigned per selected row.")
    content_ids = normalize_bulk_ids(
        selected_content_ids,
        expected_count=expected_count,
        max_count=max_count,
    )
    if not dry_run and not str(plan_id or "").strip():
        raise ValueError("plan_id is required when dry_run=false for bulk manual-script execution.")
    preflight, runtime_fingerprint = _fast_bulk_preflight(
        scenario_tool="alterios_fast_live_bulk_manual_script",
        delivery_evidence=delivery_evidence,
        profile=profile,
        project_id=project_id,
        expected_runtime_fingerprint=expected_runtime_fingerprint,
        dry_run=dry_run,
        refresh_health=refresh_health,
        health_cache_ttl_seconds=health_cache_ttl_seconds,
        allow_cached_health=allow_cached_health,
        require_clean_health=require_clean_health,
        include_replay_smoke=include_replay_smoke,
    )
    if not bool((preflight.get("summary") or {}).get("ok")):
        return _blocked_fast_bulk_result(
            kind="alterios_fast_live_bulk_manual_script",
            profile=profile,
            project_id=project_id,
            preflight=preflight,
            dry_run=dry_run,
        )

    client = _client(profile, project_id)
    script = _find_script(client, script_id=script_id)
    if not script:
        raise ValueError(f"Script {script_id!r} was not found.")
    if script.get("type") != "manual":
        raise ValueError(f"Script {script_id!r} has type {script.get('type')!r}; expected 'manual'.")
    if expected_script_name and script.get("name") != expected_script_name:
        raise ValueError(
            f"Script name mismatch: expected {expected_script_name!r}, got {script.get('name')!r}."
        )
    if script.get("active") is not expected_script_active:
        raise ValueError(
            f"Script active mismatch: expected {expected_script_active!r}, got {script.get('active')!r}."
        )
    declared_arguments = script_argument_keys(script)
    provided_arguments = set(normalized_shared_args) | {normalized_arg_name}
    missing_arguments = sorted(declared_arguments - provided_arguments)
    if missing_arguments:
        raise ValueError(
            "Bulk manual script arguments are missing declared keys: " + ", ".join(missing_arguments) + "."
        )
    targets = load_bulk_content_targets(
        client,
        content_ids,
        expected_content_type_id=normalized_content_type_id,
    )
    script_fingerprint = _resource_fingerprint(
        script,
        ("_id", "name", "type", "active", "value", "config", "librariesIds", "apiKey"),
    )
    operation = _resource_operation(
        name="POST /api/scripts/execute-manual x selected",
        kind="bulk_manual_script",
        method="POST",
        path="/api/scripts/execute-manual",
        summary="Execute one verified manual script for explicitly selected content rows.",
        request={
            "scriptId": script_id,
            "scriptFingerprint": script_fingerprint,
            "selectedContentIds": content_ids,
            "sharedArgs": normalized_shared_args,
            "contentArgName": normalized_arg_name,
            "expectedContentTypeId": normalized_content_type_id,
            "readbackContent": readback_content,
            "stopOnError": stop_on_error,
            "runtimeFingerprint": runtime_fingerprint,
            "deliveryEvidence": delivery_evidence,
        },
        risk_level="manual_script",
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
    )
    response_payload: dict[str, Any] = {
        "preflight": preflight,
        "runtime_fingerprint": runtime_fingerprint,
        "script": _resource_summary(script),
        "script_fingerprint": script_fingerprint,
        "argument_contract": {
            "declared": sorted(declared_arguments),
            "provided": sorted(provided_arguments),
            "extra": sorted(provided_arguments - declared_arguments) if declared_arguments else [],
        },
        "selected_count": len(content_ids),
        "targets": targets,
        "planned_args": [
            {"content_id": item, "args": {**normalized_shared_args, normalized_arg_name: item}}
            for item in content_ids
        ],
    }
    if dry_run:
        result = controlled_write_result(audit=audit, response=response_payload)
        return {"kind": "alterios_fast_live_bulk_manual_script", "status": "planned", **result}

    _assert_runtime_gate(runtime_fingerprint)
    response_payload["delivery_evidence"] = _assert_delivery_evidence(delivery_evidence)
    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=_write_enabled(),
    )
    assert_plan_matches_audit(plan_id=str(plan_id), audit=audit.as_dict())
    response_payload["execution"] = execute_bulk_manual_script(
        client,
        script_id=script_id,
        content_ids=content_ids,
        shared_args=normalized_shared_args,
        content_arg_name=normalized_arg_name,
        readback_content=readback_content,
        stop_on_error=stop_on_error,
    )
    result = controlled_write_result(audit=audit, response=response_payload, plan_id=plan_id)
    status = "applied" if response_payload["execution"]["ok"] else "partial_failure"
    return {"kind": "alterios_fast_live_bulk_manual_script", "status": status, **result}

def alterios_fast_live_bulk_process(
    diagram_id: str,
    selected_content_ids: list[str],
    delivery_evidence: dict[str, Any],
    profile: str,
    project_id: str,
    expected_count: int,
    expected_content_type_id: str,
    params: dict[str, Any] | None = None,
    process_name: str | None = None,
    expected_diagram_name: str | None = None,
    max_count: int = 100,
    stop_on_error: bool = True,
    expected_runtime_fingerprint: str | None = None,
    dry_run: bool = True,
    plan_id: str | None = None,
    refresh_health: bool = False,
    health_cache_ttl_seconds: int | None = None,
    allow_cached_health: bool = True,
    require_clean_health: bool = True,
    include_replay_smoke: bool = False,
) -> dict[str, Any]:
    """Plan or start one verified BPMN process for selected content rows."""
    if not str(diagram_id or "").strip():
        raise ValueError("diagram_id must not be empty.")
    normalized_content_type_id = str(expected_content_type_id or "").strip()
    if not normalized_content_type_id:
        raise ValueError("expected_content_type_id is required for bulk process start.")
    content_ids = normalize_bulk_ids(
        selected_content_ids,
        expected_count=expected_count,
        max_count=max_count,
    )
    if not dry_run and not str(plan_id or "").strip():
        raise ValueError("plan_id is required when dry_run=false for bulk process start.")
    preflight, runtime_fingerprint = _fast_bulk_preflight(
        scenario_tool="alterios_fast_live_bulk_process",
        delivery_evidence=delivery_evidence,
        profile=profile,
        project_id=project_id,
        expected_runtime_fingerprint=expected_runtime_fingerprint,
        dry_run=dry_run,
        refresh_health=refresh_health,
        health_cache_ttl_seconds=health_cache_ttl_seconds,
        allow_cached_health=allow_cached_health,
        require_clean_health=require_clean_health,
        include_replay_smoke=include_replay_smoke,
    )
    if not bool((preflight.get("summary") or {}).get("ok")):
        return _blocked_fast_bulk_result(
            kind="alterios_fast_live_bulk_process",
            profile=profile,
            project_id=project_id,
            preflight=preflight,
            dry_run=dry_run,
        )
    client = _client(profile, project_id)
    diagram = _find_diagram(client, diagram_id=diagram_id)
    if not diagram:
        raise ValueError(f"Diagram {diagram_id!r} was not found.")
    if expected_diagram_name and diagram.get("name") != expected_diagram_name:
        raise ValueError(
            f"Diagram name mismatch: expected {expected_diagram_name!r}, got {diagram.get('name')!r}."
        )
    targets = load_bulk_content_targets(
        client,
        content_ids,
        expected_content_type_id=normalized_content_type_id,
    )
    diagram_fingerprint = _resource_fingerprint(
        diagram,
        ("_id", "name", "value", "contentTypeId", "createOnStart", "delayedStart"),
    )
    operation = _resource_operation(
        name="POST /api/processes x selected",
        kind="bulk_process_start",
        method="POST",
        path="/api/processes",
        summary="Start one verified BPMN process for explicitly selected content rows.",
        request={
            "diagramId": diagram_id,
            "diagramFingerprint": diagram_fingerprint,
            "selectedContentIds": content_ids,
            "params": params,
            "name": process_name,
            "expectedContentTypeId": normalized_content_type_id,
            "stopOnError": stop_on_error,
            "runtimeFingerprint": runtime_fingerprint,
            "deliveryEvidence": delivery_evidence,
        },
        risk_level="workflow_side_effect",
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
    )
    response_payload: dict[str, Any] = {
        "preflight": preflight,
        "runtime_fingerprint": runtime_fingerprint,
        "diagram": _resource_summary(diagram),
        "diagram_fingerprint": diagram_fingerprint,
        "selected_count": len(content_ids),
        "targets": targets,
    }
    if dry_run:
        result = controlled_write_result(audit=audit, response=response_payload)
        return {"kind": "alterios_fast_live_bulk_process", "status": "planned", **result}

    _assert_runtime_gate(runtime_fingerprint)
    response_payload["delivery_evidence"] = _assert_delivery_evidence(delivery_evidence)
    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=_write_enabled(),
    )
    assert_plan_matches_audit(plan_id=str(plan_id), audit=audit.as_dict())
    response_payload["execution"] = execute_bulk_process_start(
        client,
        diagram_id=diagram_id,
        content_ids=content_ids,
        params=params,
        name=process_name,
        stop_on_error=stop_on_error,
    )
    result = controlled_write_result(audit=audit, response=response_payload, plan_id=plan_id)
    status = "applied" if response_payload["execution"]["ok"] else "partial_failure"
    return {"kind": "alterios_fast_live_bulk_process", "status": status, **result}

def alterios_fast_live_bulk_delete(
    selected_content_ids: list[str],
    expected_count: int,
    expected_content_type_id: str,
    delivery_evidence: dict[str, Any],
    profile: str,
    project_id: str,
    script_id: str,
    expected_script_name: str,
    content_ids_arg_name: str = "contentIds",
    expected_script_active: bool = True,
    max_count: int = 50,
    expected_runtime_fingerprint: str | None = None,
    dry_run: bool = True,
    plan_id: str | None = None,
    allow_destructive: bool = False,
    refresh_health: bool = False,
    health_cache_ttl_seconds: int | None = None,
    allow_cached_health: bool = True,
    require_clean_health: bool = True,
    include_replay_smoke: bool = False,
) -> dict[str, Any]:
    """Plan or destructively delete explicitly reviewed content rows through a dedicated dangerous workflow."""
    if not looks_like_uuid(script_id):
        raise ValueError("script_id must be a saved manual delete script UUID.")
    normalized_arg_name = str(content_ids_arg_name or "").strip()
    if not normalized_arg_name:
        raise ValueError("content_ids_arg_name must not be empty.")
    normalized_content_type_id = str(expected_content_type_id or "").strip()
    if not normalized_content_type_id:
        raise ValueError("expected_content_type_id is required for destructive bulk delete.")
    content_ids = normalize_bulk_ids(
        selected_content_ids,
        expected_count=expected_count,
        max_count=max_count,
    )
    if not dry_run and not str(plan_id or "").strip():
        raise ValueError("plan_id is required when dry_run=false for destructive bulk delete.")
    preflight, runtime_fingerprint = _fast_bulk_preflight(
        scenario_tool="alterios_fast_live_bulk_delete",
        delivery_evidence=delivery_evidence,
        profile=profile,
        project_id=project_id,
        expected_runtime_fingerprint=expected_runtime_fingerprint,
        dry_run=dry_run,
        refresh_health=refresh_health,
        health_cache_ttl_seconds=health_cache_ttl_seconds,
        allow_cached_health=allow_cached_health,
        require_clean_health=require_clean_health,
        include_replay_smoke=include_replay_smoke,
    )
    if not bool((preflight.get("summary") or {}).get("ok")):
        return _blocked_fast_bulk_result(
            kind="alterios_fast_live_bulk_delete",
            profile=profile,
            project_id=project_id,
            preflight=preflight,
            dry_run=dry_run,
        )
    client = _client(profile, project_id)
    script = _find_script(client, script_id=script_id)
    if not script:
        raise ValueError(f"Script {script_id!r} was not found.")
    if script.get("type") != "manual":
        raise ValueError(f"Script {script_id!r} has type {script.get('type')!r}; expected 'manual'.")
    if script.get("name") != expected_script_name:
        raise ValueError(
            f"Script name mismatch: expected {expected_script_name!r}, got {script.get('name')!r}."
        )
    if script.get("active") is not expected_script_active:
        raise ValueError(
            f"Script active mismatch: expected {expected_script_active!r}, got {script.get('active')!r}."
        )
    declared_arguments = script_argument_keys(script)
    if normalized_arg_name not in declared_arguments:
        raise ValueError(
            f"Destructive script must declare argument {normalized_arg_name!r} in config.arguments."
        )
    missing_arguments = sorted(declared_arguments - {normalized_arg_name})
    if missing_arguments:
        raise ValueError(
            "Destructive script declares unsupported extra required arguments: " + ", ".join(missing_arguments) + "."
        )
    script_fingerprint = _resource_fingerprint(
        script,
        ("_id", "name", "type", "active", "body", "value", "config", "librariesIds", "apiKey"),
    )
    operation = _resource_operation(
        name="POST /api/scripts/execute-manual destructive x selected",
        kind="destructive_bulk_delete",
        method="POST",
        path="/api/scripts/execute-manual",
        summary="Delete only the reviewed content IDs after a matching dry-run plan and dangerous gates.",
        request={
            "scriptId": script_id,
            "scriptFingerprint": script_fingerprint,
            "contentIdsArgName": normalized_arg_name,
            "selectedContentIds": content_ids,
            "expectedCount": expected_count,
            "expectedContentTypeId": normalized_content_type_id,
            "runtimeFingerprint": runtime_fingerprint,
            "deliveryEvidence": delivery_evidence,
        },
        risk_level="destructive",
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    targets = load_bulk_content_targets(
        client,
        content_ids,
        expected_content_type_id=normalized_content_type_id,
    )
    response_payload: dict[str, Any] = {
        "preflight": preflight,
        "runtime_fingerprint": runtime_fingerprint,
        "script": _resource_summary(script),
        "script_fingerprint": script_fingerprint,
        "selected_count": len(content_ids),
        "targets": targets,
        "required_execution_gates": [
            "dry_run=false",
            "matching plan_id",
            "ALTERIOS_MCP_ALLOW_WRITE=1",
            "ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE=1",
            "allow_destructive=true",
        ],
    }
    if dry_run:
        result = controlled_write_result(audit=audit, response=response_payload)
        return {"kind": "alterios_fast_live_bulk_delete", "status": "planned", **result}

    _assert_runtime_gate(runtime_fingerprint)
    response_payload["delivery_evidence"] = _assert_delivery_evidence(delivery_evidence)
    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    assert_plan_matches_audit(plan_id=str(plan_id), audit=audit.as_dict())
    response_payload["execution"] = execute_bulk_delete(
        client,
        script_id=script_id,
        content_ids=content_ids,
        content_ids_arg_name=normalized_arg_name,
    )
    result = controlled_write_result(audit=audit, response=response_payload, plan_id=plan_id)
    status = "applied" if response_payload["execution"]["ok"] else "readback_failed"
    return {"kind": "alterios_fast_live_bulk_delete", "status": status, **result}

__all__ = ['alterios_fast_live_write', 'alterios_fast_live_bulk_manual_script', 'alterios_fast_live_bulk_process', 'alterios_fast_live_bulk_delete']
