from __future__ import annotations

import base64
import binascii
import json
import os
import time
from typing import Any
from xml.sax.saxutils import escape as _xml_escape

from mcp.server.fastmcp import FastMCP

from .client import (
    AlteriosClient,
    AlteriosConfig,
    AlteriosRequestError,
    content_update_payload,
    configured_profiles,
    normalize_content_field_value,
    looks_like_uuid,
    listandcount_items,
    report_full_item,
    strip_alterios_metadata,
)
from .discovery import discover_readonly, list_objects, list_projects
from .form_surface import analyze_form_surface
from .profile_smoke import run_profile_smoke
from .services import get_service, list_services, service_to_dict
from .stimulsoft_layout import analyze_stimulsoft_layout
from .write_control import (
    WriteOperation,
    assert_write_allowed,
    build_write_audit,
    classify_rest_write_risk,
    collect_target_ids,
    controlled_write_result,
    is_dangerous_write_risk,
)
from .write_plan import assert_plan_matches_audit, list_write_journal, list_write_plans, load_write_plan

mcp = FastMCP("alterios")


def _client(profile: str | None = None, project_id: str | None = None) -> AlteriosClient:
    return AlteriosClient(AlteriosConfig.from_env(profile=profile).with_project_id(project_id))


def _write_enabled() -> bool:
    return os.environ.get("ALTERIOS_MCP_ALLOW_WRITE") == "1"


def _dangerous_write_enabled() -> bool:
    return os.environ.get("ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE") == "1"


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
    risk_level = classify_rest_write_risk(method, path)
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


def _security_resource_summary(resource: dict[str, Any] | None) -> dict[str, Any] | None:
    if resource is None:
        return None
    return {
        "_id": resource.get("_id"),
        "name": resource.get("name"),
        "email": resource.get("email"),
        "description": resource.get("description"),
        "projectId": resource.get("projectId"),
        "isActive": resource.get("isActive"),
        "rolesIds": resource.get("rolesIds"),
        "groupsIds": resource.get("groupsIds"),
        "projectsIds": resource.get("projectsIds"),
    }


