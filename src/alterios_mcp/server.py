from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import AlteriosClient, AlteriosConfig, configured_profiles, looks_like_uuid
from .discovery import discover_readonly, list_objects, list_projects
from .services import get_service, list_services, service_to_dict
from .write_control import (
    WriteOperation,
    assert_write_allowed,
    build_write_audit,
    collect_target_ids,
    controlled_write_result,
)

mcp = FastMCP("alterios")


def _client(profile: str | None = None, project_id: str | None = None) -> AlteriosClient:
    return AlteriosClient(AlteriosConfig.from_env(profile=profile).with_project_id(project_id))


def _write_enabled() -> bool:
    return os.environ.get("ALTERIOS_MCP_ALLOW_WRITE") == "1"


def _write_service_operation(function: str, args: dict[str, Any]) -> WriteOperation:
    service = get_service(function)
    if not service.mutates:
        raise ValueError("Use alterios_call_readonly_service for read-only script services.")
    return WriteOperation(
        name=function,
        kind="script_service",
        risk_level=service.risk_level,
        summary=service.description,
        method="POST",
        target_ids=collect_target_ids(args),
        request={"function": function, "args": args},
    )


def _manual_script_operation(script_id: str, args: dict[str, Any]) -> WriteOperation:
    if not looks_like_uuid(script_id):
        raise ValueError("alterios_execute_manual_script requires a script UUID.")
    return WriteOperation(
        name="execute_manual_script",
        kind="manual_script",
        risk_level="manual_script",
        summary="Execute a saved Alterios manual script by UUID.",
        method="POST",
        path="/api/scripts/execute-manual",
        target_ids=collect_target_ids({"scriptId": script_id, "args": args}),
        request={"script_id": script_id, "args": args},
    )


def _rest_write_operation(method: str, path: str, params: dict[str, Any], body: dict[str, Any]) -> WriteOperation:
    risk_level = "destructive" if method == "DELETE" else "write"
    return WriteOperation(
        name=f"{method} {path}",
        kind="rest",
        risk_level=risk_level,
        summary=f"Run {method} against an Alterios REST API path.",
        method=method,
        path=path,
        target_ids=collect_target_ids({"params": params, "body": body}),
        request={"params": params, "body": body},
    )


@mcp.tool()
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


@mcp.tool()
def alterios_list_profiles(profile: str | None = None) -> dict[str, Any]:
    """Return configured Alterios instance profiles with redacted settings and missing values."""
    return configured_profiles(selected_profile=profile)


@mcp.tool()
def alterios_list_projects(
    limit: int = 100,
    offset: int = 0,
    profile: str | None = None,
) -> dict[str, Any]:
    """List projects available on the selected Alterios instance."""
    return list_projects(_client(profile), limit=limit, offset=offset)


@mcp.tool()
def alterios_service_catalog(read_only: bool = True) -> list[dict[str, Any]]:
    """Return known Alterios script-service functions."""
    return [service_to_dict(service) for service in list_services(read_only=read_only)]


