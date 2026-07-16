from __future__ import annotations

from .._support import *

def alterios_discover_readonly(
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Probe the known safe read-only Alterios REST routes."""
    return discover_readonly(_client(profile, project_id))

def alterios_profile_smoke_matrix(
    profile: str | None = None,
    project_limit: int = 100,
    include_project_discovery: bool = True,
    include_project_ids: bool = False,
    include_project_names: bool = False,
) -> dict[str, Any]:
    """Run read-only project-list and default-project route smoke across configured profiles."""
    return run_profile_smoke(
        selected_profile=profile,
        project_limit=project_limit,
        include_project_discovery=include_project_discovery,
        include_project_ids=include_project_ids,
        include_project_names=include_project_names,
    )

def alterios_replay_smoke(
    profile: str | None = None,
    project_id: str | None = None,
    include_live: bool = False,
    expected_tool_count_min: int = 75,
) -> dict[str, Any]:
    """Run local/read-only MCP replay smoke checks after an update."""
    if expected_tool_count_min < 1:
        raise ValueError("expected_tool_count_min must be positive.")
    return run_replay_smoke(
        profile=profile,
        project_id=project_id,
        include_live=include_live,
        expected_tool_count_min=expected_tool_count_min,
    )

def alterios_project_health(
    profile: str | None = None,
    project_id: str | None = None,
    refresh: bool = False,
    use_cache: bool = True,
    write_cache: bool = True,
    cache_ttl_seconds: int | None = None,
    include_processes: bool = True,
    include_report_templates: bool = False,
) -> dict[str, Any]:
    """Return a read-only health summary for forms/views/scripts/BPMN/reports before writes."""
    return run_project_health(
        profile=profile,
        project_id=project_id,
        refresh=refresh,
        use_cache=use_cache,
        write_cache=write_cache,
        cache_ttl_seconds=cache_ttl_seconds,
        include_processes=include_processes,
        include_report_templates=include_report_templates,
    )

def alterios_write_safety_preflight(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    allow_destructive: bool = False,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Classify a proposed mutating REST call and return the gates required before execution."""
    method = method.upper()
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        raise ValueError("alterios_write_safety_preflight supports only POST, PUT, PATCH, and DELETE")
    operation = _rest_write_operation(method, path, params or {}, body or {})
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=True,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    required_execution_gates = ["dry_run=false", "ALTERIOS_MCP_ALLOW_WRITE=1"]
    if is_dangerous_write_risk(operation.risk_level):
        required_execution_gates.extend(["ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE=1", "allow_destructive=true"])
    return controlled_write_result(
        audit=audit,
        response={
            "risk_level": operation.risk_level,
            "dangerous": is_dangerous_write_risk(operation.risk_level),
            "required_execution_gates": required_execution_gates,
            "will_execute": False,
        },
    )

def alterios_call_write_service(
    function: str,
    args: dict[str, Any],
    dry_run: bool = True,
    allow_destructive: bool = False,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or call a mutating Alterios script service. Execution requires explicit write gates."""
    operation = _write_service_operation(function, args)
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    if dry_run:
        return controlled_write_result(audit=audit)

    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    response = _client(profile, project_id).call_script_service(function, args, allow_write=True).as_dict()
    return controlled_write_result(audit=audit, response=response)

def alterios_execute_manual_script(
    script_id: str,
    args: dict[str, Any],
    expected_name: str | None = None,
    expected_active: bool | None = True,
    dry_run: bool = True,
    allow_destructive: bool = False,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or execute a manual Alterios script by UUID with preflight and readback."""
    operation = _manual_script_operation(script_id, args)
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
        allow_destructive=allow_destructive,
    )
    client = _client(profile, project_id)
    script = _find_script(client, script_id=script_id)
    if not script:
        raise ValueError(f"Script {script_id!r} was not found.")
    if script.get("type") != "manual":
        raise ValueError(f"Script {script_id!r} has type {script.get('type')!r}; expected 'manual'.")
    if expected_name and script.get("name") != expected_name:
        raise ValueError(f"Script name mismatch: expected {expected_name!r}, got {script.get('name')!r}.")
    if expected_active is not None and script.get("active") is not expected_active:
        raise ValueError(f"Script active mismatch: expected {expected_active!r}, got {script.get('active')!r}.")
    response_payload: dict[str, Any] = {
        "preflight": _resource_summary(script),
        "script_type": script.get("type"),
        "active": script.get("active"),
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)

    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=_write_enabled(),
        allow_destructive=allow_destructive,
    )
    response = client.execute_manual_script(script_id, args).as_dict()
    response_payload["executed"] = response
    response_payload["script_readback"] = client.script_by_id(script_id).as_dict()
    content_id = args.get("contentId") if isinstance(args, dict) else None
    if isinstance(content_id, str) and content_id.strip():
        response_payload["content_readback"] = client.content_by_id(content_id).as_dict()
    return controlled_write_result(audit=audit, response=response_payload)

def alterios_rest_write(
    method: str,
    path: str,
    body: dict[str, Any],
    params: dict[str, Any] | None = None,
    dry_run: bool = True,
    plan_id: str | None = None,
    allow_destructive: bool = False,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or run a mutating REST request. Execution requires explicit write gates."""
    method = method.upper()
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        raise ValueError("alterios_rest_write supports only POST, PUT, PATCH, and DELETE")
    request_params = params or {}
    operation = _rest_write_operation(method, path, request_params, body)
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    if dry_run:
        return controlled_write_result(audit=audit)

    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    if not plan_id:
        raise ValueError("plan_id is required when dry_run=false for alterios_rest_write.")
    assert_plan_matches_audit(plan_id=plan_id, audit=audit.as_dict())
    response = _client(profile, project_id).request(method, path, params=request_params, body=body).as_dict()
    return controlled_write_result(audit=audit, response=response, plan_id=plan_id)

__all__ = ['alterios_discover_readonly', 'alterios_profile_smoke_matrix', 'alterios_replay_smoke', 'alterios_project_health', 'alterios_write_safety_preflight', 'alterios_call_write_service', 'alterios_execute_manual_script', 'alterios_rest_write']
