from __future__ import annotations

import base64
import binascii
import json
import os
import time
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import (
    AlteriosClient,
    AlteriosConfig,
    content_update_payload,
    configured_profiles,
    normalize_content_field_value,
    looks_like_uuid,
    listandcount_items,
    report_full_item,
    strip_alterios_metadata,
)
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


def _add_comment_operation(entity_id: str, body: str, entity: str, parent_id: str | None) -> WriteOperation:
    request: dict[str, Any] = {"entity": entity, "entityId": entity_id, "body": body}
    if parent_id:
        request["parentId"] = parent_id
    return WriteOperation(
        name="POST /api/v1/comments",
        kind="comment",
        risk_level="write",
        summary="Create a comment on an Alterios entity and verify it through comments readback.",
        method="POST",
        path="/api/v1/comments",
        target_ids=collect_target_ids(request),
        request=request,
    )


def _content_fields_operation(
    content_id: str,
    field_values: dict[str, Any],
    *,
    content_type_id: str | None = None,
    groups_ids: list[str] | None = None,
    name: str | None = None,
) -> WriteOperation:
    request = {
        "_id": content_id,
        "contentTypeId": content_type_id,
        "fields": field_values,
        "groupsIds": groups_ids,
        "name": name,
    }
    return WriteOperation(
        name="PATCH /api/contents/save",
        kind="content_fields",
        risk_level="write",
        summary="Update fields on an existing Alterios content row with preflight and readback.",
        method="PATCH",
        path="/api/contents/save",
        target_ids=collect_target_ids(request),
        request={key: value for key, value in request.items() if value is not None},
    )


def _file_upload_operation(
    content_id: str,
    field_mname: str,
    filename: str,
    size: int,
    *,
    content_type_id: str | None = None,
    field_id: str | None = None,
    replace: bool = True,
) -> WriteOperation:
    request = {
        "contentId": content_id,
        "contentTypeId": content_type_id,
        "fieldId": field_id,
        "field_mname": field_mname,
        "filename": filename,
        "size": size,
        "replace": replace,
    }
    return WriteOperation(
        name="POST /api/file/upload/field + PATCH /api/contents/save",
        kind="file_upload",
        risk_level="write",
        summary="Upload a file to an Alterios file field and save the returned file value on a content row.",
        method="POST",
        path="/api/file/upload/field",
        target_ids=collect_target_ids(request),
        request={key: value for key, value in request.items() if value is not None},
    )


def _assert_expected_content(
    content: dict[str, Any],
    *,
    expected_content_type_id: str | None = None,
    expected_name: str | None = None,
) -> None:
    if expected_content_type_id and content.get("contentTypeId") != expected_content_type_id:
        raise ValueError(
            f"Content type mismatch: expected {expected_content_type_id!r}, got {content.get('contentTypeId')!r}."
        )
    if expected_name and content.get("name") != expected_name:
        raise ValueError(f"Content name mismatch: expected {expected_name!r}, got {content.get('name')!r}.")


def _content_summary(content: dict[str, Any]) -> dict[str, Any]:
    fields = content.get("fields") or {}
    return {
        "_id": content.get("_id"),
        "contentTypeId": content.get("contentTypeId"),
        "name": content.get("name"),
        "field_keys": sorted(str(key) for key in fields.keys()) if isinstance(fields, dict) else [],
    }


def _field_diff(existing_fields: dict[str, Any], field_values: dict[str, Any]) -> list[dict[str, Any]]:
    diff = []
    for field_name, value in field_values.items():
        normalized_value = normalize_content_field_value(value)
        before = existing_fields.get(field_name)
        diff.append(
            {
                "field": field_name,
                "before": before,
                "after": normalized_value,
                "changed": before != normalized_value,
            }
        )
    return diff