def _filter_items(items: list[dict[str, Any]], search: str | None, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if not search:
        return items
    needle = search.strip().lower()
    if not needle:
        return items
    filtered = []
    for item in items:
        haystack = " ".join(str(item.get(key) or "") for key in keys).lower()
        if needle in haystack:
            filtered.append(item)
    return filtered


def _listandcount_tool_response(
    response: Any,
    *,
    search: str | None = None,
    keys: tuple[str, ...] = ("_id", "name"),
) -> dict[str, Any]:
    payload = response.as_dict()
    if search:
        items = _filter_items(listandcount_items(response.body), search, keys)
        payload["local_filter"] = {"search": search, "matched_count": len(items), "items": items}
    return payload


def _security_resource_operation(
    *,
    collection: str,
    action: str,
    kind: str,
    resource_id: str | None,
    request: dict[str, Any],
    summary: str,
    path_override: str | None = None,
) -> WriteOperation:
    method = "DELETE" if action == "delete" else ("PATCH" if resource_id else "POST")
    path = path_override or (f"/api/{collection}/{resource_id}" if resource_id else f"/api/{collection}")
    sanitized_request = strip_alterios_metadata(request)
    return _resource_operation(
        name=f"{method} {path}",
        kind=kind,
        method=method,
        path=path,
        summary=summary,
        request=sanitized_request,
        risk_level="security",
    )


def _security_payload(existing: dict[str, Any] | None, payload: dict[str, Any], resource_id: str | None) -> dict[str, Any]:
    if not payload:
        raise ValueError("payload must contain at least one field.")
    merged = {**(existing or {}), **payload}
    if resource_id:
        merged["_id"] = resource_id
    return merged


def _delete_readback(client: AlteriosClient, kind: str, resource_id: str) -> dict[str, Any]:
    try:
        if kind == "user":
            body = client.user_by_id(resource_id).body
        elif kind == "user_group":
            body = client.user_group_by_id(resource_id).body
        elif kind == "role":
            body = client.role_by_id(resource_id).body
        else:
            raise ValueError(f"Unsupported delete readback kind: {kind}")
    except AlteriosRequestError:
        return {"deleted": True, "body": None}
    return {"deleted": False, "body": body}


def _find_named_resource(items: Any, name: str) -> dict[str, Any] | None:
    for item in listandcount_items(items):
        if item.get("name") == name:
            return item
    return None


def _extract_response_id(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("_id", "id", "contentId", "uuid"):
            if value.get(key):
                return str(value[key])
        for key in ("body", "data", "result", "value"):
            found = _extract_response_id(value.get(key))
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _extract_response_id(item)
            if found:
                return found
    return None


def _find_content_type(
    client: AlteriosClient,
    *,
    content_type_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any] | None:
    if content_type_id:
        body = client.content_type_by_id(content_type_id).body
        if not isinstance(body, dict):
            raise ValueError("Content type readback returned unexpected payload.")
        return body
    if name:
        return _find_named_resource(client.list_content_types(limit=5000).body, name)
    return None


def _find_shared_content_type(client: AlteriosClient, content_type_id: str) -> dict[str, Any] | None:
    for item in client.list_shared_content_types().body:
        if isinstance(item, dict) and item.get("_id") == content_type_id:
            return item
    return None


def _find_field(
    client: AlteriosClient,
    *,
    content_type_id: str,
    field_id: str | None = None,
    mname: str | None = None,
    name: str | None = None,
) -> dict[str, Any] | None:
    if field_id:
        body = client.field_by_id(field_id).body
        if not isinstance(body, dict):
            raise ValueError("Field readback returned unexpected payload.")
        return body
    body = client.list_fields(content_type_id=content_type_id).body
    if not isinstance(body, list):
        raise ValueError("Field inventory returned unexpected payload.")
    for field in body:
        if not isinstance(field, dict):
            continue
        if mname and field.get("mname") == mname:
            return field
        if name and field.get("name") == name:
            return field
    return None


def _find_group(
    client: AlteriosClient,
    *,
    group_id: str | None = None,
    name: str | None = None,
    include_root: bool = False,
) -> dict[str, Any] | None:
    groups = _response_items(client.list_groups().body)
    if group_id:
        for group in groups:
            if group.get("_id") == group_id:
                return group
        return None
    for group in groups:
        if name and group.get("name") == name and (include_root or not group.get("root")):
            return group
    return None


def _find_user(
    client: AlteriosClient,
    *,
    user_id: str | None = None,
    email: str | None = None,
    name: str | None = None,
) -> dict[str, Any] | None:
    if user_id:
        try:
            body = client.user_by_id(user_id).body
        except AlteriosRequestError:
            return None
        if not isinstance(body, dict):
            raise ValueError("User readback returned unexpected payload.")
        return body
    items = listandcount_items(client.list_users(limit=5000).body)
    normalized_email = email.strip().lower() if email else None
    for item in items:
        if normalized_email and str(item.get("email") or "").lower() == normalized_email:
            return item
        if name:
            haystack = " ".join(
                str(item.get(key) or "") for key in ("name", "firstName", "lastName", "middleName", "email")
            ).lower()
            if name.strip().lower() in haystack:
                return item
    return None


def _find_user_group(
    client: AlteriosClient,
    *,
    user_group_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any] | None:
    if user_group_id:
        try:
            body = client.user_group_by_id(user_group_id).body
        except AlteriosRequestError:
            return None
        if not isinstance(body, dict):
            raise ValueError("User group readback returned unexpected payload.")
        return body
    if name:
        return _find_named_resource(client.list_user_groups(limit=5000).body, name)
    return None


def _find_role(
    client: AlteriosClient,
    *,
    role_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any] | None:
    if role_id:
        try:
            body = client.role_by_id(role_id).body
        except AlteriosRequestError:
            return None
        if not isinstance(body, dict):
            raise ValueError("Role readback returned unexpected payload.")
        return body
    if name:
        return _find_named_resource(client.list_roles(limit=5000).body, name)
    return None


def _find_root_group(client: AlteriosClient) -> dict[str, Any] | None:
    for group in _response_items(client.list_groups().body):
        if group.get("root") or group.get("name") == "root":
            return group
    return None


def _find_help(
    client: AlteriosClient,
    *,
    help_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any] | None:
    if help_id:
        body = client.help_by_id(help_id).body
        if not isinstance(body, dict):
            raise ValueError("Help readback returned unexpected payload.")
        return body
    if name:
        for item in _response_items(client.list_helps().body):
            if item.get("name") == name:
                return item
    return None


def _assert_help_managed_or_allowed(resource: dict[str, Any], *, allow_unmanaged_update: bool) -> None:
    if allow_unmanaged_update:
        return
    if MANAGED_MARKER in str(resource.get("description") or "") or MANAGED_MARKER in str(resource.get("value") or ""):
        return
    raise ValueError(f"Help {resource.get('_id')!r} is not marked as Codex-managed; pass allow_unmanaged_update=True.")


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


def _response_body(value: Any) -> Any:
    if isinstance(value, dict) and "body" in value:
        return value.get("body")
    return value


def _material_module_operation(
    *,
    module_name: str,
    field_name_prefix: str,
    fields: list[dict[str, Any]],
    content_type_id: str | None,
    view_id: str | None,
    add_form_id: str | None,
    edit_form_id: str | None,
    list_form_id: str | None,
    group_id: str | None,
    parent_group_id: str | None,
    names: dict[str, str],
    content_name_template: str | None,
    icon_id: str | None,
    add_icon_id: str | None,
    edit_icon_id: str | None,
    save_icon_id: str | None,
    allow_unmanaged_update: bool,
) -> WriteOperation:
    request = {
        "moduleName": module_name,
        "fieldNamePrefix": field_name_prefix,
        "fields": fields,
        "contentTypeId": content_type_id,
        "viewId": view_id,
        "addFormId": add_form_id,
        "editFormId": edit_form_id,
        "listFormId": list_form_id,
        "groupId": group_id,
        "parentGroupId": parent_group_id,
        "names": names,
        "contentNameTemplate": content_name_template,
        "icons": {
            "group": icon_id,
            "add": add_icon_id,
            "edit": edit_icon_id,
            "save": save_icon_id,
        },
        "allowUnmanagedUpdate": allow_unmanaged_update,
    }
    return _resource_operation(
        name="SCENARIO create_material_module",
        kind="scenario_material_module",
        risk_level="write",
        method="POST",
        path="scenario://material-module",
        summary=(
            "Create or update a complete Alterios material module: content type, fields, view, "
            "add/edit/list forms, and menu group."
        ),
        request={key: value for key, value in request.items() if value is not None},
    )


def _normalize_material_module_fields(
    fields: list[dict[str, Any]],
    *,
    field_name_prefix: str,
) -> list[dict[str, Any]]:
    if not isinstance(fields, list) or not fields:
        raise ValueError("fields must contain at least one field definition.")
    normalized: list[dict[str, Any]] = []
    seen_mnames: set[str] = set()
    for index, raw in enumerate(fields):
        if not isinstance(raw, dict):
            raise ValueError("Each field definition must be a JSON object.")
        name = str(raw.get("name") or "").strip()
        mname = str(raw.get("mname") or "").strip()
        field_type = str(raw.get("field_type") or raw.get("type") or "").strip()
        if not name:
            raise ValueError(f"fields[{index}].name must not be empty.")
        if not mname:
            raise ValueError(f"fields[{index}].mname must not be empty.")
        if not field_type:
            raise ValueError(f"fields[{index}].field_type must not be empty.")
        if mname in seen_mnames:
            raise ValueError(f"Duplicate field mname {mname!r}.")
        seen_mnames.add(mname)
        order = raw.get("order")
        normalized_field: dict[str, Any] = {
            "name": name,
            "mname": mname,
            "field_type": field_type,
            "view_mname": str(raw.get("view_mname") or _material_view_mname(mname, field_name_prefix)).strip(),
            "order": int(order) if order is not None else index,
        }
        for source_key, target_key in (
            ("field_id", "field_id"),
            ("description", "description"),
            ("help", "help"),
            ("tooltip", "tooltip"),
            ("required", "required"),
            ("default_value", "default_value"),
            ("defaultValue", "default_value"),
            ("form_display", "form_display"),
            ("formDisplay", "form_display"),
            ("settings", "settings"),
        ):
            if source_key in raw:
                normalized_field[target_key] = raw[source_key]
        normalized.append(normalized_field)
    return normalized


def _material_view_mname(field_mname: str, field_name_prefix: str) -> str:
    prefix = f"{field_name_prefix}_"
    if field_name_prefix and field_mname.startswith(prefix):
        return field_mname.removeprefix(prefix)
    if field_mname.startswith("field_"):
        return field_mname.removeprefix("field_")
    return field_mname


def _material_module_names(module_name: str, names: dict[str, str] | None = None) -> dict[str, str]:
    overrides = names or {}
    return {
        "content_type": overrides.get("content_type") or module_name,
        "view": overrides.get("view") or f"{module_name}. Список",
        "add_form": overrides.get("add_form") or f"{module_name}. Добавить",
        "edit_form": overrides.get("edit_form") or f"{module_name}. Карточка",
        "list_form": overrides.get("list_form") or module_name,
        "group": overrides.get("group") or module_name,
    }


def _material_flex_styles() -> dict[str, Any]:
    return {"flexGrow": 1, "flexBasis": 0, "flexShrink": 1, "flexBasisUnit": "%"}


def _material_row_styles() -> dict[str, Any]:
    return _material_flex_styles()


def _material_content_display_fields(fields: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        field["mname"]: {"order": int(field.get("order", index)), "title": field["name"]}
        for index, field in enumerate(fields)
    }


def _material_view_display_fields(fields: list[dict[str, Any]]) -> dict[str, Any]:
    display: dict[str, Any] = {"_id": {"order": 0, "hidden": True}}
    for index, field in enumerate(fields, start=1):
        field_order = int(field.get("order", index - 1)) + 1
        display[field["view_mname"]] = {"order": field_order, "hidden": False, "title": field["name"]}
    return display


def _material_content_form_row(module_name: str, content_type_id: str, fields: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "cells": [
            {
                "name": module_name,
                "type": "content",
                "adding": {},
                "params": {
                    "openId": False,
                    "createNew": True,
                    "contentTypeId": content_type_id,
                    "engineVersion": None,
                },
                "styles": _material_flex_styles(),
                "editing": {},
                "emitting": {},
                "reporting": {"reports": []},
                "displaying": {"fields": _material_content_display_fields(fields), "header": {}, "editForm": {}},
                "cellActionContainers": [],
            }
        ],
        "styles": _material_row_styles(),
        "reverse": False,
    }


def _material_view_data_row(module_name: str, view_id: str, fields: list[dict[str, Any]], *, editable: bool) -> dict[str, Any]:
    return {
        "cells": [
            {
                "name": module_name,
                "type": "view_data",
                "adding": {},
                "params": {"openId": True, "viewId": view_id, "engineVersion": "v2"},
                "styles": _material_flex_styles(),
                "editing": {"enabled": bool(editable)},
                "emitting": {},
                "reporting": {"reports": []},
                "displaying": {"fields": _material_view_display_fields(fields), "header": {}, "editForm": {}},
                "cellActionContainers": [],
            }
        ],
        "styles": _material_row_styles(),
        "reverse": False,
    }


def _material_comments_row() -> dict[str, Any]:
    return {
        "cells": [
            {
                "name": "Комментарии",
                "type": "comments_list",
                "adding": {},
                "params": {"openId": True, "entity": "any"},
                "styles": _material_flex_styles(),
                "editing": {},
                "emitting": {},
                "reporting": {},
                "displaying": {"fields": {}, "header": {"title": "Комментарии", "position": "top_left"}},
                "cellActionContainers": [],
            }
        ],
        "styles": _material_row_styles(),
        "reverse": False,
    }


def _material_open_form_container(
    *,
    title: str,
    icon_id: str | None,
    form_id: str,
    form_name: str,
    view_entity_id: str,
    position: str,
) -> dict[str, Any]:
    container: dict[str, Any] = {
        "type": "action",
        "title": title,
        "styles": {},
        "actions": [
            {
                "_id": form_id,
                "name": form_name,
                "type": "forms",
                "openInDialog": True,
                "openInNewTab": False,
                "viewEntityId": view_entity_id,
                "argumentsConfig": {},
            }
        ],
        "position": position,
        "default": title == "Добавить",
        "conditions": [],
    }
    if icon_id:
        container["iconId"] = icon_id
    return container


def _material_save_action_container(icon_id: str | None) -> dict[str, Any]:
    container: dict[str, Any] = {
        "type": "action",
        "title": "Сохранить",
        "styles": {},
        "actions": [{"_id": None, "type": "data_managing", "argumentsConfig": {}, "dataManagingType": "submit_all"}],
        "position": "bottom_left",
        "conditions": [],
    }
    if icon_id:
        container["iconId"] = icon_id
    return container


def _material_view_data_list_row(
    *,
    module_name: str,
    view_id: str,
    view_entity_id: str,
    add_form_id: str,
    add_form_name: str,
    edit_form_id: str,
    edit_form_name: str,
    fields: list[dict[str, Any]],
    add_icon_id: str | None,
    edit_icon_id: str | None,
) -> dict[str, Any]:
    return {
        "cells": [
            {
                "name": module_name,
                "type": "view_data_list",
                "adding": {"items": []},
                "params": {"openId": True, "viewId": view_id, "engineVersion": "v2"},
                "styles": _material_flex_styles(),
                "editing": {},
                "emitting": {"listeners": []},
                "reporting": {"reports": []},
                "displaying": {
                    "list": {"pageSizeOptions": []},
                    "fields": _material_view_display_fields(fields),
                    "header": {},
                    "editForm": {},
                },
                "cellActionContainers": [
                    _material_open_form_container(
                        title="Добавить",
                        icon_id=add_icon_id,
                        form_id=add_form_id,
                        form_name=add_form_name,
                        view_entity_id=view_entity_id,
                        position="top_left",
                    )
                ],
                "valueActionContainers": [
                    _material_open_form_container(
                        title="Редактировать",
                        icon_id=edit_icon_id,
                        form_id=edit_form_id,
                        form_name=edit_form_name,
                        view_entity_id=view_entity_id,
                        position="toolbar",
                    )
                ],
            }
        ],
        "styles": _material_row_styles(),
        "reverse": False,
    }


def _material_module_preflight(
    client: AlteriosClient,
    *,
    names: dict[str, str],
    fields: list[dict[str, Any]],
    content_type_id: str | None,
    view_id: str | None,
    add_form_id: str | None,
    edit_form_id: str | None,
    list_form_id: str | None,
    group_id: str | None,
    parent_group_id: str | None,
    allow_unmanaged_update: bool,
) -> dict[str, Any]:
    content_type = _find_content_type(client, content_type_id=content_type_id, name=names["content_type"])
    if content_type:
        _assert_managed_or_allowed(content_type, kind="Content type", allow_unmanaged_update=allow_unmanaged_update)

    field_preflight = []
    if content_type and content_type.get("_id"):
        for field in fields:
            existing_field = _find_field(
                client,
                content_type_id=str(content_type["_id"]),
                field_id=field.get("field_id"),
                mname=field["mname"],
                name=field["name"],
            )
            if existing_field:
                _assert_managed_or_allowed(existing_field, kind="Field", allow_unmanaged_update=allow_unmanaged_update)
            field_preflight.append({"field": field["mname"], "existing": _resource_summary(existing_field)})

    view = _find_view(client, view_id=view_id, name=names["view"])
    if view:
        _assert_managed_or_allowed(view, kind="View", allow_unmanaged_update=allow_unmanaged_update)

    view_entity = None
    if view and view.get("_id"):
        view_entity = _find_view_entity(
            client,
            view_id=str(view["_id"]),
            name=names["content_type"],
            entity_type="content",
        )

    forms = {
        "add": _find_form(client, form_id=add_form_id, name=names["add_form"]),
        "edit": _find_form(client, form_id=edit_form_id, name=names["edit_form"]),
        "list": _find_form(client, form_id=list_form_id, name=names["list_form"]),
    }
    for kind, form in forms.items():
        if form:
            _assert_managed_or_allowed(form, kind=f"{kind} form", allow_unmanaged_update=allow_unmanaged_update)

    group = _find_group(client, group_id=group_id, name=names["group"])
    if group:
        _assert_managed_or_allowed(group, kind="Group", allow_unmanaged_update=allow_unmanaged_update)
    parent = _find_group(client, group_id=parent_group_id, include_root=True) if parent_group_id else _find_root_group(client)
    if parent_group_id and not parent:
        raise ValueError(f"Parent group {parent_group_id!r} was not found.")

    return {
        "content_type": _resource_summary(content_type),
        "fields": field_preflight,
        "view": _resource_summary(view),
        "view_entity": _resource_summary(view_entity),
        "forms": {key: _resource_summary(value) for key, value in forms.items()},
        "group": _resource_summary(group),
        "parent_group": _resource_summary(parent),
    }


def _material_module_plan_preview(
    *,
    module_name: str,
    names: dict[str, str],
    fields: list[dict[str, Any]],
    field_name_prefix: str,
    content_type_id: str | None,
    view_id: str | None,
    add_form_id: str | None,
    edit_form_id: str | None,
    list_form_id: str | None,
    group_id: str | None,
    parent_group_id: str | None,
    icon_id: str | None,
    add_icon_id: str | None,
    edit_icon_id: str | None,
    save_icon_id: str | None,
) -> dict[str, Any]:
    planned_content_type_id = content_type_id or "$content_type_id"
    planned_view_id = view_id or "$view_id"
    planned_view_entity_id = "$view_entity_id"
    planned_add_form_id = add_form_id or "$add_form_id"
    planned_edit_form_id = edit_form_id or "$edit_form_id"
    planned_list_form_id = list_form_id or "$list_form_id"
    return {
        "steps": [
            "upsert_content_type",
            "upsert_fields",
            "upsert_view",
            "upsert_view_entity",
            "upsert_view_fields",
            "upsert_add_form",
            "upsert_edit_form",
            "upsert_list_form",
            "upsert_group",
            "readback_summary",
        ],
        "content_type": {
            "name": names["content_type"],
            "content_type_id": content_type_id,
            "field_name_prefix": field_name_prefix,
        },
        "fields": fields,
        "view": {
            "name": names["view"],
            "view_id": view_id,
            "entity": {
                "name": names["content_type"],
                "type": "content",
                "config": {
                    "main": True,
                    "position": {"x": -260, "y": -180},
                    "contentTypesIds": [planned_content_type_id],
                },
            },
        },
        "forms": {
            "add": {
                "name": names["add_form"],
                "form_id": add_form_id,
                "tabs": [{"name": None, "rows": [_material_content_form_row(module_name, planned_content_type_id, fields)]}],
                "formActionContainers": [_material_save_action_container(save_icon_id)],
            },
            "edit": {
                "name": names["edit_form"],
                "form_id": edit_form_id,
                "tabs": [
                    {
                        "name": None,
                        "rows": [
                            _material_view_data_row(module_name, planned_view_id, fields, editable=True),
                            _material_comments_row(),
                        ],
                    }
                ],
                "formActionContainers": [_material_save_action_container(save_icon_id)],
            },
            "list": {
                "name": names["list_form"],
                "form_id": list_form_id,
                "tabs": [
                    {
                        "name": None,
                        "rows": [
                            _material_view_data_list_row(
                                module_name=module_name,
                                view_id=planned_view_id,
                                view_entity_id=planned_view_entity_id,
                                add_form_id=planned_add_form_id,
                                add_form_name=names["add_form"],
                                edit_form_id=planned_edit_form_id,
                                edit_form_name=names["edit_form"],
                                fields=fields,
                                add_icon_id=add_icon_id,
                                edit_icon_id=edit_icon_id,
                            )
                        ],
                    }
                ],
                "formActionContainers": [],
            },
        },
        "group": {
            "name": names["group"],
            "group_id": group_id,
            "parent_group_id": parent_group_id,
            "form_id": planned_list_form_id,
            "icon_id": icon_id,
        },
    }


def _report_tab_operation(
    *,
    source_view_id: str,
    target_form_id: str,
    report_name: str,
    report_id: str | None,
    report_type: str,
    tab_name: str,
    cell_name: str,
    template: str | dict[str, Any],
    marker: str,
    context_content_id: str | None,
    expected_context_row_count: int | None,
    open_id: bool,
    fullscreen_mode: bool,
    replace_existing_tab: bool,
    allow_unmanaged_update: bool,
) -> WriteOperation:
    request = {
        "sourceViewId": source_view_id,
        "targetFormId": target_form_id,
        "reportName": report_name,
        "reportId": report_id,
        "reportType": report_type,
        "tabName": tab_name,
        "cellName": cell_name,
        "template": template,
        "marker": marker,
        "contextContentId": context_content_id,
        "expectedContextRowCount": expected_context_row_count,
        "openId": open_id,
        "fullscreenMode": fullscreen_mode,
        "replaceExistingTab": replace_existing_tab,
        "allowUnmanagedUpdate": allow_unmanaged_update,
    }
    return _resource_operation(
        name="SCENARIO create_report_tab",
        kind="scenario_report_tab",
        risk_level="write",
        method="POST",
        path="scenario://report-tab",
        summary=(
            "Create or update an Alterios report, attach it as an openId form tab, "
            "and verify Project Database source/context readback."
        ),
        request={key: value for key, value in request.items() if value is not None},
    )


def _view_rows_from_response(value: Any) -> list[dict[str, Any]] | None:
    body = value.get("body") if isinstance(value, dict) and "body" in value else value
    if isinstance(body, list):
        return [item for item in body if isinstance(item, dict)]
    if isinstance(body, dict):
        for key in ("rows", "items", "data", "results", "values"):
            rows = body.get(key)
            if isinstance(rows, list):
                return [item for item in rows if isinstance(item, dict)]
    return None


def _view_row_count(value: Any) -> int | None:
    rows = _view_rows_from_response(value)
    return len(rows) if rows is not None else None


def _report_column_type(field: dict[str, Any]) -> str:
    source = field.get("contentTypeField") if isinstance(field.get("contentTypeField"), dict) else field
    raw_type = str(source.get("type") or "").lower()
    if raw_type in {"number", "integer", "float", "decimal"}:
        return "System.Decimal"
    if raw_type in {"boolean", "bool", "checkbox"}:
        return "System.Boolean"
    if raw_type in {"date", "datetime", "time"}:
        return "System.DateTime"
    return "System.String"


def _project_database_columns(view_fields: list[dict[str, Any]]) -> list[dict[str, str]]:
    columns: list[dict[str, str]] = [{"name": "_id", "alias": "ID", "type": "System.String"}]
    seen = {"_id"}
    ordered = sorted(view_fields, key=lambda item: (int(item.get("order") or 0), str(item.get("mname") or "")))
    for field in ordered:
        mname = str(field.get("mname") or field.get("attribute") or "").strip()
        if not mname or mname in seen:
            continue
        seen.add(mname)
        columns.append(
            {
                "name": mname,
                "alias": str(field.get("alias") or field.get("name") or mname),
                "type": _report_column_type(field),
            }
        )
    return columns


def _project_database_dashboard_template(
    *,
    report_name: str,
    marker: str,
    source_view_id: str,
    source_view_name: str,
    columns: list[dict[str, str]],
) -> dict[str, Any]:
    column_items = {
        str(index): {"Name": column["name"], "Alias": column["alias"], "Type": column["type"]}
        for index, column in enumerate(columns)
    }
    connection = json.dumps(
        {"type": "view-data-v2", "filter": {"viewId": source_view_id}},
        ensure_ascii=False,
        sort_keys=True,
    )
    return {
        "CodexMarker": marker,
        "ReportName": report_name,
        "Alterios": {
            "sourceViewId": source_view_id,
            "sourceViewName": source_view_name,
            "templateKind": "report_tab_project_database",
        },
        "Dictionary": {
            "Databases": {
                "0": {
                    "Ident": "StiDatabase",
                    "Name": "Project Database",
                    "Alias": "Project Database",
                    "ServiceName": "Project Database",
                    "ConnectionString": connection,
                }
            },
            "DataSources": {
                "0": {
                    "Ident": "StiDataTableSource",
                    "Name": source_view_name,
                    "Alias": source_view_name,
                    "NameInSource": source_view_name,
                    "ServiceName": "Project Database",
                    "Columns": column_items,
                }
            },
        },
        "Pages": {
            "0": {
                "Ident": "StiDashboard",
                "Name": "ReportTabDashboard",
                "Width": 10,
                "Height": 7,
                "Components": {
                    "0": {
                        "Ident": "StiTextElement",
                        "Name": "ReportTitle",
                        "ClientRectangle": "0.2,0.2,9.4,0.5",
                        "Text": report_name,
                    },
                    "1": {
                        "Ident": "StiTableElement",
                        "Name": "SourceRows",
                        "ClientRectangle": "0.2,0.9,9.4,5.8",
                        "DataSourceName": source_view_name,
                    },
                },
            }
        },
    }


def _report_tab_row(*, report_id: str, cell_name: str, open_id: bool, fullscreen_mode: bool) -> dict[str, Any]:
    params: dict[str, Any] = {"reportId": report_id, "fullscreenMode": fullscreen_mode}
    if open_id:
        params["openId"] = True
    return {
        "cells": [
            {
                "name": cell_name,
                "type": "report",
                "adding": {},
                "params": params,
                "styles": _material_flex_styles(),
                "editing": {},
                "emitting": {},
                "reporting": {"reports": []},
                "displaying": {"fields": {}, "header": {}},
                "cellActionContainers": [],
            }
        ],
        "styles": _material_row_styles(),
        "reverse": False,
    }


def _tabs_with_report_tab(
    form: dict[str, Any],
    *,
    tab_name: str,
    report_id: str,
    cell_name: str,
    open_id: bool,
    fullscreen_mode: bool,
    replace_existing_tab: bool,
) -> list[dict[str, Any]]:
    tabs = json.loads(json.dumps(form.get("tabs") or [], ensure_ascii=False))
    if not isinstance(tabs, list):
        raise ValueError("Form tabs must be a list.")
    target_row = _report_tab_row(
        report_id=report_id,
        cell_name=cell_name,
        open_id=open_id,
        fullscreen_mode=fullscreen_mode,
    )
    for tab in tabs:
        if isinstance(tab, dict) and tab.get("name") == tab_name:
            if not replace_existing_tab:
                raise ValueError(f"Report tab {tab_name!r} already exists; pass replace_existing_tab=True.")
            tab["rows"] = [target_row]
            return tabs
    tabs.append({"name": tab_name, "rows": [target_row]})
    return tabs


def _find_report_tab_cell(
    form: dict[str, Any],
    *,
    tab_name: str,
    report_id: str,
) -> dict[str, Any] | None:
    tabs = form.get("tabs") or []
    if not isinstance(tabs, list):
        return None
    for tab in tabs:
        if not isinstance(tab, dict) or tab.get("name") != tab_name:
            continue
        for row in tab.get("rows") or []:
            for cell in (row or {}).get("cells") or []:
                if isinstance(cell, dict) and cell.get("type") == "report":
                    params = cell.get("params") or {}
                    if isinstance(params, dict) and params.get("reportId") == report_id:
                        return cell
    return None


def _process_flow_operation(
    *,
    task_form_name: str,
    task_form_id: str | None,
    diagram_name: str,
    diagram_id: str | None,
    content_type_id: str,
    script_refs: list[dict[str, Any]],
    bpmn_xml: str,
    content_id: str | None,
    start_process_smoke: bool,
    complete_task: bool,
    expected_user_task_name: str,
    expected_task_form_id: str | None,
    allow_unmanaged_update: bool,
) -> WriteOperation:
    request = {
        "taskFormName": task_form_name,
        "taskFormId": task_form_id,
        "diagramName": diagram_name,
        "diagramId": diagram_id,
        "contentTypeId": content_type_id,
        "scriptRefs": script_refs,
        "bpmnXml": bpmn_xml,
        "contentId": content_id,
        "startProcessSmoke": start_process_smoke,
        "completeTask": complete_task,
        "expectedUserTaskName": expected_user_task_name,
        "expectedTaskFormId": expected_task_form_id,
        "allowUnmanagedUpdate": allow_unmanaged_update,
    }
    return _resource_operation(
        name="SCENARIO create_process_flow",
        kind="scenario_process_flow",
        risk_level="workflow_side_effect" if (content_id and start_process_smoke) or complete_task else "write",
        method="POST",
        path="scenario://process-flow",
        summary=(
            "Create or update a task form, validate script references, save BPMN, "
            "and optionally smoke-test process start/task flow."
        ),
        request={key: value for key, value in request.items() if value is not None},
    )


def _normalize_process_script_refs(script_refs: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if script_refs is None:
        return []
    if not isinstance(script_refs, list):
        raise ValueError("script_refs must be a list.")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(script_refs):
        if not isinstance(raw, dict):
            raise ValueError("Each script ref must be a JSON object.")
        script_id = str(raw.get("script_id") or raw.get("scriptId") or raw.get("_id") or "").strip()
        name = str(raw.get("name") or "").strip() or None
        script_type = str(raw.get("type") or raw.get("script_type") or "diagram").strip()
        expected_body_contains = raw.get("expected_body_contains") or raw.get("expectedBodyContains") or []
        if isinstance(expected_body_contains, str):
            expected_body_contains = [expected_body_contains]
        if not script_id and not name:
            raise ValueError(f"script_refs[{index}] requires script_id or name.")
        if script_type not in {"manual", "event", "diagram"}:
            raise ValueError("script_refs[].type must be one of: manual, event, diagram.")
        key = script_id or name or str(index)
        if key in seen:
            raise ValueError(f"Duplicate script ref {key!r}.")
        seen.add(key)
        normalized.append(
            {
                "script_id": script_id or None,
                "name": name,
                "type": script_type,
                "expected_body_contains": [str(item) for item in expected_body_contains],
            }
        )
    return normalized


def _safe_bpmn_id(value: str) -> str:
    normalized = "".join(ch if ch.isalnum() else "_" for ch in value.strip())
    normalized = "_".join(part for part in normalized.split("_") if part)
    return normalized or "process"


def _xml_attr(value: Any) -> str:
    return _xml_escape(str(value), {'"': "&quot;"})


def _build_simple_user_task_bpmn(
    *,
    process_id: str,
    process_name: str,
    task_id: str,
    task_name: str,
    task_form_id: str,
    start_form_id: str | None = None,
    next_flow_id: str = "Flow_to_end",
    next_flow_name: str = "Complete",
) -> str:
    safe_process_id = _safe_bpmn_id(process_id)
    safe_task_id = _safe_bpmn_id(task_id)
    safe_next_flow_id = _safe_bpmn_id(next_flow_id)
    safe_start_id = f"StartEvent_{safe_process_id}"
    safe_end_id = f"EndEvent_{safe_process_id}"
    safe_start_to_task_flow_id = f"Flow_{safe_process_id}_start_to_task"
    effective_start_form_id = start_form_id or task_form_id
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:camunda="http://camunda.org/schema/1.0/bpmn" '
        'id="Definitions_1" targetNamespace="http://bpmn.io/schema/bpmn">\n'
        f'  <bpmn:process id="{_xml_attr(safe_process_id)}" name="{_xml_attr(process_name)}" isExecutable="true">\n'
        f'    <bpmn:startEvent id="{_xml_attr(safe_start_id)}" name="Start" camunda:formKey="{_xml_attr(effective_start_form_id)}">\n'
        f'      <bpmn:outgoing>{_xml_attr(safe_start_to_task_flow_id)}</bpmn:outgoing>\n'
        "    </bpmn:startEvent>\n"
        f'    <bpmn:sequenceFlow id="{_xml_attr(safe_start_to_task_flow_id)}" '
        f'sourceRef="{_xml_attr(safe_start_id)}" targetRef="{_xml_attr(safe_task_id)}" />\n'
        f'    <bpmn:userTask id="{_xml_attr(safe_task_id)}" name="{_xml_attr(task_name)}" '
        f'camunda:formKey="{_xml_attr(task_form_id)}" camunda:savable="true">\n'
        f'      <bpmn:incoming>{_xml_attr(safe_start_to_task_flow_id)}</bpmn:incoming>\n'
        f'      <bpmn:outgoing>{_xml_attr(safe_next_flow_id)}</bpmn:outgoing>\n'
        "    </bpmn:userTask>\n"
        f'    <bpmn:sequenceFlow id="{_xml_attr(safe_next_flow_id)}" name="{_xml_attr(next_flow_name)}" '
        f'sourceRef="{_xml_attr(safe_task_id)}" targetRef="{_xml_attr(safe_end_id)}" />\n'
        f'    <bpmn:endEvent id="{_xml_attr(safe_end_id)}" name="End">\n'
        f'      <bpmn:incoming>{_xml_attr(safe_next_flow_id)}</bpmn:incoming>\n'
        "    </bpmn:endEvent>\n"
        "  </bpmn:process>\n"
        "</bpmn:definitions>"
    )


def _bpmn_xml_contains_form_key(bpmn_xml: str, form_id: str) -> bool:
    return f'formKey="{form_id}"' in bpmn_xml or f"formKey='{form_id}'" in bpmn_xml


def _bpmn_xml_script_refs(bpmn_xml: str) -> list[str]:
    refs: list[str] = []
    for marker in ("scriptId", "scriptRef", "script"):
        pattern = f"{marker}="
        start = 0
        while True:
            found = bpmn_xml.find(pattern, start)
            if found < 0:
                break
            quote_index = found + len(pattern)
            if quote_index >= len(bpmn_xml):
                break
            quote = bpmn_xml[quote_index]
            if quote not in {"'", '"'}:
                start = quote_index + 1
                continue
            end = bpmn_xml.find(quote, quote_index + 1)
            if end < 0:
                break
            value = bpmn_xml[quote_index + 1 : end].strip()
            if value:
                refs.append(value)
            start = end + 1
    return list(dict.fromkeys(refs))


def _process_flow_validate_scripts(
    client: AlteriosClient,
    script_refs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    for ref in script_refs:
        script = _find_script(client, script_id=ref.get("script_id"), name=ref.get("name"))
        if not script:
            label = ref.get("script_id") or ref.get("name")
            raise ValueError(f"Script {label!r} was not found.")
        expected_type = ref.get("type")
        actual_type = script.get("type")
        if expected_type and actual_type and actual_type != expected_type:
            raise ValueError(
                f"Script {script.get('_id')!r} type mismatch: expected {expected_type!r}, got {actual_type!r}."
            )
        body = str(script.get("body") or "")
        missing = [needle for needle in ref.get("expected_body_contains") or [] if needle not in body]
        if missing:
            raise ValueError(f"Script {script.get('_id')!r} body is missing required fragments: {missing!r}.")
        validated.append(
            {
                "_id": script.get("_id"),
                "name": script.get("name"),
                "type": actual_type,
                "active": script.get("active"),
                "expected_body_contains": ref.get("expected_body_contains") or [],
            }
        )
    return validated


def _process_task_form_tabs(title: str, body: str | None = None) -> list[dict[str, Any]]:
    html = body or f"<div><strong>{_xml_attr(title)}</strong></div>"
    return [
        {
            "name": None,
            "rows": [
                {
                    "cells": [
                        {
                            "name": title,
                            "type": "html",
                            "adding": {},
                            "params": {"html": html},
                            "styles": _material_flex_styles(),
                            "editing": {},
                            "emitting": {"listeners": []},
                            "reporting": {"reports": []},
                            "displaying": {"fields": {}, "header": {"title": title, "position": "top_left"}},
                            "cellActionContainers": [],
                        }
                    ],
                    "styles": _material_row_styles(),
                    "reverse": False,
                }
            ],
        }
    ]


def _process_flow_preflight(
    client: AlteriosClient,
    *,
    task_form_id: str | None,
    task_form_name: str,
    diagram_id: str | None,
    diagram_name: str,
    script_refs: list[dict[str, Any]],
    allow_unmanaged_update: bool,
) -> dict[str, Any]:
    task_form = _find_form(client, form_id=task_form_id, name=task_form_name)
    if task_form:
        _assert_managed_or_allowed(task_form, kind="Task form", allow_unmanaged_update=allow_unmanaged_update)
    diagram = _find_diagram(client, diagram_id=diagram_id, name=diagram_name)
    if diagram:
        _assert_managed_or_allowed(diagram, kind="Diagram", allow_unmanaged_update=allow_unmanaged_update)
    scripts = _process_flow_validate_scripts(client, script_refs)
    return {
        "task_form": task_form,
        "diagram": diagram,
        "scripts": scripts,
    }


def _process_task_from_tasks(
    tasks: list[dict[str, Any]],
    *,
    expected_form_id: str | None,
    expected_name: str | None,
) -> dict[str, Any] | None:
    for task in tasks:
        if expected_form_id and task.get("formId") not in {expected_form_id, None}:
            continue
        if expected_name and task.get("name") and task.get("name") != expected_name:
            continue
        return task
    return tasks[0] if tasks else None


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
def alterios_list_write_plans(profile: str, project_id: str, limit: int = 20) -> dict[str, Any]:
    """List stored dry-run write plans for a profile/project target."""
    if limit < 1 or limit > 200:
        raise ValueError("limit must be between 1 and 200.")
    return {
        "profile": profile,
        "project_id": project_id,
        "plans": list_write_plans(profile=profile, project_id=project_id, limit=limit),
    }


@mcp.tool()
def alterios_get_write_plan(plan_id: str, profile: str, project_id: str) -> dict[str, Any]:
    """Read one stored dry-run write plan by plan_id."""
    if not plan_id.strip():
        raise ValueError("plan_id must not be empty.")
    return load_write_plan(plan_id=plan_id, profile=profile, project_id=project_id)


@mcp.tool()
def alterios_write_journal(profile: str, project_id: str, limit: int = 50) -> dict[str, Any]:
    """Read recent write-plan and write-execution journal entries."""
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500.")
    return {
        "profile": profile,
        "project_id": project_id,
        "entries": list_write_journal(profile=profile, project_id=project_id, limit=limit),
    }


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
def alterios_list_content_types(
    limit: int = 1000,
    offset: int = 0,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read Alterios content types through the typed listandcount route."""
    return _client(profile, project_id).list_content_types(limit=limit, offset=offset).as_dict()


@mcp.tool()
def alterios_list_users(
    limit: int = 1000,
    offset: int = 0,
    search: str | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read Alterios users through the typed security listandcount route."""
    response = _client(profile, project_id).list_users(limit=limit, offset=offset)
    return _listandcount_tool_response(response, search=search, keys=("_id", "name", "email", "firstName", "lastName"))


@mcp.tool()
def alterios_get_user(
    user_id: str,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read one Alterios user by ID through the typed security route."""
    return _client(profile, project_id).user_by_id(user_id).as_dict()


@mcp.tool()
def alterios_list_user_groups(
    limit: int = 1000,
    offset: int = 0,
    search: str | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read Alterios user groups through the typed security listandcount route."""
    response = _client(profile, project_id).list_user_groups(limit=limit, offset=offset)
    return _listandcount_tool_response(response, search=search, keys=("_id", "name", "description"))


@mcp.tool()
def alterios_get_user_group(
    user_group_id: str,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read one Alterios user group by ID through the typed security route."""
    return _client(profile, project_id).user_group_by_id(user_group_id).as_dict()


@mcp.tool()
def alterios_list_roles(
    limit: int = 1000,
    offset: int = 0,
    search: str | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read Alterios roles through the typed security listandcount route."""
    response = _client(profile, project_id).list_roles(limit=limit, offset=offset)
    return _listandcount_tool_response(response, search=search, keys=("_id", "name", "description", "code"))


@mcp.tool()
def alterios_get_role(
    role_id: str,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read one Alterios role by ID through the typed security route."""
    return _client(profile, project_id).role_by_id(role_id).as_dict()


@mcp.tool()
def alterios_file_metadata(
    file_ids: list[str],
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read Alterios file metadata for one or more file IDs."""
    return _client(profile, project_id).file_metadata(file_ids).as_dict()


@mcp.tool()
def alterios_upsert_user(
    payload: dict[str, Any],
    user_id: str | None = None,
    lookup_email: str | None = None,
    lookup_name: str | None = None,
    expected_email: str | None = None,
    allow_create: bool = False,
    dry_run: bool = True,
    allow_destructive: bool = False,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or create/update an Alterios user. Classified as security write."""
    client = _client(profile, project_id)
    existing = _find_user(client, user_id=user_id, email=lookup_email, name=lookup_name)
    if not existing and not allow_create:
        raise ValueError("User was not found; pass allow_create=True only after security review.")
    if existing and expected_email and str(existing.get("email") or "").lower() != expected_email.strip().lower():
        raise ValueError(f"User email mismatch: expected {expected_email!r}, got {existing.get('email')!r}.")
    resource_id = user_id or (str(existing.get("_id")) if existing and existing.get("_id") else None)
    planned_payload = _security_payload(existing, payload, resource_id)
    operation = _security_resource_operation(
        collection="users",
        action="upsert",
        kind="user",
        resource_id=resource_id,
        request=planned_payload,
        summary="Create or update an Alterios user and verify through user readback.",
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
    response_payload: dict[str, Any] = {
        "preflight": _security_resource_summary(existing),
        "diff": _resource_diff(existing, planned_payload, tuple(sorted(planned_payload.keys()))),
        "planned_payload": strip_alterios_metadata(planned_payload),
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    saved = client.save_user(planned_payload).as_dict()
    saved_id = _extract_response_id(saved) or planned_payload.get("_id")
    readback = client.user_by_id(str(saved_id)).as_dict() if saved_id else None
    response_payload.update({"saved": saved, "readback": readback})
    return controlled_write_result(audit=audit, response=response_payload)


@mcp.tool()
def alterios_upsert_user_group(
    payload: dict[str, Any],
    user_group_id: str | None = None,
    lookup_name: str | None = None,
    expected_name: str | None = None,
    allow_create: bool = False,
    dry_run: bool = True,
    allow_destructive: bool = False,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or create/update an Alterios user group. Classified as security write."""
    client = _client(profile, project_id)
    existing = _find_user_group(client, user_group_id=user_group_id, name=lookup_name)
    if not existing and not allow_create:
        raise ValueError("User group was not found; pass allow_create=True only after security review.")
    if existing and expected_name and existing.get("name") != expected_name:
        raise ValueError(f"User group name mismatch: expected {expected_name!r}, got {existing.get('name')!r}.")
    resource_id = user_group_id or (str(existing.get("_id")) if existing and existing.get("_id") else None)
    planned_payload = _security_payload(existing, payload, resource_id)
    operation = _security_resource_operation(
        collection="user-groups",
        action="upsert",
        kind="user_group",
        resource_id=resource_id,
        request=planned_payload,
        summary="Create or update an Alterios user group and verify through user-group readback.",
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
    response_payload: dict[str, Any] = {
        "preflight": _security_resource_summary(existing),
        "diff": _resource_diff(existing, planned_payload, tuple(sorted(planned_payload.keys()))),
        "planned_payload": strip_alterios_metadata(planned_payload),
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    saved = client.save_user_group(planned_payload).as_dict()
    saved_id = _extract_response_id(saved) or planned_payload.get("_id")
    readback = client.user_group_by_id(str(saved_id)).as_dict() if saved_id else None
    response_payload.update({"saved": saved, "readback": readback})
    return controlled_write_result(audit=audit, response=response_payload)


@mcp.tool()
def alterios_upsert_role(
    payload: dict[str, Any],
    role_id: str | None = None,
    lookup_name: str | None = None,
    expected_name: str | None = None,
    allow_create: bool = False,
    dry_run: bool = True,
    allow_destructive: bool = False,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or create/update an Alterios role. Classified as security write."""
    client = _client(profile, project_id)
    existing = _find_role(client, role_id=role_id, name=lookup_name)
    if not existing and not allow_create:
        raise ValueError("Role was not found; pass allow_create=True only after security review.")
    if existing and expected_name and existing.get("name") != expected_name:
        raise ValueError(f"Role name mismatch: expected {expected_name!r}, got {existing.get('name')!r}.")
    resource_id = role_id or (str(existing.get("_id")) if existing and existing.get("_id") else None)
    planned_payload = _security_payload(existing, payload, resource_id)
    operation = _security_resource_operation(
        collection="roles",
        action="upsert",
        kind="role",
        resource_id=resource_id,
        request=planned_payload,
        summary="Create or update an Alterios role and verify through role readback.",
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
    response_payload: dict[str, Any] = {
        "preflight": _security_resource_summary(existing),
        "diff": _resource_diff(existing, planned_payload, tuple(sorted(planned_payload.keys()))),
        "planned_payload": strip_alterios_metadata(planned_payload),
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    saved = client.save_role(planned_payload).as_dict()
    saved_id = _extract_response_id(saved) or planned_payload.get("_id")
    readback = client.role_by_id(str(saved_id)).as_dict() if saved_id else None
    response_payload.update({"saved": saved, "readback": readback})
    return controlled_write_result(audit=audit, response=response_payload)


@mcp.tool()
def alterios_delete_user(
    user_id: str,
    expected_email: str | None = None,
    dry_run: bool = True,
    allow_destructive: bool = False,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or delete an Alterios user. Classified as security/destructive write."""
    client = _client(profile, project_id)
    existing = _find_user(client, user_id=user_id)
    if not existing:
        raise ValueError(f"User {user_id!r} was not found.")
    if expected_email and str(existing.get("email") or "").lower() != expected_email.strip().lower():
        raise ValueError(f"User email mismatch: expected {expected_email!r}, got {existing.get('email')!r}.")
    operation = _security_resource_operation(
        collection="users",
        action="delete",
        kind="user_delete",
        resource_id=user_id,
        request={"_id": user_id, "expectedEmail": expected_email},
        summary="Delete an Alterios user and verify absence through user readback.",
        path_override="/api/users",
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
    response_payload: dict[str, Any] = {"preflight": _security_resource_summary(existing)}
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    deleted = client.delete_user(user_id).as_dict()
    response_payload.update({"deleted": deleted, "delete_readback": _delete_readback(client, "user", user_id)})
    return controlled_write_result(audit=audit, response=response_payload)


@mcp.tool()
def alterios_delete_user_group(
    user_group_id: str,
    expected_name: str | None = None,
    dry_run: bool = True,
    allow_destructive: bool = False,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or delete an Alterios user group. Classified as security/destructive write."""
    client = _client(profile, project_id)
    existing = _find_user_group(client, user_group_id=user_group_id)
    if not existing:
        raise ValueError(f"User group {user_group_id!r} was not found.")
    if expected_name and existing.get("name") != expected_name:
        raise ValueError(f"User group name mismatch: expected {expected_name!r}, got {existing.get('name')!r}.")
    operation = _security_resource_operation(
        collection="user-groups",
        action="delete",
        kind="user_group_delete",
        resource_id=user_group_id,
        request={"_id": user_group_id, "expectedName": expected_name},
        summary="Delete an Alterios user group and verify absence through user-group readback.",
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
    response_payload: dict[str, Any] = {"preflight": _security_resource_summary(existing)}
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    deleted = client.delete_user_group(user_group_id).as_dict()
    response_payload.update(
        {"deleted": deleted, "delete_readback": _delete_readback(client, "user_group", user_group_id)}
    )
    return controlled_write_result(audit=audit, response=response_payload)


@mcp.tool()
def alterios_delete_role(
    role_id: str,
    expected_name: str | None = None,
    dry_run: bool = True,
    allow_destructive: bool = False,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or delete an Alterios role. Classified as security/destructive write."""
    client = _client(profile, project_id)
    existing = _find_role(client, role_id=role_id)
    if not existing:
        raise ValueError(f"Role {role_id!r} was not found.")
    if expected_name and existing.get("name") != expected_name:
        raise ValueError(f"Role name mismatch: expected {expected_name!r}, got {existing.get('name')!r}.")
    operation = _security_resource_operation(
        collection="roles",
        action="delete",
        kind="role_delete",
        resource_id=role_id,
        request={"_id": role_id, "expectedName": expected_name},
        summary="Delete an Alterios role and verify absence through role readback.",
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
    response_payload: dict[str, Any] = {"preflight": _security_resource_summary(existing)}
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    deleted = client.delete_role(role_id).as_dict()
    response_payload.update({"deleted": deleted, "delete_readback": _delete_readback(client, "role", role_id)})
    return controlled_write_result(audit=audit, response=response_payload)


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
def alterios_upsert_content_type(
    name: str,
    content_type_id: str | None = None,
    field_name_prefix: str | None = None,
    content_name_template: str | None = None,
    settings: dict[str, Any] | None = None,
    description: str | None = None,
    share: bool | None = None,
    share_creating: bool | None = None,
    share_editing: bool | None = None,
    share_deleting: bool | None = None,
    allow_unmanaged_update: bool = False,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or create/update an Alterios content type. Execution requires explicit write gates."""
    if not name.strip():
        raise ValueError("name must not be empty.")
    client = _client(profile, project_id)
    existing = _find_content_type(client, content_type_id=content_type_id, name=name)
    if existing:
        _assert_managed_or_allowed(existing, kind="Content type", allow_unmanaged_update=allow_unmanaged_update)
    elif not field_name_prefix:
        raise ValueError("field_name_prefix is required when creating a new content type.")

    payload = {
        **(existing or {}),
        "name": name,
        "description": description
        if description is not None
        else (existing or {}).get("description")
        or f"{MANAGED_MARKER}: alterios-mcp content type.",
        "settings": settings if settings is not None else (existing or {}).get("settings") or {"maxRefDepth": 0},
        "share": share if share is not None else (existing or {}).get("share") or False,
        "shareCreating": share_creating if share_creating is not None else (existing or {}).get("shareCreating") or False,
        "shareEditing": share_editing if share_editing is not None else (existing or {}).get("shareEditing") or False,
        "shareDeleting": share_deleting if share_deleting is not None else (existing or {}).get("shareDeleting") or False,
    }
    if field_name_prefix is not None:
        payload["fieldNamePrefix"] = field_name_prefix
    elif existing and existing.get("fieldNamePrefix") is not None:
        payload["fieldNamePrefix"] = existing.get("fieldNamePrefix")
    if content_name_template is not None:
        payload["contentNameTemplate"] = content_name_template
    elif existing and existing.get("contentNameTemplate") is not None:
        payload["contentNameTemplate"] = existing.get("contentNameTemplate")

    operation = _resource_operation(
        name="POST /api/content-types/save",
        kind="content_type",
        method="POST",
        path="/api/content-types/save",
        summary="Create or update an Alterios content type with preflight and readback.",
        request={"_id": payload.get("_id"), "name": name, "fieldNamePrefix": payload.get("fieldNamePrefix")},
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
        "diff": _resource_diff(
            existing,
            payload,
            (
                "name",
                "description",
                "fieldNamePrefix",
                "contentNameTemplate",
                "settings",
                "share",
                "shareCreating",
                "shareEditing",
                "shareDeleting",
            ),
        ),
        "planned_payload": strip_alterios_metadata(payload),
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    saved = client.save_content_type(payload).as_dict()
    saved_id = _extract_response_id(saved) or payload.get("_id")
    readback = client.content_type_by_id(saved_id).as_dict() if saved_id else {"body": _find_content_type(client, name=name)}
    response_payload.update({"saved": saved, "readback": readback})
    return controlled_write_result(audit=audit, response=response_payload)


@mcp.tool()
def alterios_plan_content_type_publish(
    content_type_id: str,
    target_project_ids: list[str],
    ui_har_evidence: dict[str, Any] | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan native content-type publish/transfer and review route evidence before execution."""
    normalized_targets = [str(target_id).strip() for target_id in target_project_ids if str(target_id).strip()]
    if not content_type_id.strip():
        raise ValueError("content_type_id must not be empty.")
    if not normalized_targets:
        raise ValueError("target_project_ids must contain at least one project id.")
    if len(set(normalized_targets)) != len(normalized_targets):
        raise ValueError("target_project_ids must not contain duplicates.")
    client = _client(profile, project_id)
    content_type = _find_content_type(client, content_type_id=content_type_id)
    if not content_type:
        raise ValueError(f"Content type {content_type_id!r} was not found.")

    route = (ui_har_evidence or {}).get("route") if isinstance(ui_har_evidence, dict) else None
    method = str((ui_har_evidence or {}).get("method") or "").upper() if isinstance(ui_har_evidence, dict) else ""
    payload_shape = (ui_har_evidence or {}).get("payload_shape") if isinstance(ui_har_evidence, dict) else None
    native_ready = bool(route and method in {"POST", "PUT", "PATCH"} and payload_shape)
    return {
        "source": _resource_summary(content_type),
        "target_project_ids": normalized_targets,
        "native_publish": {
            "ready": native_ready,
            "status": "route_evidence_available" if native_ready else "blocked_until_ui_har_evidence",
            "required_evidence": [
                "UI or HAR route path",
                "HTTP method",
                "redacted payload shape",
                "source contentTypeId and target project IDs",
                "readback route proving availability in every target project",
            ],
            "provided_evidence": {
                "method": method or None,
                "route": route,
                "payload_shape": payload_shape,
            },
        },
        "safe_fallback_plan": [
            "Read source content type and fields from the source project.",
            "Create or update the target content type in each explicit target project.",
            "Recreate fields, views, forms, groups, scripts, reports, icons, and dependencies by typed tools.",
            "Run target readback and UI checks per project.",
        ],
        "next_step": "Use alterios_clone_shared_content_type for dry-run-first native clone only in an explicit target sandbox project."
        if native_ready
        else "Capture UI/HAR evidence first; do not execute native publish by inference.",
    }


@mcp.tool()
def alterios_clone_shared_content_type(
    source_content_type_id: str,
    expected_source_name: str | None = None,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or clone a shared content type into the explicit target project context."""
    if not source_content_type_id.strip():
        raise ValueError("source_content_type_id must not be empty.")
    if not project_id or not project_id.strip():
        raise ValueError("project_id must be the explicit target project for content type clone.")
    client = _client(profile, project_id)
    shared_source = _find_shared_content_type(client, source_content_type_id)
    if not shared_source:
        raise ValueError(
            f"Shared content type {source_content_type_id!r} is not visible from target project {project_id!r}."
        )
    if expected_source_name and shared_source.get("name") != expected_source_name:
        raise ValueError(
            f"Shared content type name mismatch: expected {expected_source_name!r}, got {shared_source.get('name')!r}."
        )

    request = {"id": source_content_type_id, "expectedSourceName": expected_source_name}
    operation = _resource_operation(
        name="POST /api/content-types/clone",
        kind="content_type_clone",
        method="POST",
        path="/api/content-types/clone",
        summary="Clone a shared Alterios content type into the explicit target project.",
        request=request,
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
    )
    response_payload: dict[str, Any] = {
        "source": _resource_summary(shared_source),
        "source_project_id": shared_source.get("projectId"),
        "target_project_id": project_id,
        "route_evidence": {
            "shared_list": "GET /api/content-types?share=true",
            "clone": "POST /api/content-types/clone",
            "payload": {"id": source_content_type_id},
        },
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)

    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    cloned = client.clone_content_type(source_content_type_id).as_dict()
    cloned_id = _extract_response_id(cloned)
    readback = client.content_type_by_id(cloned_id).as_dict() if cloned_id else None
    response_payload.update({"cloned": cloned, "readback": readback})
    return controlled_write_result(audit=audit, response=response_payload)


@mcp.tool()
def alterios_upsert_field(
    content_type_id: str,
    name: str,
    field_type: str,
    field_id: str | None = None,
    mname: str | None = None,
    description: str | None = None,
    help: str | None = None,
    tooltip: str | None = None,
    order: int | None = None,
    required: bool | None = None,
    default_value: Any | None = None,
    form_display: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    allow_unmanaged_update: bool = False,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or create/update an Alterios content type field. Execution requires explicit write gates."""
    if not content_type_id.strip():
        raise ValueError("content_type_id must not be empty.")
    if not name.strip():
        raise ValueError("name must not be empty.")
    if not field_type.strip():
        raise ValueError("field_type must not be empty.")
    client = _client(profile, project_id)
    parent = _find_content_type(client, content_type_id=content_type_id)
    if not parent:
        raise ValueError(f"Content type {content_type_id!r} was not found.")
    existing = _find_field(client, content_type_id=content_type_id, field_id=field_id, mname=mname, name=name)
    if existing:
        existing_content_type_id = existing.get("contentTypeId") or existing.get("content_type_id")
        if existing_content_type_id and existing_content_type_id != content_type_id:
            raise ValueError(
                f"Field {existing.get('_id')!r} belongs to content type {existing_content_type_id!r}, not {content_type_id!r}."
            )
        _assert_managed_or_allowed(existing, kind="Field", allow_unmanaged_update=allow_unmanaged_update)
    elif not mname:
        raise ValueError("mname is required when creating a new field.")

    payload = {
        **(existing or {}),
        "name": name,
        "type": field_type,
        "contentTypeId": content_type_id,
        "description": description
        if description is not None
        else (existing or {}).get("description")
        or f"{MANAGED_MARKER}: alterios-mcp field.",
        "settings": settings if settings is not None else (existing or {}).get("settings") or {},
        "formDisplay": form_display if form_display is not None else (existing or {}).get("formDisplay") or {},
    }
    if mname is not None:
        payload["mname"] = mname
    elif existing and existing.get("mname") is not None:
        payload["mname"] = existing.get("mname")
    if help is not None:
        payload["help"] = help
    elif existing and existing.get("help") is not None:
        payload["help"] = existing.get("help")
    if tooltip is not None:
        payload["tooltip"] = tooltip
    elif existing and existing.get("tooltip") is not None:
        payload["tooltip"] = existing.get("tooltip")
    if order is not None:
        payload["order"] = order
    elif existing and existing.get("order") is not None:
        payload["order"] = existing.get("order")
    if required is not None:
        payload["required"] = required
    elif existing and existing.get("required") is not None:
        payload["required"] = existing.get("required")
    if default_value is not None:
        payload["defaultValue"] = default_value
    elif existing and existing.get("defaultValue") is not None:
        payload["defaultValue"] = existing.get("defaultValue")

    operation = _resource_operation(
        name="POST /api/fields/save",
        kind="field",
        method="POST",
        path="/api/fields/save",
        summary="Create or update an Alterios content type field with preflight and readback.",
        request={"_id": payload.get("_id"), "name": name, "mname": payload.get("mname"), "contentTypeId": content_type_id},
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
    )
    response_payload: dict[str, Any] = {
        "content_type": _resource_summary(parent),
        "preflight": _resource_summary(existing),
        "diff": _resource_diff(
            existing,
            payload,
            ("name", "mname", "type", "description", "help", "tooltip", "order", "required", "defaultValue", "formDisplay", "settings"),
        ),
        "planned_payload": strip_alterios_metadata(payload),
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    saved = client.save_field(payload).as_dict()
    saved_id = _extract_response_id(saved) or payload.get("_id")
    if saved_id:
        readback = client.field_by_id(saved_id).as_dict()
    else:
        readback = {"body": _find_field(client, content_type_id=content_type_id, mname=payload.get("mname"), name=name)}
    response_payload.update({"saved": saved, "readback": readback})
    return controlled_write_result(audit=audit, response=response_payload)


@mcp.tool()
def alterios_create_content(
    content_type_id: str,
    field_values: dict[str, Any],
    expected_content_type_name: str | None = None,
    groups_ids: list[str] | None = None,
    name: str | None = None,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or create an Alterios content row. Execution requires explicit write gates."""
    if not content_type_id.strip():
        raise ValueError("content_type_id must not be empty.")
    if not field_values:
        raise ValueError("field_values must contain at least one field.")
    client = _client(profile, project_id)
    content_type = _find_content_type(client, content_type_id=content_type_id)
    if not content_type:
        raise ValueError(f"Content type {content_type_id!r} was not found.")
    if expected_content_type_name and content_type.get("name") != expected_content_type_name:
        raise ValueError(
            f"Content type name mismatch: expected {expected_content_type_name!r}, got {content_type.get('name')!r}."
        )
    normalized_fields = {str(key): normalize_content_field_value(value) for key, value in field_values.items()}
    planned_payload: dict[str, Any] = {"contentTypeId": content_type_id, "fields": normalized_fields}
    if groups_ids is not None:
        planned_payload["groupsIds"] = groups_ids
    if name is not None:
        planned_payload["name"] = name
    operation = _resource_operation(
        name="POST /api/contents/save",
        kind="content_create",
        method="POST",
        path="/api/contents/save",
        summary="Create an Alterios content row with preflight and readback when the API returns an id.",
        request=planned_payload,
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
    )
    response_payload: dict[str, Any] = {
        "content_type": _resource_summary(content_type),
        "planned_payload": planned_payload,
        "field_keys": sorted(normalized_fields),
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    created = client.create_content(content_type_id, field_values, groups_ids=groups_ids, name=name).as_dict()
    created_id = _extract_response_id(created)
    readback = client.content_by_id(created_id).as_dict() if created_id else None
    response_payload.update({"created": created, "content_id": created_id, "readback": readback})
    return controlled_write_result(audit=audit, response=response_payload)


@mcp.tool()
def alterios_upsert_group(
    name: str,
    group_id: str | None = None,
    form_id: str | None = None,
    parent_group_id: str | None = None,
    description: str | None = None,
    publish: bool | None = None,
    root: bool = False,
    children: list[dict[str, Any]] | None = None,
    order: int | None = None,
    icon_id: str | None = None,
    allow_unmanaged_update: bool = False,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or create/update an Alterios menu group. Execution requires explicit write gates."""
    if not name.strip():
        raise ValueError("name must not be empty.")
    client = _client(profile, project_id)
    existing = _find_group(client, group_id=group_id, name=name, include_root=root)
    if group_id and not existing:
        raise ValueError(f"Group {group_id!r} was not found.")
    if existing:
        _assert_managed_or_allowed(existing, kind="Group", allow_unmanaged_update=allow_unmanaged_update)
    parent = _find_group(client, group_id=parent_group_id, include_root=True) if parent_group_id else _find_root_group(client)
    if parent_group_id and not parent:
        raise ValueError(f"Parent group {parent_group_id!r} was not found.")
    if not existing and not root and not parent:
        raise ValueError("parent_group_id was not passed and root group was not found.")
    payload_root = root
    if existing and existing.get("root") and not root:
        payload_root = True
    payload_publish = publish if publish is not None else (((existing or {}).get("publish")) if existing else True)
    payload = {
        **(existing or {}),
        "name": name,
        "description": description
        if description is not None
        else (existing or {}).get("description")
        or f"{MANAGED_MARKER}: alterios-mcp group.",
        "root": payload_root,
        "children": children if children is not None else (existing or {}).get("children") or [],
        "publish": payload_publish,
    }
    if parent_group_id is not None:
        payload["parentGroupId"] = parent_group_id
    elif existing and existing.get("parentGroupId") is not None:
        payload["parentGroupId"] = existing.get("parentGroupId")
    elif parent:
        payload["parentGroupId"] = parent.get("_id")
    if form_id is not None:
        payload["formId"] = form_id
    elif existing and existing.get("formId") is not None:
        payload["formId"] = existing.get("formId")
    if order is not None:
        payload["order"] = order
    elif existing and existing.get("order") is not None:
        payload["order"] = existing.get("order")
    if icon_id is not None:
        payload["iconId"] = icon_id
    elif existing and existing.get("iconId") is not None:
        payload["iconId"] = existing.get("iconId")

    operation = _resource_operation(
        name=("PATCH /api/groups/{id}" if existing else "POST /api/groups"),
        kind="group",
        method="PATCH" if existing else "POST",
        path=f"/api/groups/{existing.get('_id')}" if existing else "/api/groups",
        summary="Create or update an Alterios menu group with preflight and readback.",
        request={"_id": payload.get("_id"), "name": name, "formId": payload.get("formId"), "parentGroupId": payload.get("parentGroupId")},
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
        "parent": _resource_summary(parent),
        "diff": _resource_diff(existing, payload, ("name", "description", "root", "children", "publish", "parentGroupId", "formId", "order", "iconId")),
        "planned_payload": strip_alterios_metadata(payload),
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    saved = client.save_group(payload).as_dict()
    saved_id = _extract_response_id(saved) or payload.get("_id")
    readback = {"body": _find_group(client, group_id=saved_id, name=name, include_root=root)}
    response_payload.update({"saved": saved, "readback": readback})
    return controlled_write_result(audit=audit, response=response_payload)


@mcp.tool()
def alterios_upsert_help(
    name: str,
    value: str,
    help_id: str | None = None,
    description: str | None = None,
    allow_unmanaged_update: bool = False,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or create/update an Alterios help entry. Execution requires explicit write gates."""
    if not name.strip():
        raise ValueError("name must not be empty.")
    if not value.strip():
        raise ValueError("value must not be empty.")
    client = _client(profile, project_id)
    existing = _find_help(client, help_id=help_id, name=name)
    if existing:
        _assert_help_managed_or_allowed(existing, allow_unmanaged_update=allow_unmanaged_update)
    payload = {
        **(existing or {}),
        "name": name,
        "value": value,
        "description": description
        if description is not None
        else (existing or {}).get("description")
        or f"{MANAGED_MARKER}: alterios-mcp help.",
    }
    operation = _resource_operation(
        name=("PATCH /api/helps/{id}" if existing else "POST /api/helps"),
        kind="help",
        method="PATCH" if existing else "POST",
        path=f"/api/helps/{existing.get('_id')}" if existing else "/api/helps",
        summary="Create or update an Alterios help entry with preflight and readback.",
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
        "diff": _resource_diff(existing, payload, ("name", "value", "description")),
        "planned_payload": strip_alterios_metadata(payload),
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    saved = client.save_help(payload).as_dict()
    saved_id = _extract_response_id(saved) or payload.get("_id")
    readback = {"body": _find_help(client, help_id=saved_id, name=name)}
    response_payload.update({"saved": saved, "readback": readback})
    return controlled_write_result(audit=audit, response=response_payload)


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
def alterios_bulk_update_selected_content_fields(
    selected_content_ids: list[str],
    field_values: dict[str, Any],
    expected_count: int | None = None,
    expected_content_type_id: str | None = None,
    groups_ids: list[str] | None = None,
    max_count: int = 100,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or update fields on multiple selected Alterios content rows with per-row preflight/readback."""
    normalized_ids = [str(content_id).strip() for content_id in selected_content_ids if str(content_id).strip()]
    if not normalized_ids:
        raise ValueError("selected_content_ids must contain at least one content id.")
    if len(set(normalized_ids)) != len(normalized_ids):
        raise ValueError("selected_content_ids must not contain duplicates.")
    if expected_count is not None and expected_count != len(normalized_ids):
        raise ValueError(f"expected_count mismatch: expected {expected_count}, got {len(normalized_ids)}.")
    if max_count < 1:
        raise ValueError("max_count must be positive.")
    if len(normalized_ids) > max_count:
        raise ValueError(f"Refusing to update {len(normalized_ids)} rows; max_count is {max_count}.")
    if not field_values:
        raise ValueError("field_values must contain at least one field.")

    operation = _resource_operation(
        name="PATCH /api/contents/save x selected",
        kind="bulk_selection",
        method="PATCH",
        path="/api/contents/save",
        summary="Bulk-update fields on selected Alterios content rows with per-row preflight and readback.",
        request={
            "selectedContentIds": normalized_ids,
            "expectedContentTypeId": expected_content_type_id,
            "fields": field_values,
            "groupsIds": groups_ids,
        },
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
    rows: list[dict[str, Any]] = []
    for content_id in normalized_ids:
        before = client.content_by_id(content_id).body
        if not isinstance(before, dict):
            raise ValueError(f"Content {content_id!r} preflight returned unexpected payload.")
        _assert_expected_content(before, expected_content_type_id=expected_content_type_id)
        planned_payload = content_update_payload(
            before,
            field_values,
            content_type_id=expected_content_type_id,
            groups_ids=groups_ids,
        )
        rows.append(
            {
                "content": _content_summary(before),
                "field_diff": _field_diff(before.get("fields") or {}, field_values),
                "planned_payload": planned_payload,
            }
        )

    response_payload: dict[str, Any] = {
        "selected_count": len(normalized_ids),
        "field_keys": sorted(str(key) for key in field_values.keys()),
        "rows": rows,
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)

    updates = []
    for content_id in normalized_ids:
        updated = client.update_content_fields(
            content_id,
            field_values,
            content_type_id=expected_content_type_id,
            groups_ids=groups_ids,
        ).as_dict()
        readback = client.content_by_id(content_id).as_dict()
        updates.append({"content_id": content_id, "updated": updated, "readback": readback})
    response_payload["updates"] = updates
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
def alterios_create_material_module(
    module_name: str,
    field_name_prefix: str,
    fields: list[dict[str, Any]],
    content_type_id: str | None = None,
    view_id: str | None = None,
    add_form_id: str | None = None,
    edit_form_id: str | None = None,
    list_form_id: str | None = None,
    group_id: str | None = None,
    names: dict[str, str] | None = None,
    content_name_template: str | None = None,
    parent_group_id: str | None = None,
    icon_id: str | None = "inventory_2",
    add_icon_id: str | None = "add",
    edit_icon_id: str | None = "edit",
    save_icon_id: str | None = "save",
    allow_unmanaged_update: bool = False,
    dry_run: bool = True,
    plan_id: str | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or apply a full Alterios material module: content type, fields, view, forms, and group."""
    normalized_module_name = module_name.strip()
    normalized_prefix = field_name_prefix.strip()
    if not normalized_module_name:
        raise ValueError("module_name must not be empty.")
    if not normalized_prefix:
        raise ValueError("field_name_prefix must not be empty.")
    normalized_fields = _normalize_material_module_fields(fields, field_name_prefix=normalized_prefix)
    resolved_names = _material_module_names(normalized_module_name, names)
    operation = _material_module_operation(
        module_name=normalized_module_name,
        field_name_prefix=normalized_prefix,
        fields=normalized_fields,
        content_type_id=content_type_id,
        view_id=view_id,
        add_form_id=add_form_id,
        edit_form_id=edit_form_id,
        list_form_id=list_form_id,
        group_id=group_id,
        parent_group_id=parent_group_id,
        names=resolved_names,
        content_name_template=content_name_template,
        icon_id=icon_id,
        add_icon_id=add_icon_id,
        edit_icon_id=edit_icon_id,
        save_icon_id=save_icon_id,
        allow_unmanaged_update=allow_unmanaged_update,
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
    )
    client = _client(profile, project_id)
    preflight = _material_module_preflight(
        client,
        names=resolved_names,
        fields=normalized_fields,
        content_type_id=content_type_id,
        view_id=view_id,
        add_form_id=add_form_id,
        edit_form_id=edit_form_id,
        list_form_id=list_form_id,
        group_id=group_id,
        parent_group_id=parent_group_id,
        allow_unmanaged_update=allow_unmanaged_update,
    )
    response_payload: dict[str, Any] = {
        "module_name": normalized_module_name,
        "names": resolved_names,
        "preflight": preflight,
        "planned": _material_module_plan_preview(
            module_name=normalized_module_name,
            names=resolved_names,
            fields=normalized_fields,
            field_name_prefix=normalized_prefix,
            content_type_id=content_type_id or (preflight.get("content_type") or {}).get("_id"),
            view_id=view_id or (preflight.get("view") or {}).get("_id"),
            add_form_id=add_form_id or ((preflight.get("forms") or {}).get("add") or {}).get("_id"),
            edit_form_id=edit_form_id or ((preflight.get("forms") or {}).get("edit") or {}).get("_id"),
            list_form_id=list_form_id or ((preflight.get("forms") or {}).get("list") or {}).get("_id"),
            group_id=group_id or (preflight.get("group") or {}).get("_id"),
            parent_group_id=parent_group_id or (preflight.get("parent_group") or {}).get("_id"),
            icon_id=icon_id,
            add_icon_id=add_icon_id,
            edit_icon_id=edit_icon_id,
            save_icon_id=save_icon_id,
        ),
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)

    if not plan_id:
        raise ValueError("plan_id is required when dry_run=false for alterios_create_material_module.")
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    assert_plan_matches_audit(plan_id=plan_id, audit=audit.as_dict())

    steps: list[dict[str, Any]] = []

    content_type_result = alterios_upsert_content_type(
        resolved_names["content_type"],
        content_type_id=content_type_id,
        field_name_prefix=normalized_prefix,
        content_name_template=content_name_template,
        allow_unmanaged_update=allow_unmanaged_update,
        dry_run=False,
        profile=profile,
        project_id=project_id,
    )
    content_type_body = _response_body((content_type_result.get("response") or {}).get("readback"))
    content_type_id = _extract_response_id(content_type_body) or _extract_response_id(content_type_result) or content_type_id
    if not content_type_id:
        raise ValueError("Content type id was not resolved after save.")
    steps.append({"step": "content_type", "id": content_type_id, "result": content_type_result})

    saved_fields: list[dict[str, Any]] = []
    for field in normalized_fields:
        field_result = alterios_upsert_field(
            content_type_id,
            field["name"],
            field["field_type"],
            field_id=field.get("field_id"),
            mname=field["mname"],
            description=field.get("description"),
            help=field.get("help"),
            tooltip=field.get("tooltip"),
            order=field.get("order"),
            required=field.get("required"),
            default_value=field.get("default_value"),
            form_display=field.get("form_display"),
            settings=field.get("settings"),
            allow_unmanaged_update=allow_unmanaged_update,
            dry_run=False,
            profile=profile,
            project_id=project_id,
        )
        field_body = _response_body((field_result.get("response") or {}).get("readback"))
        field_id = _extract_response_id(field_body) or _extract_response_id(field_result) or field.get("field_id")
        if not field_id:
            raise ValueError(f"Field id was not resolved after save for {field['mname']!r}.")
        saved_field = {**field, "_id": field_id}
        if isinstance(field_body, dict):
            saved_field.update({key: value for key, value in field_body.items() if key in {"_id", "name", "mname", "type"}})
        saved_fields.append(saved_field)
        steps.append({"step": "field", "id": field_id, "mname": field["mname"], "result": field_result})

    view_result = alterios_upsert_view(
        resolved_names["view"],
        view_id=view_id,
        allow_unmanaged_update=allow_unmanaged_update,
        dry_run=False,
        profile=profile,
        project_id=project_id,
    )
    view_body = _response_body((view_result.get("response") or {}).get("readback"))
    view_id = _extract_response_id(view_body) or _extract_response_id(view_result) or view_id
    if not view_id:
        raise ValueError("View id was not resolved after save.")
    steps.append({"step": "view", "id": view_id, "result": view_result})

    view_entity_result = alterios_upsert_view_entity(
        view_id,
        resolved_names["content_type"],
        entity_type="content",
        config={"main": True, "position": {"x": -260, "y": -180}, "contentTypesIds": [content_type_id]},
        joins=[],
        allow_unmanaged_update=allow_unmanaged_update,
        dry_run=False,
        profile=profile,
        project_id=project_id,
    )
    view_entity_body = _response_body((view_entity_result.get("response") or {}).get("readback"))
    view_entity_id = _extract_response_id(view_entity_body) or _extract_response_id(view_entity_result)
    if not view_entity_id:
        raise ValueError("View entity id was not resolved after save.")
    steps.append({"step": "view_entity", "id": view_entity_id, "result": view_entity_result})

    id_view_field_result = alterios_upsert_view_field(
        view_id,
        view_entity_id,
        attribute="_id",
        alias="ID",
        mname="_id",
        order=0,
        allow_unmanaged_update=allow_unmanaged_update,
        dry_run=False,
        profile=profile,
        project_id=project_id,
    )
    steps.append({"step": "view_field", "attribute": "_id", "result": id_view_field_result})
    saved_view_fields: list[dict[str, Any]] = []
    for index, field in enumerate(saved_fields, start=1):
        view_order = int(field.get("order", index - 1)) + 1
        view_field_result = alterios_upsert_view_field(
            view_id,
            view_entity_id,
            content_type_field_id=str(field["_id"]),
            alias=field["name"],
            mname=field["view_mname"],
            order=view_order,
            allow_unmanaged_update=allow_unmanaged_update,
            dry_run=False,
            profile=profile,
            project_id=project_id,
        )
        view_field_body = _response_body((view_field_result.get("response") or {}).get("readback"))
        saved_view_fields.append(
            {
                "field_id": field["_id"],
                "field_mname": field["mname"],
                "view_field_id": _extract_response_id(view_field_body),
                "view_mname": field["view_mname"],
            }
        )
        steps.append({"step": "view_field", "field_id": field["_id"], "result": view_field_result})

    add_tabs = [
        {
            "name": None,
            "rows": [_material_content_form_row(normalized_module_name, content_type_id, saved_fields)],
        }
    ]
    add_form_result = alterios_upsert_form(
        resolved_names["add_form"],
        form_id=add_form_id,
        page_title=resolved_names["add_form"],
        tabs=add_tabs,
        form_action_containers=[_material_save_action_container(save_icon_id)],
        allow_unmanaged_update=allow_unmanaged_update,
        dry_run=False,
        profile=profile,
        project_id=project_id,
    )
    add_form_body = _response_body((add_form_result.get("response") or {}).get("readback"))
    add_form_id = _extract_response_id(add_form_body) or _extract_response_id(add_form_result) or add_form_id
    if not add_form_id:
        raise ValueError("Add form id was not resolved after save.")
    steps.append({"step": "add_form", "id": add_form_id, "result": add_form_result})

    edit_tabs = [
        {
            "name": None,
            "rows": [
                _material_view_data_row(normalized_module_name, view_id, saved_fields, editable=True),
                _material_comments_row(),
            ],
        }
    ]
    edit_form_result = alterios_upsert_form(
        resolved_names["edit_form"],
        form_id=edit_form_id,
        page_title=resolved_names["edit_form"],
        tabs=edit_tabs,
        form_action_containers=[_material_save_action_container(save_icon_id)],
        allow_unmanaged_update=allow_unmanaged_update,
        dry_run=False,
        profile=profile,
        project_id=project_id,
    )
    edit_form_body = _response_body((edit_form_result.get("response") or {}).get("readback"))
    edit_form_id = _extract_response_id(edit_form_body) or _extract_response_id(edit_form_result) or edit_form_id
    if not edit_form_id:
        raise ValueError("Edit form id was not resolved after save.")
    steps.append({"step": "edit_form", "id": edit_form_id, "result": edit_form_result})

    list_tabs = [
        {
            "name": None,
            "rows": [
                _material_view_data_list_row(
                    module_name=normalized_module_name,
                    view_id=view_id,
                    view_entity_id=view_entity_id,
                    add_form_id=add_form_id,
                    add_form_name=resolved_names["add_form"],
                    edit_form_id=edit_form_id,
                    edit_form_name=resolved_names["edit_form"],
                    fields=saved_fields,
                    add_icon_id=add_icon_id,
                    edit_icon_id=edit_icon_id,
                )
            ],
        }
    ]
    list_form_result = alterios_upsert_form(
        resolved_names["list_form"],
        form_id=list_form_id,
        page_title=resolved_names["list_form"],
        tabs=list_tabs,
        form_action_containers=[],
        allow_unmanaged_update=allow_unmanaged_update,
        dry_run=False,
        profile=profile,
        project_id=project_id,
    )
    list_form_body = _response_body((list_form_result.get("response") or {}).get("readback"))
    list_form_id = _extract_response_id(list_form_body) or _extract_response_id(list_form_result) or list_form_id
    if not list_form_id:
        raise ValueError("List form id was not resolved after save.")
    steps.append({"step": "list_form", "id": list_form_id, "result": list_form_result})

    group_result = alterios_upsert_group(
        resolved_names["group"],
        group_id=group_id,
        form_id=list_form_id,
        parent_group_id=parent_group_id,
        icon_id=icon_id,
        allow_unmanaged_update=allow_unmanaged_update,
        dry_run=False,
        profile=profile,
        project_id=project_id,
    )
    group_body = _response_body((group_result.get("response") or {}).get("readback"))
    group_id = _extract_response_id(group_body) or _extract_response_id(group_result) or group_id
    if not group_id:
        raise ValueError("Group id was not resolved after save.")
    steps.append({"step": "group", "id": group_id, "result": group_result})

    readback = {
        "content_type": _resource_summary(_find_content_type(client, content_type_id=content_type_id)),
        "fields": [
            _resource_summary(_find_field(client, content_type_id=content_type_id, field_id=str(field["_id"])))
            for field in saved_fields
        ],
        "view": _resource_summary(_find_view(client, view_id=view_id)),
        "view_data_smoke": client.request(
            "POST",
            "/api/views/v2/get-data-simplified",
            body={"viewId": view_id, "limit": 1, "offset": 0},
        ).as_dict(),
        "view_entity": _resource_summary(_find_view_entity(client, view_id=view_id, entity_id=view_entity_id)),
        "view_fields": saved_view_fields,
        "forms": {
            "add": _resource_summary(_find_form(client, form_id=add_form_id)),
            "edit": _resource_summary(_find_form(client, form_id=edit_form_id)),
            "list": _resource_summary(_find_form(client, form_id=list_form_id)),
        },
        "group": _resource_summary(_find_group(client, group_id=group_id)),
    }
    response_payload.update(
        {
            "ids": {
                "content_type_id": content_type_id,
                "field_ids": {field["mname"]: field["_id"] for field in saved_fields},
                "view_id": view_id,
                "view_entity_id": view_entity_id,
                "add_form_id": add_form_id,
                "edit_form_id": edit_form_id,
                "list_form_id": list_form_id,
                "group_id": group_id,
            },
            "steps": steps,
            "readback": readback,
        }
    )
    return controlled_write_result(audit=audit, response=response_payload, plan_id=plan_id)


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
def alterios_patch_form_cell_listeners(
    form_id: str,
    tab_index: int,
    row_index: int,
    cell_index: int,
    listeners: list[dict[str, Any]],
    expected_name: str | None = None,
    allow_unmanaged_update: bool = False,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or patch one form cell's emitting.listeners without replacing the whole form manually."""
    if tab_index < 0 or row_index < 0 or cell_index < 0:
        raise ValueError("tab_index, row_index, and cell_index must be non-negative.")
    if not isinstance(listeners, list):
        raise ValueError("listeners must be a list.")
    client = _client(profile, project_id)
    existing = _find_form(client, form_id=form_id)
    if not existing:
        raise ValueError(f"Form {form_id!r} was not found.")
    if expected_name and existing.get("name") != expected_name:
        raise ValueError(f"Form name mismatch: expected {expected_name!r}, got {existing.get('name')!r}.")
    _assert_managed_or_allowed(existing, kind="Form", allow_unmanaged_update=allow_unmanaged_update)

    tabs = json.loads(json.dumps(existing.get("tabs") or [], ensure_ascii=False))
    try:
        cell = tabs[tab_index]["rows"][row_index]["cells"][cell_index]
    except (IndexError, KeyError, TypeError) as exc:
        raise ValueError(
            f"Cell path tabs[{tab_index}].rows[{row_index}].cells[{cell_index}] was not found."
        ) from exc
    if not isinstance(cell, dict):
        raise ValueError("Target form cell is not a JSON object.")
    emitting = cell.get("emitting")
    if not isinstance(emitting, dict):
        emitting = {}
        cell["emitting"] = emitting
    before = emitting.get("listeners")
    emitting["listeners"] = listeners

    operation = _resource_operation(
        name="PATCH /api/forms/{id}",
        kind="form_listeners",
        method="PATCH",
        path=f"/api/forms/{form_id}",
        summary="Patch emitting.listeners for one Alterios form cell and verify through form readback.",
        request={
            "_id": form_id,
            "cellPath": f"tabs[{tab_index}].rows[{row_index}].cells[{cell_index}]",
            "listeners": listeners,
        },
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
    )
    payload = {**existing, "tabs": tabs}
    response_payload: dict[str, Any] = {
        "form": _resource_summary(existing),
        "cell_path": f"tabs[{tab_index}].rows[{row_index}].cells[{cell_index}]",
        "before": before,
        "after": listeners,
        "changed": before != listeners,
        "planned_payload": {"_id": form_id, "tabs": tabs},
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    saved = client.save_form(payload).as_dict()
    readback = client.form_by_id(form_id).as_dict()
    response_payload.update({"saved": saved, "readback": readback})
    return controlled_write_result(audit=audit, response=response_payload)


@mcp.tool()
def alterios_analyze_form_surface(
    form_id: str | None = None,
    form: dict[str, Any] | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Analyze an Alterios form for layout gaps, data sources, roles, styles, and icon-first actions."""
    if not form_id and form is None:
        raise ValueError("Provide form_id for live read or form JSON for offline analysis.")
    if form_id and form is not None:
        raise ValueError("Provide either form_id or form, not both.")
    if form_id:
        client = _client(profile, project_id)
        form_body = _find_form(client, form_id=form_id)
        if not form_body:
            raise ValueError(f"Form {form_id!r} was not found.")
    else:
        form_body = form
    if not isinstance(form_body, dict):
        raise ValueError("Form payload must be a JSON object.")
    return {
        "form": _resource_summary(form_body),
        "surface": analyze_form_surface(form_body),
    }


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
def alterios_create_process_flow(
    diagram_name: str,
    task_form_name: str,
    content_type_id: str | None = None,
    task_form_id: str | None = None,
    diagram_id: str | None = None,
    task_form_tabs: list[dict[str, Any]] | None = None,
    task_form_action_containers: list[dict[str, Any]] | None = None,
    task_form_page_title: str | None = None,
    task_form_description: str | None = None,
    task_title: str | None = None,
    task_body_html: str | None = None,
    bpmn_xml: str | None = None,
    user_task_id: str | None = None,
    user_task_name: str = "Task",
    next_flow_id: str = "Flow_to_end",
    next_flow_name: str = "Complete",
    script_refs: list[dict[str, Any]] | None = None,
    content_id: str | None = None,
    process_params: dict[str, Any] | None = None,
    process_name: str | None = None,
    start_process_smoke: bool = True,
    complete_task: bool = False,
    expected_task_count_min: int | None = 1,
    allow_unmanaged_update: bool = False,
    dry_run: bool = True,
    plan_id: str | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or apply a BPMN process scenario: task form, diagram, script refs, and optional process smoke."""
    normalized_diagram_name = diagram_name.strip()
    normalized_task_form_name = task_form_name.strip()
    normalized_user_task_name = user_task_name.strip()
    normalized_next_flow_id = next_flow_id.strip()
    normalized_next_flow_name = next_flow_name.strip()
    if not normalized_diagram_name:
        raise ValueError("diagram_name must not be empty.")
    if not normalized_task_form_name:
        raise ValueError("task_form_name must not be empty.")
    if not normalized_user_task_name:
        raise ValueError("user_task_name must not be empty.")
    if not normalized_next_flow_id:
        raise ValueError("next_flow_id must not be empty.")
    if expected_task_count_min is not None and expected_task_count_min < 0:
        raise ValueError("expected_task_count_min must be non-negative or null.")
    if complete_task and (not content_id or not start_process_smoke):
        raise ValueError("complete_task requires content_id and start_process_smoke=true.")

    normalized_script_refs = _normalize_process_script_refs(script_refs)
    client = _client(profile, project_id)
    preflight = _process_flow_preflight(
        client,
        task_form_id=task_form_id,
        task_form_name=normalized_task_form_name,
        diagram_id=diagram_id,
        diagram_name=normalized_diagram_name,
        script_refs=normalized_script_refs,
        allow_unmanaged_update=allow_unmanaged_update,
    )

    existing_diagram = preflight["diagram"]
    resolved_content_type_id = (content_type_id or (existing_diagram or {}).get("contentTypeId") or "").strip()
    if not resolved_content_type_id:
        raise ValueError("content_type_id is required when creating a new BPMN diagram.")

    content_preflight = None
    if content_id:
        content_preflight = client.content_by_id(content_id).body
        if not isinstance(content_preflight, dict):
            raise ValueError("Content preflight returned unexpected payload.")
        _assert_expected_content(content_preflight, expected_content_type_id=resolved_content_type_id)

    existing_task_form = preflight["task_form"]
    planned_task_form_id = task_form_id or (existing_task_form or {}).get("_id") or "$task_form_id"
    planned_tabs = task_form_tabs or _process_task_form_tabs(
        task_title or normalized_task_form_name,
        body=task_body_html,
    )
    planned_actions = (
        task_form_action_containers
        if task_form_action_containers is not None
        else [_material_save_action_container("save")]
    )
    planned_form = {
        "_id": planned_task_form_id,
        "name": normalized_task_form_name,
        "pageTitle": task_form_page_title or normalized_task_form_name,
        "tabs": planned_tabs,
        "formActionContainers": planned_actions,
    }
    form_surface = analyze_form_surface(planned_form)

    process_seed = diagram_id or normalized_diagram_name
    generated_task_id = user_task_id or f"Activity_{_safe_bpmn_id(normalized_user_task_name)}"
    planned_bpmn_xml = bpmn_xml or _build_simple_user_task_bpmn(
        process_id=process_seed,
        process_name=normalized_diagram_name,
        task_id=generated_task_id,
        task_name=normalized_user_task_name,
        task_form_id=planned_task_form_id,
        start_form_id=planned_task_form_id,
        next_flow_id=normalized_next_flow_id,
        next_flow_name=normalized_next_flow_name,
    )
    if bpmn_xml and "$task_form_id" not in planned_bpmn_xml and not _bpmn_xml_contains_form_key(
        planned_bpmn_xml,
        planned_task_form_id,
    ):
        raise ValueError("bpmn_xml must contain the resolved task form id or the $task_form_id placeholder.")

    bpmn_refs = _bpmn_xml_script_refs(planned_bpmn_xml)
    known_script_ids = {str(item.get("_id")) for item in preflight["scripts"] if item.get("_id")}
    unmatched_bpmn_script_refs = [ref for ref in bpmn_refs if ref not in known_script_ids]
    process_smoke_planned = {
        "enabled": bool(content_id and start_process_smoke),
        "content_id": content_id,
        "process_name": process_name,
        "complete_task": complete_task,
        "expected_task_count_min": expected_task_count_min,
    }
    operation = _process_flow_operation(
        task_form_name=normalized_task_form_name,
        task_form_id=task_form_id or (existing_task_form or {}).get("_id"),
        diagram_name=normalized_diagram_name,
        diagram_id=diagram_id or (existing_diagram or {}).get("_id"),
        content_type_id=resolved_content_type_id,
        script_refs=normalized_script_refs,
        bpmn_xml=planned_bpmn_xml,
        content_id=content_id,
        start_process_smoke=start_process_smoke,
        complete_task=complete_task,
        expected_user_task_name=normalized_user_task_name,
        expected_task_form_id=planned_task_form_id,
        allow_unmanaged_update=allow_unmanaged_update,
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
    )
    response_payload: dict[str, Any] = {
        "preflight": {
            "task_form": _resource_summary(existing_task_form),
            "diagram": _resource_summary(existing_diagram),
            "scripts": preflight["scripts"],
            "content": _content_summary(content_preflight) if isinstance(content_preflight, dict) else None,
        },
        "planned": {
            "steps": [
                "upsert_task_form",
                "validate_script_refs",
                "upsert_bpmn_diagram",
                "readback_form_key",
                "optional_start_process_smoke",
                "optional_complete_task",
            ],
            "task_form": {
                "form_id": planned_task_form_id,
                "name": normalized_task_form_name,
                "page_title": task_form_page_title or normalized_task_form_name,
                "tabs": planned_tabs,
                "formActionContainers": planned_actions,
                "surface": form_surface,
            },
            "diagram": {
                "diagram_id": diagram_id or (existing_diagram or {}).get("_id"),
                "name": normalized_diagram_name,
                "content_type_id": resolved_content_type_id,
                "bpmn_xml": planned_bpmn_xml,
                "bpmn_script_refs": bpmn_refs,
                "unmatched_bpmn_script_refs": unmatched_bpmn_script_refs,
            },
            "process_smoke": process_smoke_planned,
        },
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)

    if not plan_id:
        raise ValueError("plan_id is required when dry_run=false for alterios_create_process_flow.")
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    assert_plan_matches_audit(plan_id=plan_id, audit=audit.as_dict())

    form_result = alterios_upsert_form(
        normalized_task_form_name,
        form_id=task_form_id,
        page_title=task_form_page_title or normalized_task_form_name,
        tabs=planned_tabs,
        form_action_containers=planned_actions,
        description=task_form_description or f"{MANAGED_MARKER}: alterios-mcp process task form.",
        allow_unmanaged_update=allow_unmanaged_update,
        dry_run=False,
        profile=profile,
        project_id=project_id,
    )
    form_readback = _response_body((form_result.get("response") or {}).get("readback"))
    resolved_task_form_id = _extract_response_id(form_readback) or task_form_id
    if not resolved_task_form_id:
        raise ValueError("Task form id was not resolved after save.")

    actual_bpmn_xml = planned_bpmn_xml.replace("$task_form_id", resolved_task_form_id)
    if not _bpmn_xml_contains_form_key(actual_bpmn_xml, resolved_task_form_id):
        raise ValueError("Saved BPMN XML does not contain the resolved task form key.")

    diagram_result = alterios_upsert_bpmn_diagram(
        normalized_diagram_name,
        diagram_id=diagram_id,
        value=actual_bpmn_xml,
        content_type_id=resolved_content_type_id,
        description=f"{MANAGED_MARKER}: alterios-mcp process flow.",
        allow_unmanaged_update=allow_unmanaged_update,
        dry_run=False,
        profile=profile,
        project_id=project_id,
    )
    diagram_readback = _response_body((diagram_result.get("response") or {}).get("readback"))
    resolved_diagram_id = _extract_response_id(diagram_readback) or diagram_id
    if not resolved_diagram_id:
        raise ValueError("Diagram id was not resolved after save.")
    if not isinstance(diagram_readback, dict) or not _bpmn_xml_contains_form_key(
        str(diagram_readback.get("value") or ""),
        resolved_task_form_id,
    ):
        raise ValueError("Diagram readback does not contain the resolved task form key.")

    process_smoke: dict[str, Any] = {"status": "skipped", "reason": "content_id was not provided or smoke is disabled."}
    if content_id and start_process_smoke:
        start_result = alterios_start_process(
            resolved_diagram_id,
            content_id=content_id,
            params=process_params,
            name=process_name,
            dry_run=False,
            profile=profile,
            project_id=project_id,
        )
        start_response = start_result.get("response") or {}
        process_id = start_response.get("process_id")
        readback_tasks = start_response.get("readback_tasks") or []
        if expected_task_count_min is not None and len(readback_tasks) < expected_task_count_min:
            raise ValueError(
                f"Process smoke expected at least {expected_task_count_min} task(s), got {len(readback_tasks)}."
            )
        task = _process_task_from_tasks(
            [item for item in readback_tasks if isinstance(item, dict)],
            expected_form_id=resolved_task_form_id,
            expected_name=normalized_user_task_name,
        )
        task_form_value = None
        if isinstance(task, dict):
            task_form_value = task.get("formId") or task.get("formKey") or task.get("form")
        task_form_matches = task is not None and (task_form_value in {None, resolved_task_form_id})
        process_smoke = {
            "status": "started",
            "start": start_result,
            "process_id": process_id,
            "task": task,
            "task_count": len(readback_tasks),
            "validation": {
                "task_count_matches": expected_task_count_min is None or len(readback_tasks) >= expected_task_count_min,
                "task_form_value": task_form_value,
                "task_form_matches": task_form_matches,
            },
        }
        if not task_form_matches:
            raise ValueError(
                f"Started task form mismatch: expected {resolved_task_form_id!r}, got {task_form_value!r}."
            )
        if complete_task:
            if not isinstance(task, dict) or not task.get("_id"):
                raise ValueError("Process smoke cannot complete task because active task id was not found.")
            complete_result = alterios_complete_task(
                str(task["_id"]),
                next_flow_id=normalized_next_flow_id,
                expected_process_id=str(process_id) if process_id else None,
                expected_content_id=content_id,
                expected_diagram_id=resolved_diagram_id,
                dry_run=False,
                profile=profile,
                project_id=project_id,
            )
            process_smoke["completed"] = complete_result

    response_payload.update(
        {
            "ids": {
                "task_form_id": resolved_task_form_id,
                "diagram_id": resolved_diagram_id,
                "content_type_id": resolved_content_type_id,
                "content_id": content_id,
            },
            "form_write": form_result,
            "diagram_write": diagram_result,
            "readback": {
                "task_form": _resource_summary(form_readback if isinstance(form_readback, dict) else None),
                "diagram": _resource_summary(diagram_readback if isinstance(diagram_readback, dict) else None),
                "diagram_form_key_found": True,
            },
            "process_smoke": process_smoke,
        }
    )
    return controlled_write_result(audit=audit, response=response_payload, plan_id=plan_id)


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
def alterios_validate_stimulsoft_layout(
    report_id: str | None = None,
    template: str | dict[str, Any] | None = None,
    overlap_tolerance: float = 0.05,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Validate Stimulsoft template geometry for overlaps, page overflow, and dynamic-height risks."""
    if not report_id and template is None:
        raise ValueError("Pass report_id or template.")
    report = None
    source: Any = template
    if report_id:
        report = _client(profile, project_id).report_by_id(report_id).body
        source = report
    return {
        "report": _resource_summary(report) if isinstance(report, dict) else None,
        "layout": analyze_stimulsoft_layout(source, overlap_tolerance=overlap_tolerance),
    }


@mcp.tool()
def alterios_create_report_tab(
    source_view_id: str,
    target_form_id: str,
    report_name: str,
    report_id: str | None = None,
    tab_name: str = "Отчет",
    cell_name: str | None = None,
    report_type: str = "dashboard",
    template: str | dict[str, Any] | None = None,
    marker: str | None = None,
    expected_source_view_name: str | None = None,
    context_content_id: str | None = None,
    expected_context_row_count: int | None = 1,
    open_id: bool = True,
    fullscreen_mode: bool = False,
    replace_existing_tab: bool = True,
    allow_unmanaged_update: bool = False,
    dry_run: bool = True,
    plan_id: str | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or apply a report plus openId form tab scenario backed by a Project Database source view."""
    normalized_view_id = source_view_id.strip()
    normalized_form_id = target_form_id.strip()
    normalized_report_name = report_name.strip()
    normalized_tab_name = tab_name.strip()
    normalized_cell_name = (cell_name or tab_name).strip()
    normalized_report_type = report_type.strip() or "dashboard"
    if not normalized_view_id:
        raise ValueError("source_view_id must not be empty.")
    if not normalized_form_id:
        raise ValueError("target_form_id must not be empty.")
    if not normalized_report_name:
        raise ValueError("report_name must not be empty.")
    if not normalized_tab_name:
        raise ValueError("tab_name must not be empty.")
    if not normalized_cell_name:
        raise ValueError("cell_name must not be empty.")
    if expected_context_row_count is not None and expected_context_row_count < 0:
        raise ValueError("expected_context_row_count must be non-negative or null.")

    client = _client(profile, project_id)
    source_view = _find_view(client, view_id=normalized_view_id)
    if not source_view:
        raise ValueError(f"Source view {normalized_view_id!r} was not found.")
    source_view_name = str(source_view.get("name") or "")
    if expected_source_view_name and source_view_name != expected_source_view_name:
        raise ValueError(
            f"Source view name mismatch: expected {expected_source_view_name!r}, got {source_view_name!r}."
        )

    target_form = _find_form(client, form_id=normalized_form_id)
    if not target_form:
        raise ValueError(f"Target form {normalized_form_id!r} was not found.")
    _assert_managed_or_allowed(target_form, kind="Form", allow_unmanaged_update=allow_unmanaged_update)

    existing_report = _find_report(client, report_id=report_id, name=normalized_report_name)
    existing_report_full = (
        client.report_by_id(existing_report["_id"]).body
        if existing_report and existing_report.get("_id")
        else None
    )
    if existing_report and not allow_unmanaged_update and not _report_is_manageable(existing_report, existing_report_full):
        raise ValueError(
            f"Report {existing_report.get('_id')!r} is not marked as Codex-managed; pass allow_unmanaged_update=True."
        )

    view_fields = _view_fields_body(client, normalized_view_id)
    resolved_marker = marker or f"{MANAGED_MARKER}: alterios-mcp report tab {normalized_report_name}."
    template_payload: str | dict[str, Any] = template if template is not None else _project_database_dashboard_template(
        report_name=normalized_report_name,
        marker=resolved_marker,
        source_view_id=normalized_view_id,
        source_view_name=source_view_name,
        columns=_project_database_columns(view_fields),
    )

    operation = _report_tab_operation(
        source_view_id=normalized_view_id,
        target_form_id=normalized_form_id,
        report_name=normalized_report_name,
        report_id=report_id or (existing_report or {}).get("_id"),
        report_type=normalized_report_type,
        tab_name=normalized_tab_name,
        cell_name=normalized_cell_name,
        template=template_payload,
        marker=resolved_marker,
        context_content_id=context_content_id,
        expected_context_row_count=expected_context_row_count,
        open_id=open_id,
        fullscreen_mode=fullscreen_mode,
        replace_existing_tab=replace_existing_tab,
        allow_unmanaged_update=allow_unmanaged_update,
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
    )

    source_readback = client.view_data_simplified(normalized_view_id, limit=5, offset=0).as_dict()
    data_id_readback = None
    content_id_readback = None
    if context_content_id:
        data_id_readback = client.view_data(normalized_view_id, limit=5, offset=0, data_id=[context_content_id]).as_dict()
        content_id_readback = client.view_data(normalized_view_id, limit=5, offset=0, content_id=context_content_id).as_dict()
    planned_tabs = _tabs_with_report_tab(
        target_form,
        tab_name=normalized_tab_name,
        report_id=report_id or (existing_report or {}).get("_id") or "$report_id",
        cell_name=normalized_cell_name,
        open_id=open_id,
        fullscreen_mode=fullscreen_mode,
        replace_existing_tab=replace_existing_tab,
    )
    context_validation = {
        "checked": bool(context_content_id),
        "context_content_id": context_content_id,
        "source_row_count": _view_row_count(source_readback),
        "data_id_row_count": _view_row_count(data_id_readback) if data_id_readback else None,
        "content_id_row_count": _view_row_count(content_id_readback) if content_id_readback else None,
        "expected_context_row_count": expected_context_row_count,
    }
    context_validation["data_id_matches_expected"] = (
        not context_content_id
        or expected_context_row_count is None
        or context_validation["data_id_row_count"] == expected_context_row_count
    )
    response_payload: dict[str, Any] = {
        "source_view": _resource_summary(source_view),
        "target_form": _resource_summary(target_form),
        "report": _resource_summary(existing_report),
        "view_field_count": len(view_fields),
        "source_readback": source_readback,
        "context_readback": {
            "data_id": data_id_readback,
            "content_id": content_id_readback,
            "validation": context_validation,
        },
        "planned": {
            "report": {
                "_id": report_id or (existing_report or {}).get("_id"),
                "name": normalized_report_name,
                "type": normalized_report_type,
                "marker": resolved_marker,
                "template": template_payload,
            },
            "form_tabs": planned_tabs,
            "layout": analyze_stimulsoft_layout(template_payload),
        },
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)

    if not plan_id:
        raise ValueError("plan_id is required when dry_run=false for alterios_create_report_tab.")
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    assert_plan_matches_audit(plan_id=plan_id, audit=audit.as_dict())

    report_result = alterios_upsert_report(
        normalized_report_name,
        report_id=report_id,
        report_type=normalized_report_type,
        template=template_payload,
        description=resolved_marker,
        allow_unmanaged_update=allow_unmanaged_update,
        dry_run=False,
        profile=profile,
        project_id=project_id,
    )
    report_body = _response_body((report_result.get("response") or {}).get("readback"))
    resolved_report_id = _extract_response_id(report_body) or _extract_response_id(report_result) or report_id
    if not resolved_report_id:
        raise ValueError("Report id was not resolved after save.")

    next_tabs = _tabs_with_report_tab(
        target_form,
        tab_name=normalized_tab_name,
        report_id=resolved_report_id,
        cell_name=normalized_cell_name,
        open_id=open_id,
        fullscreen_mode=fullscreen_mode,
        replace_existing_tab=replace_existing_tab,
    )
    form_result = alterios_patch_form_tabs(
        normalized_form_id,
        next_tabs,
        expected_name=str(target_form.get("name") or "") or None,
        allow_unmanaged_update=True,
        dry_run=False,
        profile=profile,
        project_id=project_id,
    )

    report_readback = client.report_by_id(resolved_report_id).body
    form_readback = client.form_by_id(normalized_form_id).body
    report_validation = _report_project_base_validation(
        report_readback,
        expected_view_name=source_view_name,
        expected_marker=resolved_marker,
    )
    report_tab_cell = _find_report_tab_cell(form_readback, tab_name=normalized_tab_name, report_id=resolved_report_id)
    if not report_tab_cell:
        raise ValueError("Report tab cell was not visible on form readback.")
    params = report_tab_cell.get("params") if isinstance(report_tab_cell, dict) else {}
    readback_validation = {
        "report_project_database": report_validation,
        "layout": analyze_stimulsoft_layout(report_readback),
        "form_tab_found": report_tab_cell is not None,
        "form_tab_open_id": isinstance(params, dict) and params.get("openId") is True,
        "form_tab_report_id": params.get("reportId") if isinstance(params, dict) else None,
        "context": context_validation,
        "render_evidence": {
            "status": "not_collected",
            "note": "API/readback validation completed; browser Stimulsoft viewer render remains a separate UI evidence step.",
        },
    }
    response_payload.update(
        {
            "ids": {"report_id": resolved_report_id, "form_id": normalized_form_id, "source_view_id": normalized_view_id},
            "report_write": report_result,
            "form_write": form_result,
            "readback": {
                "report": _resource_summary(report_readback),
                "form": _resource_summary(form_readback),
                "report_tab_cell": report_tab_cell,
                "validation": readback_validation,
            },
        }
    )
    return controlled_write_result(audit=audit, response=response_payload, plan_id=plan_id)


@mcp.tool()
def alterios_discover_readonly(
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Probe the known safe read-only Alterios REST routes."""
    return discover_readonly(_client(profile, project_id))


@mcp.tool()
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


@mcp.tool()
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


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