@mcp.tool()
def alterios_call_readonly_service(
    function: str,
    args: dict[str, Any] | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Call a known read-only Alterios script service."""
    return _client(profile, project_id).call_script_service(function, args or {}, allow_write=False).as_dict()


@mcp.tool()
def alterios_rest_get(
    path: str,
    params: dict[str, Any] | None = None,
    profile: str | None = None,
    project_id: str | None = None,
    requires_project: bool = True,
) -> dict[str, Any]:
    """Run a read-only GET request against an Alterios REST API path."""
    return _client(profile, project_id).request(
        "GET",
        path,
        params=params or {},
        requires_project=requires_project,
    ).as_dict()


@mcp.tool()
def alterios_list_objects(
    kind: str,
    limit: int = 20,
    offset: int = 0,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """List common Alterios object types via validated listandcount routes."""
    return list_objects(_client(profile, project_id), kind=kind, limit=limit, offset=offset)


@mcp.tool()
def alterios_view_data_simplified(
    view_id: str,
    limit: int = 20,
    offset: int = 0,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read a view as Stimulsoft usually sees it through get-data-simplified."""
    body = {"viewId": view_id, "limit": limit, "offset": offset}
    return _client(profile, project_id).request("POST", "/api/views/v2/get-data-simplified", body=body).as_dict()


@mcp.tool()
def alterios_report_full(
    report_id: str,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read a full Alterios report by ID through the encoded report filter route."""
    return _client(profile, project_id).report_full(report_id).as_dict()


@mcp.tool()
def alterios_get_view(
    view_id: str,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read a full Alterios view object by ID."""
    return _client(profile, project_id).view_full(view_id).as_dict()


@mcp.tool()
def alterios_get_form(
    form_id: str,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read a full Alterios form object by ID."""
    return _client(profile, project_id).form_full(form_id).as_dict()


@mcp.tool()
def alterios_view_entities(
    view_id: str,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read configured entities/joins for an Alterios view."""
    return _client(profile, project_id).view_entities(view_id).as_dict()


@mcp.tool()
def alterios_view_fields_populated(
    view_id: str,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read populated field metadata for an Alterios view."""
    return _client(profile, project_id).view_fields_populated(view_id).as_dict()


@mcp.tool()
def alterios_list_fields(
    content_type_id: str | None = None,
    field_id: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read Alterios content type fields, optionally filtered by content type or field ID."""
    return _client(profile, project_id).list_fields(
        content_type_id=content_type_id,
        field_id=field_id,
        limit=limit,
        offset=offset,
    ).as_dict()


@mcp.tool()
def alterios_list_groups(
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read Alterios project groups."""
    return _client(profile, project_id).list_groups().as_dict()


@mcp.tool()
def alterios_file_metadata(
    file_ids: list[str],
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read Alterios file metadata for one or more file IDs."""
    return _client(profile, project_id).file_metadata(file_ids).as_dict()


@mcp.tool()
def alterios_list_comments(
    entity_id: str,
    entity: str = "any",
    limit: int = 20,
    depth: int = 1,
    page: int = 1,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read Alterios comments for an entity through the v1 comments API."""
    return _client(profile, project_id).list_comments(
        entity_id,
        entity=entity,
        limit=limit,
        depth=depth,
        page=page,
    ).as_dict()


@mcp.tool()
def alterios_view_data(
    view_id: str,
    limit: int = 20,
    offset: int = 0,
    content_id: str | None = None,
    data_id: list[str] | None = None,
    user_filters: dict[str, Any] | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read view rows through get-data with optional content, data, and user filter context."""
    return _client(profile, project_id).view_data(
        view_id,
        limit=limit,
        offset=offset,
        content_id=content_id,
        data_id=data_id,
        user_filters=user_filters,
    ).as_dict()


@mcp.tool()
def alterios_discover_readonly(
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Probe the known safe read-only Alterios REST routes."""
    return discover_readonly(_client(profile, project_id))


@mcp.tool()
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
        allow_destructive=allow_destructive,
    )
    if dry_run:
        return controlled_write_result(audit=audit)

    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=_write_enabled(),
        allow_destructive=allow_destructive,
    )
    response = _client(profile, project_id).call_script_service(function, args, allow_write=True).as_dict()
    return controlled_write_result(audit=audit, response=response)


@mcp.tool()
def alterios_execute_manual_script(
    script_id: str,
    args: dict[str, Any],
    dry_run: bool = True,
    allow_destructive: bool = False,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or execute a manual Alterios script by UUID. Execution requires explicit write gates."""
    operation = _manual_script_operation(script_id, args)
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
        allow_destructive=allow_destructive,
    )
    if dry_run:
        return controlled_write_result(audit=audit)

    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=_write_enabled(),
        allow_destructive=allow_destructive,
    )
    response = _client(profile, project_id).call_script_service(
        script_id,
        args,
        body_style="manual_script",
        allow_write=True,
    ).as_dict()
    return controlled_write_result(audit=audit, response=response)


@mcp.tool()
def alterios_rest_write(
    method: str,
    path: str,
    body: dict[str, Any],
    params: dict[str, Any] | None = None,
    dry_run: bool = True,
    allow_destructive: bool = False,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or run a mutating REST request. Execution requires explicit write gates."""
    method = method.upper()
    if method not in {"POST", "PUT", "DELETE"}:
        raise ValueError("alterios_rest_write supports only POST, PUT, and DELETE")
    request_params = params or {}
    operation = _rest_write_operation(method, path, request_params, body)
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
        allow_destructive=allow_destructive,
    )
    if dry_run:
        return controlled_write_result(audit=audit)

    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=_write_enabled(),
        allow_destructive=allow_destructive,
    )
    response = _client(profile, project_id).request(method, path, params=request_params, body=body).as_dict()
    return controlled_write_result(audit=audit, response=response)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