def _decode_file_payload(content_base64: str | None, text: str | None) -> bytes:
    if bool(content_base64) == bool(text):
        raise ValueError("Pass exactly one of content_base64 or text.")
    if content_base64:
        try:
            data = base64.b64decode(content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("content_base64 must be valid base64.") from exc
    else:
        data = (text or "").encode("utf-8")
    if not data:
        raise ValueError("file payload must not be empty.")
    return data


def _resolve_file_field(
    client: AlteriosClient,
    *,
    content_type_id: str,
    field_mname: str,
    field_id: str | None = None,
) -> dict[str, Any]:
    fields_response = client.list_fields(content_type_id=content_type_id)
    fields = fields_response.body
    if not isinstance(fields, list):
        raise ValueError("Field inventory returned unexpected payload.")

    resolved = next(
        (
            field
            for field in fields
            if isinstance(field, dict)
            and (field.get("mname") == field_mname or (field_id is not None and field.get("_id") == field_id))
        ),
        None,
    )
    if not resolved:
        raise ValueError(f"File field {field_mname!r} was not found in content type {content_type_id!r}.")
    if field_id and resolved.get("_id") != field_id:
        raise ValueError(f"Field id mismatch: expected {field_id!r}, got {resolved.get('_id')!r}.")
    if resolved.get("type") != "file":
        raise ValueError(f"Field {field_mname!r} is not a file field: {resolved.get('type')!r}.")
    return resolved


def _file_value_id(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("id", "_id", "fileId"):
            if value.get(key):
                return str(value[key])
    if isinstance(value, str):
        return value
    return None


def _file_values(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


MANAGED_MARKER = "Codex-managed"


def _resource_operation(
    *,
    name: str,
    kind: str,
    method: str,
    path: str,
    summary: str,
    request: dict[str, Any],
    risk_level: str = "write",
) -> WriteOperation:
    return WriteOperation(
        name=name,
        kind=kind,
        risk_level=risk_level,
        summary=summary,
        method=method,
        path=path,
        target_ids=collect_target_ids(request),
        request=request,
    )


def _assert_managed_or_allowed(resource: dict[str, Any], *, kind: str, allow_unmanaged_update: bool) -> None:
    if allow_unmanaged_update:
        return
    if MANAGED_MARKER in str(resource.get("description") or ""):
        return
    raise ValueError(f"{kind} {resource.get('_id')!r} is not marked as Codex-managed; pass allow_unmanaged_update=True.")


def _resource_diff(existing: dict[str, Any] | None, payload: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    diff = []
    for key in keys:
        before = existing.get(key) if existing else None
        after = payload.get(key)
        diff.append({"field": key, "before": before, "after": after, "changed": before != after})
    return diff


def _resource_summary(resource: dict[str, Any] | None) -> dict[str, Any] | None:
    if resource is None:
        return None
    return {
        "_id": resource.get("_id"),
        "name": resource.get("name"),
        "description": resource.get("description"),
        "projectId": resource.get("projectId"),
    }


def _find_named_resource(items: Any, name: str) -> dict[str, Any] | None:
    for item in listandcount_items(items):
        if item.get("name") == name:
            return item
    return None


def _find_view(
    client: AlteriosClient,
    *,
    view_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any] | None:
    if view_id:
        body = client.view_by_id(view_id).body
        if not isinstance(body, dict):
            raise ValueError("View readback returned unexpected payload.")
        return body
    if name:
        return _find_named_resource(client.list_views(limit=5000).body, name)
    return None


def _find_form(
    client: AlteriosClient,
    *,
    form_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any] | None:
    if form_id:
        body = client.form_by_id(form_id).body
        if not isinstance(body, dict):
            raise ValueError("Form readback returned unexpected payload.")
        return body
    if name:
        return _find_named_resource(client.list_forms(limit=5000).body, name)
    return None


def _view_entities_body(client: AlteriosClient, view_id: str) -> list[dict[str, Any]]:
    body = client.view_entities(view_id).body
    if not isinstance(body, list):
        raise ValueError("View entities readback returned unexpected payload.")
    return [item for item in body if isinstance(item, dict)]


def _view_fields_body(client: AlteriosClient, view_id: str) -> list[dict[str, Any]]:
    body = client.view_fields_populated(view_id).body
    if not isinstance(body, list):
        raise ValueError("View fields readback returned unexpected payload.")
    return [item for item in body if isinstance(item, dict)]


def _find_view_entity(
    client: AlteriosClient,
    *,
    view_id: str,
    entity_id: str | None = None,
    name: str | None = None,
    entity_type: str | None = None,
) -> dict[str, Any] | None:
    for entity in _view_entities_body(client, view_id):
        if entity_id and entity.get("_id") == entity_id:
            return entity
        if name and entity.get("name") == name and (entity_type is None or entity.get("type") == entity_type):
            return entity
    return None


def _find_view_field(
    client: AlteriosClient,
    *,
    view_id: str,
    view_field_id: str | None = None,
    entity_id: str | None = None,
    attribute: str | None = None,
    content_type_field_id: str | None = None,
) -> dict[str, Any] | None:
    for field in _view_fields_body(client, view_id):
        if view_field_id and field.get("_id") == view_field_id:
            return field
        if entity_id and field.get("entityId") != entity_id:
            continue
        if content_type_field_id and field.get("contentTypeFieldId") == content_type_field_id:
            return field
        if attribute and (field.get("attribute") == attribute or field.get("mname") == attribute):
            return field
    return None


def _view_field_save_payload(field: dict[str, Any]) -> dict[str, Any]:
    payload = dict(strip_alterios_metadata(field))
    for key in ("contentType", "contentTypeField", "relatedViewField", "diagramsNames"):
        payload.pop(key, None)
    return payload


def _find_script(
    client: AlteriosClient,
    *,
    script_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any] | None:
    if script_id:
        body = client.script_by_id(script_id).body
        if not isinstance(body, dict):
            raise ValueError("Script readback returned unexpected payload.")
        return body
    if name:
        return _find_named_resource(client.list_scripts(limit=5000).body, name)
    return None


def _find_diagram(
    client: AlteriosClient,
    *,
    diagram_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any] | None:
    if diagram_id:
        body = client.diagram_by_id(diagram_id).body
        if not isinstance(body, dict):
            raise ValueError("Diagram readback returned unexpected payload.")
        return body
    if name:
        return _find_named_resource(client.list_diagrams(limit=5000).body, name)
    return None


def _find_report(
    client: AlteriosClient,
    *,
    report_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any] | None:
    if report_id:
        body = client.report_by_id(report_id).body
        if not isinstance(body, dict):
            raise ValueError("Report readback returned unexpected payload.")
        return body
    if name:
        return _find_named_resource(client.list_reports(limit=5000).body, name)
    return None


def _response_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "comments", "rows", "data", "results", "values"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return listandcount_items(payload)


def _processes_body(
    client: AlteriosClient,
    *,
    diagram_id: str | None = None,
    content_id: str | None = None,
    process_id: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return listandcount_items(
        client.list_processes(
            diagram_id=diagram_id,
            content_id=content_id,
            process_id=process_id,
            limit=limit,
            offset=0,
        ).body
    )


def _tasks_body(
    client: AlteriosClient,
    *,
    diagram_id: str | None = None,
    content_id: str | None = None,
    process_id: str | None = None,
    task_id: str | None = None,
) -> list[dict[str, Any]]:
    return _response_items(
        client.list_tasks(
            diagram_id=diagram_id,
            content_id=content_id,
            process_id=process_id,
            task_id=task_id,
        ).body
    )


def _find_task(
    client: AlteriosClient,
    *,
    task_id: str,
    process_id: str | None = None,
    diagram_id: str | None = None,
    content_id: str | None = None,
) -> dict[str, Any] | None:
    queries = [
        {"task_id": task_id, "process_id": process_id, "diagram_id": diagram_id, "content_id": content_id},
        {"task_id": None, "process_id": process_id, "diagram_id": diagram_id, "content_id": content_id},
        {"task_id": task_id, "process_id": None, "diagram_id": None, "content_id": None},
    ]
    for query in queries:
        for task in _tasks_body(client, **query):
            if task.get("_id") == task_id:
                return task
    return None


def _assert_expected_task(
    task: dict[str, Any],
    *,
    expected_process_id: str | None = None,
    expected_content_id: str | None = None,
    expected_diagram_id: str | None = None,
) -> None:
    expected = {
        "processId": expected_process_id,
        "contentId": expected_content_id,
        "diagramId": expected_diagram_id,
    }
    for key, value in expected.items():
        if value and task.get(key) != value:
            raise ValueError(f"Task {task.get('_id')!r} {key} mismatch: expected {value!r}, got {task.get(key)!r}.")


def _report_template_payload(report: Any) -> dict[str, Any] | None:
    if not isinstance(report, dict):
        return None
    template = report.get("template")
    if isinstance(template, str):
        try:
            template = json.loads(template)
        except json.JSONDecodeError:
            return None
    return template if isinstance(template, dict) else None


def _report_has_dashboard_page(report: Any) -> bool:
    template = _report_template_payload(report)
    if not isinstance(template, dict):
        return False
    page = (template.get("Pages") or {}).get("0")
    return isinstance(page, dict) and page.get("Ident") == "StiDashboard"


def _report_template_has_marker(report: Any, marker: str | None = None) -> bool:
    template = _report_template_payload(report)
    return isinstance(template, dict) and template.get("CodexMarker") == (marker or None)


def _walk_values(value: Any) -> list[Any]:
    values = [value]
    if isinstance(value, dict):
        for child in value.values():
            values.extend(_walk_values(child))
    elif isinstance(value, list):
        for child in value:
            values.extend(_walk_values(child))
    return values


def _contains_text(value: Any, expected: str) -> bool:
    return any(expected in item for item in _walk_values(value) if isinstance(item, str))


def _has_project_database(template: dict[str, Any] | None) -> bool:
    if not isinstance(template, dict):
        return False
    for value in _walk_values(template):
        if isinstance(value, dict) and value.get("ServiceName") == "Project Database":
            return True
        if isinstance(value, str) and value == "Project Database":
            return True
    return False


def _report_is_manageable(existing: dict[str, Any], full: Any) -> bool:
    if MANAGED_MARKER in str(existing.get("description") or ""):
        return True
    if isinstance(full, dict) and MANAGED_MARKER in str(full.get("description") or ""):
        return True
    template = _report_template_payload(full)
    return isinstance(template, dict) and MANAGED_MARKER in str(template.get("CodexMarker") or "")


def _report_project_base_validation(
    report: dict[str, Any],
    *,
    expected_view_name: str | None = None,
    expected_marker: str | None = None,
) -> dict[str, Any]:
    template = _report_template_payload(report)
    marker = template.get("CodexMarker") if isinstance(template, dict) else None
    return {
        "has_template": isinstance(template, dict),
        "has_dashboard_page": _report_has_dashboard_page(report),
        "has_project_database": _has_project_database(template),
        "marker": marker,
        "marker_matches": expected_marker is None or marker == expected_marker,
        "view_name_matches": expected_view_name is None or _contains_text(template, expected_view_name),
    }


def _operation_result_shape(value: Any) -> str:
    if isinstance(value, dict):
        return "dict:" + ",".join(sorted(str(key) for key in value.keys())[:8])
    if isinstance(value, list):
        return f"list:{len(value)}"
    return type(value).__name__


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
def alterios_add_comment(
    entity_id: str,
    body: str,
    entity: str = "any",
    parent_id: str | None = None,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or create an Alterios comment. Execution requires explicit write gates and returns readback."""
    operation = _add_comment_operation(entity_id, body, entity, parent_id)
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
    )
    if dry_run:
        return controlled_write_result(audit=audit)

    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=_write_enabled(),
    )
    client = _client(profile, project_id)
    created = client.add_comment(entity_id, body, entity=entity, parent_id=parent_id).as_dict()
    readback = client.list_comments(entity_id, entity=entity, limit=20, depth=4, page=1).as_dict()
    return controlled_write_result(audit=audit, response={"created": created, "readback": readback})


@mcp.tool()
def alterios_update_content_fields(
    content_id: str,
    field_values: dict[str, Any],
    expected_content_type_id: str | None = None,
    expected_name: str | None = None,
    groups_ids: list[str] | None = None,
    name: str | None = None,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or update fields on an existing Alterios content row. Execution requires explicit write gates."""
    if not field_values:
        raise ValueError("field_values must contain at least one field.")
    operation = _content_fields_operation(
        content_id,
        field_values,
        content_type_id=expected_content_type_id,
        groups_ids=groups_ids,
        name=name,
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
    )
    if not dry_run:
        assert_write_allowed(
            profile=profile,
            project_id=project_id,
            operation=operation,
            write_enabled=_write_enabled(),
        )

    client = _client(profile, project_id)
    before = client.content_by_id(content_id).body
    if not isinstance(before, dict):
        raise ValueError("Content preflight returned unexpected payload.")
    _assert_expected_content(before, expected_content_type_id=expected_content_type_id, expected_name=expected_name)
    planned_payload = content_update_payload(
        before,
        field_values,
        content_type_id=expected_content_type_id,
        groups_ids=groups_ids,
        name=name,
    )
    response_payload: dict[str, Any] = {
        "preflight": _content_summary(before),
        "field_diff": _field_diff(before.get("fields") or {}, field_values),
        "planned_payload": planned_payload,
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)

    updated = client.update_content_fields(
        content_id,
        field_values,
        content_type_id=expected_content_type_id,
        groups_ids=groups_ids,
        name=name,
    ).as_dict()
    after = client.content_by_id(content_id).as_dict()
    response_payload.update({"updated": updated, "readback": after})
    return controlled_write_result(audit=audit, response=response_payload)


@mcp.tool()
def alterios_file_upload_to_field(
    content_id: str,
    field_mname: str,
    filename: str,
    content_base64: str | None = None,
    text: str | None = None,
    mime_type: str | None = None,
    expected_content_type_id: str | None = None,
    expected_name: str | None = None,
    field_id: str | None = None,
    replace: bool = True,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or upload a file into an Alterios file field and save it on a content row."""
    data = _decode_file_payload(content_base64, text)
    operation = _file_upload_operation(
        content_id,
        field_mname,
        filename,
        len(data),
        content_type_id=expected_content_type_id,
        field_id=field_id,
        replace=replace,
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
    )
    if not dry_run:
        assert_write_allowed(
            profile=profile,
            project_id=project_id,
            operation=operation,
            write_enabled=_write_enabled(),
        )

    client = _client(profile, project_id)
    before = client.content_by_id(content_id).body
    if not isinstance(before, dict):
        raise ValueError("Content preflight returned unexpected payload.")
    _assert_expected_content(before, expected_content_type_id=expected_content_type_id, expected_name=expected_name)
    content_type_id = expected_content_type_id or before.get("contentTypeId")
    if not content_type_id:
        raise ValueError("Content type id is required for file upload.")
    field = _resolve_file_field(client, content_type_id=content_type_id, field_mname=field_mname, field_id=field_id)
    existing_values = _file_values((before.get("fields") or {}).get(field_mname))
    response_payload: dict[str, Any] = {
        "preflight": _content_summary(before),
        "file": {
            "filename": filename,
            "mime_type": mime_type,
            "size": len(data),
            "replace": replace,
            "field_mname": field_mname,
            "field_id": field.get("_id"),
            "content_type_id": content_type_id,
        },
        "existing_file_value_count": len(existing_values),
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)

    uploaded_response = client.upload_file_to_field(
        data,
        filename=filename,
        content_type_id=content_type_id,
        field_id=field["_id"],
        mime_type=mime_type,
    )
    uploaded = uploaded_response.body
    uploaded_id = _file_value_id(uploaded)
    if not uploaded_id:
        raise ValueError("File upload response did not contain a file id.")
    uploaded_filename = uploaded.get("filename") if isinstance(uploaded, dict) else None
    if not uploaded_filename and isinstance(uploaded, dict):
        uploaded_filename = uploaded.get("name")
    uploaded_mime_type = uploaded.get("mimeType") if isinstance(uploaded, dict) else None
    uploaded_value = {
        "id": uploaded_id,
        "filename": uploaded_filename or filename,
        "name": uploaded_filename or filename,
        "mimeType": uploaded_mime_type or mime_type or "application/octet-stream",
        "size": (uploaded.get("size") if isinstance(uploaded, dict) else None) or len(data),
    }
    next_values = [uploaded_value] if replace else [*existing_values, uploaded_value]
    saved = client.update_content_fields(content_id, {field_mname: next_values}, content_type_id=content_type_id).as_dict()
    metadata = client.file_metadata([uploaded_id]).as_dict()
    readback = client.content_by_id(content_id).as_dict()
    response_payload.update(
        {
            "uploaded": uploaded_response.as_dict(),
            "saved": saved,
            "file_metadata": metadata,
            "readback": readback,
        }
    )
    return controlled_write_result(audit=audit, response=response_payload)


@mcp.tool()
def alterios_upsert_view(
    name: str,
    view_id: str | None = None,
    description: str | None = None,
    format: str | None = None,
    settings: dict[str, Any] | None = None,
    strict: bool | None = None,
    allow_unmanaged_update: bool = False,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or create/update an Alterios view. Execution requires explicit write gates."""
    if not name.strip():
        raise ValueError("name must not be empty.")
    client = _client(profile, project_id)
    existing = _find_view(client, view_id=view_id, name=name)
    if existing:
        _assert_managed_or_allowed(existing, kind="View", allow_unmanaged_update=allow_unmanaged_update)
    payload = {
        **(existing or {}),
        "name": name,
        "description": description if description is not None else (existing or {}).get("description") or f"{MANAGED_MARKER}: alterios-mcp view.",
        "format": format if format is not None else (existing or {}).get("format") or "table",
        "settings": settings if settings is not None else (existing or {}).get("settings") or {},
        "strict": strict if strict is not None else (existing or {}).get("strict") or False,
    }
    operation = _resource_operation(
        name=("PATCH /api/views/{id}" if existing else "POST /api/views"),
        kind="view",
        method="PATCH" if existing else "POST",
        path=f"/api/views/{existing.get('_id')}" if existing else "/api/views",
        summary="Create or update an Alterios view with preflight and readback.",
        request={"_id": payload.get("_id"), "name": name},
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
    )
    diff = _resource_diff(existing, payload, ("name", "description", "format", "settings", "strict"))
    response_payload: dict[str, Any] = {
        "preflight": _resource_summary(existing),
        "diff": diff,
        "planned_payload": strip_alterios_metadata(payload),
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    saved = client.save_view(payload).as_dict()
    saved_id = ((saved.get("body") or {}) if isinstance(saved, dict) else {}).get("_id") or payload.get("_id")
    readback_body = client.view_by_id(saved_id).as_dict() if saved_id else {"body": _find_view(client, name=name)}
    response_payload.update({"saved": saved, "readback": readback_body})
    return controlled_write_result(audit=audit, response=response_payload)


@mcp.tool()
def alterios_upsert_view_entity(
    view_id: str,
    name: str,
    entity_type: str | None = None,
    config: dict[str, Any] | None = None,
    joins: list[dict[str, Any]] | None = None,
    entity_id: str | None = None,
    allow_unmanaged_update: bool = False,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or create/update an Alterios view entity. Execution requires explicit write gates."""
    if not view_id.strip():
        raise ValueError("view_id must not be empty.")
    if not name.strip():
        raise ValueError("name must not be empty.")
    client = _client(profile, project_id)
    view = _find_view(client, view_id=view_id)
    if not view:
        raise ValueError(f"View {view_id!r} was not found.")
    _assert_managed_or_allowed(view, kind="View", allow_unmanaged_update=allow_unmanaged_update)
    existing = _find_view_entity(client, view_id=view_id, entity_id=entity_id, name=name, entity_type=entity_type)
    if not existing and config is None:
        raise ValueError("config is required when creating a new view entity.")
    effective_entity_type = entity_type or (existing or {}).get("type") or "content"
    payload = {
        **(existing or {}),
        "name": name,
        "type": effective_entity_type,
        "viewId": view_id,
        "config": config if config is not None else (existing or {}).get("config") or {},
        "joins": joins if joins is not None else (existing or {}).get("joins") or [],
    }
    operation = _resource_operation(
        name=("PATCH /api/view-entities/{id}" if existing else "POST /api/view-entities"),
        kind="view_entity",
        method="PATCH" if existing else "POST",
        path=f"/api/view-entities/{existing.get('_id')}" if existing else "/api/view-entities",
        summary="Create or update an Alterios view entity with parent view guard and readback.",
        request={"_id": payload.get("_id"), "viewId": view_id, "name": name, "type": effective_entity_type},
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
    )
    response_payload: dict[str, Any] = {
        "view": _resource_summary(view),
        "preflight": _resource_summary(existing),
        "diff": _resource_diff(existing, payload, ("name", "type", "viewId", "config", "joins")),
        "planned_payload": strip_alterios_metadata(payload),
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    saved = client.save_view_entity(payload).as_dict()
    readback = _find_view_entity(client, view_id=view_id, entity_id=(existing or {}).get("_id"), name=name, entity_type=effective_entity_type)
    response_payload.update({"saved": saved, "readback": readback})
    return controlled_write_result(audit=audit, response=response_payload)


@mcp.tool()
def alterios_upsert_view_field(
    view_id: str,
    entity_id: str,
    view_field_id: str | None = None,
    attribute: str | None = None,
    content_type_field_id: str | None = None,
    alias: str | None = None,
    mname: str | None = None,
    order: int | None = None,
    settings: dict[str, Any] | None = None,
    allow_unmanaged_update: bool = False,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or add/update an Alterios view field. Execution requires explicit write gates."""
    if not view_id.strip():
        raise ValueError("view_id must not be empty.")
    if not entity_id.strip():
        raise ValueError("entity_id must not be empty.")
    if not view_field_id and bool(attribute) == bool(content_type_field_id):
        raise ValueError("Pass exactly one of attribute or content_type_field_id when view_field_id is not provided.")
    client = _client(profile, project_id)
    view = _find_view(client, view_id=view_id)
    if not view:
        raise ValueError(f"View {view_id!r} was not found.")
    _assert_managed_or_allowed(view, kind="View", allow_unmanaged_update=allow_unmanaged_update)
    existing = _find_view_field(
        client,
        view_id=view_id,
        view_field_id=view_field_id,
        entity_id=entity_id,
        attribute=attribute,
        content_type_field_id=content_type_field_id,
    )
    add_request = {"entityId": entity_id, "attribute": attribute, "contentTypeFieldId": content_type_field_id}
    payload = dict(existing or {})
    if existing:
        if alias is not None:
            payload["alias"] = alias
        if mname is not None:
            payload["mname"] = mname
        if order is not None:
            payload["order"] = order
        if settings is not None:
            payload["settings"] = settings
    operation = _resource_operation(
        name="POST /api/view-entities/add-one-field + POST /api/view-fields/save",
        kind="view_field",
        method="POST",
        path="/api/view-entities/add-one-field",
        summary="Add a field to a view entity when missing and update its view-field configuration.",
        request={**add_request, "viewFieldId": view_field_id, "alias": alias, "mname": mname, "order": order, "settings": settings},
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
    )
    response_payload: dict[str, Any] = {
        "view": _resource_summary(view),
        "preflight": _resource_summary(existing),
        "will_add_field": existing is None,
        "add_request": {key: value for key, value in add_request.items() if value is not None},
        "diff": _resource_diff(existing, payload, ("alias", "mname", "order", "settings")) if existing else [],
        "planned_payload": _view_field_save_payload(payload) if existing else None,
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    add_response = None
    if existing is None:
        add_response = client.add_view_entity_field(
            entity_id,
            attribute=attribute,
            content_type_field_id=content_type_field_id,
        ).as_dict()
        existing = _find_view_field(
            client,
            view_id=view_id,
            entity_id=entity_id,
            attribute=attribute,
            content_type_field_id=content_type_field_id,
        )
        if existing is None:
            raise ValueError("Created view field was not visible on readback.")
        payload = dict(existing)
    if alias is not None:
        payload["alias"] = alias
    if mname is not None:
        payload["mname"] = mname
    if order is not None:
        payload["order"] = order
    if settings is not None:
        payload["settings"] = settings
    saved = client.save_view_field(_view_field_save_payload(payload)).as_dict()
    readback = _find_view_field(client, view_id=view_id, view_field_id=payload.get("_id"))
    response_payload.update({"added": add_response, "saved": saved, "readback": readback})
    return controlled_write_result(audit=audit, response=response_payload)


@mcp.tool()
def alterios_upsert_form(
    name: str,
    form_id: str | None = None,
    page_title: str | None = None,
    tabs: list[dict[str, Any]] | None = None,
    form_action_containers: list[dict[str, Any]] | None = None,
    description: str | None = None,
    allow_unmanaged_update: bool = False,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or create/update an Alterios form. Execution requires explicit write gates."""
    if not name.strip():
        raise ValueError("name must not be empty.")
    client = _client(profile, project_id)
    existing = _find_form(client, form_id=form_id, name=name)
    if existing:
        _assert_managed_or_allowed(existing, kind="Form", allow_unmanaged_update=allow_unmanaged_update)
    elif tabs is None:
        raise ValueError("tabs is required when creating a new form.")
    payload = {
        **(existing or {}),
        "name": name,
        "pageTitle": page_title if page_title is not None else (existing or {}).get("pageTitle") or name,
        "description": description if description is not None else (existing or {}).get("description") or f"{MANAGED_MARKER}: alterios-mcp form.",
        "tabs": tabs if tabs is not None else (existing or {}).get("tabs") or [],
        "formActionContainers": (
            form_action_containers
            if form_action_containers is not None
            else (existing or {}).get("formActionContainers") or []
        ),
    }
    operation = _resource_operation(
        name=("PATCH /api/forms/{id}" if existing else "POST /api/forms"),
        kind="form",
        method="PATCH" if existing else "POST",
        path=f"/api/forms/{existing.get('_id')}" if existing else "/api/forms",
        summary="Create or update an Alterios form with managed-object guard and readback.",
        request={"_id": payload.get("_id"), "name": name},
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
    )
    response_payload: dict[str, Any] = {
        "preflight": _resource_summary(existing),
        "diff": _resource_diff(existing, payload, ("name", "pageTitle", "description", "tabs", "formActionContainers")),
        "planned_payload": strip_alterios_metadata(payload),
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    saved = client.save_form(payload).as_dict()
    saved_id = ((saved.get("body") or {}) if isinstance(saved, dict) else {}).get("_id") or payload.get("_id")
    readback_body = client.form_by_id(saved_id).as_dict() if saved_id else {"body": _find_form(client, name=name)}
    response_payload.update({"saved": saved, "readback": readback_body})
    return controlled_write_result(audit=audit, response=response_payload)


@mcp.tool()
def alterios_patch_form_actions(
    form_id: str,
    form_action_containers: list[dict[str, Any]],
    expected_name: str | None = None,
    allow_unmanaged_update: bool = False,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or replace only formActionContainers on an Alterios form."""
    client = _client(profile, project_id)
    existing = _find_form(client, form_id=form_id)
    if not existing:
        raise ValueError(f"Form {form_id!r} was not found.")
    if expected_name and existing.get("name") != expected_name:
        raise ValueError(f"Form name mismatch: expected {expected_name!r}, got {existing.get('name')!r}.")
    _assert_managed_or_allowed(existing, kind="Form", allow_unmanaged_update=allow_unmanaged_update)
    return alterios_upsert_form(
        str(existing.get("name") or ""),
        form_id=form_id,
        form_action_containers=form_action_containers,
        allow_unmanaged_update=True,
        dry_run=dry_run,
        profile=profile,
        project_id=project_id,
    )


@mcp.tool()
def alterios_patch_form_tabs(
    form_id: str,
    tabs: list[dict[str, Any]],
    expected_name: str | None = None,
    allow_unmanaged_update: bool = False,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or replace only tabs on an Alterios form."""
    client = _client(profile, project_id)
    existing = _find_form(client, form_id=form_id)
    if not existing:
        raise ValueError(f"Form {form_id!r} was not found.")
    if expected_name and existing.get("name") != expected_name:
        raise ValueError(f"Form name mismatch: expected {expected_name!r}, got {existing.get('name')!r}.")
    _assert_managed_or_allowed(existing, kind="Form", allow_unmanaged_update=allow_unmanaged_update)
    return alterios_upsert_form(
        str(existing.get("name") or ""),
        form_id=form_id,
        tabs=tabs,
        allow_unmanaged_update=True,
        dry_run=dry_run,
        profile=profile,
        project_id=project_id,
    )


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
def alterios_upsert_script(
    name: str,
    script_id: str | None = None,
    script_type: str | None = None,
    body: str | None = None,
    active: bool | None = None,
    share: bool | None = None,
    config: dict[str, Any] | None = None,
    libraries_ids: list[str] | None = None,
    description: str | None = None,
    allow_unmanaged_update: bool = False,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or create/update an Alterios manual/event/diagram script."""
    if not name.strip():
        raise ValueError("name must not be empty.")
    client = _client(profile, project_id)
    existing = _find_script(client, script_id=script_id, name=name)
    if existing:
        _assert_managed_or_allowed(existing, kind="Script", allow_unmanaged_update=allow_unmanaged_update)
    elif body is None:
        raise ValueError("body is required when creating a new script.")

    effective_type = script_type or (existing or {}).get("type") or "manual"
    if effective_type not in {"manual", "event", "diagram"}:
        raise ValueError("script_type must be one of: manual, event, diagram.")
    payload = {
        **(existing or {}),
        "name": name,
        "description": description if description is not None else (existing or {}).get("description") or f"{MANAGED_MARKER}: alterios-mcp script.",
        "type": effective_type,
        "active": active if active is not None else (existing or {}).get("active", True),
        "body": body if body is not None else (existing or {}).get("body") or "",
        "share": share if share is not None else (existing or {}).get("share", False),
        "config": config if config is not None else (existing or {}).get("config") or {},
        "librariesIds": libraries_ids if libraries_ids is not None else (existing or {}).get("librariesIds") or [],
    }
    operation = _resource_operation(
        name=("PUT /api/scripts" if existing else "POST /api/scripts"),
        kind="script",
        method="PUT" if existing else "POST",
        path="/api/scripts",
        summary="Create or update an Alterios script with managed-object guard and readback.",
        request={"_id": payload.get("_id"), "name": name, "type": effective_type},
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
    )
    response_payload: dict[str, Any] = {
        "preflight": _resource_summary(existing),
        "diff": _resource_diff(existing, payload, ("name", "description", "type", "active", "body", "share", "config", "librariesIds")),
        "planned_payload": strip_alterios_metadata(payload),
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    saved = client.save_script(payload).as_dict()
    saved_id = ((saved.get("body") or {}) if isinstance(saved, dict) else {}).get("_id") or payload.get("_id")
    readback = client.script_by_id(saved_id).as_dict() if saved_id else {"body": _find_script(client, name=name)}
    response_payload.update({"saved": saved, "readback": readback})
    return controlled_write_result(audit=audit, response=response_payload)


@mcp.tool()
def alterios_validate_script(
    script_id: str | None = None,
    name: str | None = None,
    expected_type: str | None = None,
    expected_active: bool | None = None,
    expected_managed: bool = False,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read and validate an Alterios script by ID or name."""
    if not script_id and not name:
        raise ValueError("Pass script_id or name.")
    script = _find_script(_client(profile, project_id), script_id=script_id, name=name)
    if not script:
        raise ValueError("Script was not found.")
    validation = {
        "type_matches": expected_type is None or script.get("type") == expected_type,
        "active_matches": expected_active is None or script.get("active") is expected_active,
        "managed": MANAGED_MARKER in str(script.get("description") or ""),
        "managed_matches": not expected_managed or MANAGED_MARKER in str(script.get("description") or ""),
        "has_body": bool(script.get("body")),
        "has_config": isinstance(script.get("config"), dict),
        "librariesIds_is_list": isinstance(script.get("librariesIds"), list),
    }
    return {"script": _resource_summary(script), "validation": validation, "script_type": script.get("type"), "active": script.get("active")}


@mcp.tool()
def alterios_upsert_bpmn_diagram(
    name: str,
    diagram_id: str | None = None,
    value: str | None = None,
    content_type_id: str | None = None,
    create_on_start: bool | None = None,
    delayed_start: bool | None = None,
    description: str | None = None,
    allow_unmanaged_update: bool = False,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or create/update a BPMN diagram."""
    if not name.strip():
        raise ValueError("name must not be empty.")
    client = _client(profile, project_id)
    existing = _find_diagram(client, diagram_id=diagram_id, name=name)
    if existing:
        _assert_managed_or_allowed(existing, kind="Diagram", allow_unmanaged_update=allow_unmanaged_update)
    elif value is None or content_type_id is None:
        raise ValueError("value and content_type_id are required when creating a new BPMN diagram.")
    payload = {
        **(existing or {}),
        "name": name,
        "description": description if description is not None else (existing or {}).get("description") or f"{MANAGED_MARKER}: alterios-mcp BPMN diagram.",
        "value": value if value is not None else (existing or {}).get("value") or "",
        "contentTypeId": content_type_id if content_type_id is not None else (existing or {}).get("contentTypeId"),
        "createOnStart": create_on_start if create_on_start is not None else (existing or {}).get("createOnStart", False),
        "delayedStart": delayed_start if delayed_start is not None else (existing or {}).get("delayedStart", False),
    }
    operation = _resource_operation(
        name=("PATCH /api/diagrams/{id}" if existing else "POST /api/diagrams"),
        kind="bpmn_diagram",
        method="PATCH" if existing else "POST",
        path=f"/api/diagrams/{existing.get('_id')}" if existing else "/api/diagrams",
        summary="Create or update a BPMN diagram with managed-object guard and readback.",
        request={"_id": payload.get("_id"), "name": name, "contentTypeId": payload.get("contentTypeId")},
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
    )
    response_payload: dict[str, Any] = {
        "preflight": _resource_summary(existing),
        "diff": _resource_diff(existing, payload, ("name", "description", "value", "contentTypeId", "createOnStart", "delayedStart")),
        "planned_payload": strip_alterios_metadata(payload),
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    saved = client.save_diagram(payload).as_dict()
    saved_id = ((saved.get("body") or {}) if isinstance(saved, dict) else {}).get("_id") or payload.get("_id")
    readback = client.diagram_by_id(saved_id).as_dict() if saved_id else {"body": _find_diagram(client, name=name)}
    response_payload.update({"saved": saved, "readback": readback})
    return controlled_write_result(audit=audit, response=response_payload)


@mcp.tool()
def alterios_list_process_tasks(
    process_id: str | None = None,
    diagram_id: str | None = None,
    content_id: str | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read process instances and active tasks by process, diagram, or content context."""
    if not process_id and not diagram_id and not content_id:
        raise ValueError("Pass process_id, diagram_id, or content_id.")
    client = _client(profile, project_id)
    processes = _processes_body(client, process_id=process_id, diagram_id=diagram_id, content_id=content_id)
    tasks = _tasks_body(client, process_id=process_id, diagram_id=diagram_id, content_id=content_id)
    return {"processes": processes, "tasks": tasks, "process_count": len(processes), "task_count": len(tasks)}


@mcp.tool()
def alterios_start_process(
    diagram_id: str,
    content_id: str | None = None,
    params: dict[str, Any] | None = None,
    name: str | None = None,
    start_message_id: str | None = None,
    response_message_id: str | None = None,
    contents: list[dict[str, Any]] | None = None,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or start a BPMN process. Execution creates workflow side effects."""
    if not diagram_id.strip():
        raise ValueError("diagram_id must not be empty.")
    client = _client(profile, project_id)
    diagram = _find_diagram(client, diagram_id=diagram_id)
    if not diagram:
        raise ValueError(f"Diagram {diagram_id!r} was not found.")
    content = client.content_by_id(content_id).body if content_id else None
    operation = _resource_operation(
        name="POST /api/processes",
        kind="process_start",
        method="POST",
        path="/api/processes",
        summary="Start an Alterios BPMN process and read back process/tasks.",
        request={
            "diagramId": diagram_id,
            "contentId": content_id,
            "name": name,
            "params": params,
            "startMessageId": start_message_id,
            "responseMessageId": response_message_id,
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
    before = _processes_body(client, diagram_id=diagram_id, content_id=content_id) if content_id else []
    response_payload: dict[str, Any] = {
        "diagram": _resource_summary(diagram),
        "content": _content_summary(content) if isinstance(content, dict) else None,
        "preflight_process_count": len(before),
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    started = client.start_process(
        diagram_id,
        content_id=content_id,
        params=params,
        name=name,
        start_message_id=start_message_id,
        response_message_id=response_message_id,
        contents=contents,
    ).as_dict()
    body = started.get("body") if isinstance(started, dict) else None
    process_id = body.get("processId") or body.get("_id") or body.get("id") if isinstance(body, dict) else None
    readback_processes = _processes_body(client, process_id=str(process_id) if process_id else None, diagram_id=diagram_id, content_id=content_id)
    if not process_id and readback_processes:
        process = next((item for item in readback_processes if not item.get("completed") and not item.get("error")), None)
        process = process or readback_processes[0]
        process_id = process.get("_id")
    readback_tasks = _tasks_body(client, process_id=str(process_id)) if process_id else []
    if not readback_tasks:
        readback_tasks = _tasks_body(client, diagram_id=diagram_id, content_id=content_id)
    response_payload.update({"started": started, "process_id": process_id, "readback_processes": readback_processes, "readback_tasks": readback_tasks})
    return controlled_write_result(audit=audit, response=response_payload)


@mcp.tool()
def alterios_complete_task(
    task_id: str,
    next_flow_id: str | None = None,
    process_content: dict[str, Any] | None = None,
    contents: list[dict[str, Any]] | None = None,
    expected_process_id: str | None = None,
    expected_content_id: str | None = None,
    expected_diagram_id: str | None = None,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or complete a BPMN task. Execution advances workflow state."""
    if not task_id.strip():
        raise ValueError("task_id must not be empty.")
    client = _client(profile, project_id)
    task = _find_task(
        client,
        task_id=task_id,
        process_id=expected_process_id,
        diagram_id=expected_diagram_id,
        content_id=expected_content_id,
    )
    if not task:
        raise ValueError(f"Task {task_id!r} was not found.")
    _assert_expected_task(
        task,
        expected_process_id=expected_process_id,
        expected_content_id=expected_content_id,
        expected_diagram_id=expected_diagram_id,
    )
    operation = _resource_operation(
        name="DELETE /api/tasks/complete",
        kind="task_complete",
        method="DELETE",
        path="/api/tasks/complete",
        summary="Complete an Alterios task and read back related process/task state.",
        request={"_id": task_id, "nextFlowId": next_flow_id, "processId": expected_process_id, "contentId": expected_content_id, "diagramId": expected_diagram_id},
        risk_level="workflow_side_effect",
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
    )
    response_payload: dict[str, Any] = {"preflight_task": task}
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    completed = client.complete_task(task_id, next_flow_id=next_flow_id, process_content=process_content, contents=contents or []).as_dict()
    readback_tasks = _tasks_body(client, process_id=expected_process_id, diagram_id=expected_diagram_id, content_id=expected_content_id)
    readback_processes = _processes_body(client, process_id=expected_process_id, diagram_id=expected_diagram_id, content_id=expected_content_id) if (expected_process_id or expected_diagram_id or expected_content_id) else []
    response_payload.update({"completed": completed, "readback_tasks": readback_tasks, "readback_processes": readback_processes})
    return controlled_write_result(audit=audit, response=response_payload)


@mcp.tool()
def alterios_validate_process_result(
    process_id: str | None = None,
    diagram_id: str | None = None,
    content_id: str | None = None,
    expected_completed: bool | None = None,
    expected_error_absent: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read and validate process completion/error state."""
    if not process_id and not diagram_id and not content_id:
        raise ValueError("Pass process_id, diagram_id, or content_id.")
    processes = _processes_body(_client(profile, project_id), process_id=process_id, diagram_id=diagram_id, content_id=content_id)
    selected = processes[0] if processes else None
    validation = {
        "found": selected is not None,
        "completed_matches": selected is not None and (expected_completed is None or selected.get("completed") is expected_completed),
        "error_absent_matches": selected is not None and (not expected_error_absent or not selected.get("error")),
        "status": selected.get("status") if selected else None,
        "stages": selected.get("stages") if selected else None,
    }
    return {"process": selected, "process_count": len(processes), "validation": validation}


@mcp.tool()
def alterios_upsert_report(
    name: str,
    report_id: str | None = None,
    report_type: str | None = None,
    template: str | dict[str, Any] | None = None,
    description: str | None = None,
    allow_unmanaged_update: bool = False,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or create/update an Alterios report and read it back through report full."""
    if not name.strip():
        raise ValueError("name must not be empty.")
    client = _client(profile, project_id)
    existing = _find_report(client, report_id=report_id, name=name)
    full = client.report_by_id(existing["_id"]).body if existing and existing.get("_id") else None
    if existing and not allow_unmanaged_update and not _report_is_manageable(existing, full):
        raise ValueError(f"Report {existing.get('_id')!r} is not marked as Codex-managed; pass allow_unmanaged_update=True.")
    elif not existing and template is None:
        raise ValueError("template is required when creating a new report.")
    existing_type = (existing or {}).get("type")
    full_type = full.get("type") if isinstance(full, dict) else None
    existing_template = full.get("template") if isinstance(full, dict) else None
    payload = {
        **(existing or {}),
        "name": name,
        "description": description if description is not None else (existing or {}).get("description") or f"{MANAGED_MARKER}: alterios-mcp report.",
        "type": report_type if report_type is not None else existing_type or full_type or "dashboard",
        "template": template if template is not None else existing_template,
    }
    operation = _resource_operation(
        name=("PUT /api/reports" if existing else "POST /api/reports"),
        kind="report",
        method="PUT" if existing else "POST",
        path="/api/reports",
        summary="Create or update an Alterios report and read it back through /api/reports/full.",
        request={"_id": payload.get("_id"), "name": name, "type": payload.get("type")},
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
    )
    response_payload: dict[str, Any] = {
        "preflight": _resource_summary(existing),
        "diff": _resource_diff(full if isinstance(full, dict) else existing, payload, ("name", "description", "type", "template")),
        "planned_payload": strip_alterios_metadata(payload),
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    saved = client.save_report(payload).as_dict()
    saved_id = ((saved.get("body") or {}) if isinstance(saved, dict) else {}).get("_id") or payload.get("_id")
    readback = client.report_by_id(saved_id).as_dict() if saved_id else {"body": _find_report(client, name=name)}
    response_payload.update({"saved": saved, "readback": readback})
    return controlled_write_result(audit=audit, response=response_payload)


@mcp.tool()
def alterios_patch_report_template(
    report_id: str,
    template: str | dict[str, Any],
    expected_name: str | None = None,
    expected_marker: str | None = None,
    allow_unmanaged_update: bool = False,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or replace only a report template while preserving report metadata."""
    client = _client(profile, project_id)
    existing = _find_report(client, report_id=report_id)
    if not existing:
        raise ValueError(f"Report {report_id!r} was not found.")
    if expected_name and existing.get("name") != expected_name:
        raise ValueError(f"Report name mismatch: expected {expected_name!r}, got {existing.get('name')!r}.")
    if not allow_unmanaged_update and not _report_is_manageable(existing, existing):
        raise ValueError(f"Report {report_id!r} is not marked as Codex-managed; pass allow_unmanaged_update=True.")
    validation = _report_project_base_validation(existing, expected_marker=expected_marker)
    return alterios_upsert_report(
        str(existing.get("name") or ""),
        report_id=report_id,
        report_type=str(existing.get("type") or "dashboard"),
        template=template,
        description=existing.get("description"),
        allow_unmanaged_update=True,
        dry_run=dry_run,
        profile=profile,
        project_id=project_id,
    ) | {"template_preflight_validation": validation}


@mcp.tool()
def alterios_validate_report_project_base(
    report_id: str,
    expected_view_id: str | None = None,
    expected_view_name: str | None = None,
    expected_marker: str | None = None,
    view_limit: int = 5,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Validate a report template and optionally read the source view through get-data-simplified."""
    client = _client(profile, project_id)
    report = client.report_by_id(report_id).body
    if not isinstance(report, dict):
        raise ValueError("Report readback returned unexpected payload.")
    validation = _report_project_base_validation(report, expected_view_name=expected_view_name, expected_marker=expected_marker)
    view_readback = None
    if expected_view_id:
        view_readback = client.view_data_simplified(expected_view_id, limit=view_limit, offset=0).as_dict()
        body = view_readback.get("body") if isinstance(view_readback, dict) else None
        rows = None
        if isinstance(body, list):
            rows = body
        elif isinstance(body, dict):
            rows = next((body.get(key) for key in ("items", "rows", "data", "results") if isinstance(body.get(key), list)), None)
        validation["view_readback_ok"] = view_readback.get("status_code") in {200, 201}
        validation["view_row_count"] = len(rows) if isinstance(rows, list) else None
    return {"report": _resource_summary(report), "validation": validation, "view_readback": view_readback}


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
