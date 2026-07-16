"""Pure payload, operation, and UI-fragment builders."""

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Any

from ..client import looks_like_uuid, strip_alterios_metadata
from ..services import get_service
from ..write_control import WriteOperation, classify_rest_write_risk, collect_target_ids

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

def _content_summary(content: dict[str, Any]) -> dict[str, Any]:
    fields = content.get("fields") or {}
    return {
        "_id": content.get("_id"),
        "contentTypeId": content.get("contentTypeId"),
        "name": content.get("name"),
        "field_keys": sorted(str(key) for key in fields.keys()) if isinstance(fields, dict) else [],
    }

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

def _project_icon_operation(
    *,
    icon_specs: list[dict[str, str]],
    size: int,
    color: str,
    style: str,
    force_upload: bool,
) -> WriteOperation:
    request = {
        "icons": icon_specs,
        "size": size,
        "color": color,
        "style": style,
        "force_upload": force_upload,
    }
    return _resource_operation(
        name="POST /api/file/upload/icon",
        kind="project_icons",
        method="POST",
        path="/api/file/upload/icon",
        summary="Ensure Google Fonts Icons are uploaded into the target Alterios project file manager and return project-local UUID iconId values.",
        request=request,
    )

def _project_icon_library_operation(
    *,
    library_dir: str,
    semantics: list[str],
    folder_hash: str,
    icons_folder_name: str | None,
    recurse: bool,
    force_upload: bool,
) -> WriteOperation:
    request = {
        "library_dir": library_dir,
        "semantics": semantics,
        "folder_hash": folder_hash,
        "icons_folder_name": icons_folder_name,
        "recurse": recurse,
        "force_upload": force_upload,
    }
    return _resource_operation(
        name="POST /api/file/upload/icon",
        kind="project_icon_library",
        method="POST",
        path="/api/file/upload/icon",
        summary="Ensure repo-stored Alterios project icon files are materialized into the target project file manager and return project-local iconId UUID values.",
        request=request,
    )

def _icon_registry_summary(registry: dict[str, Any]) -> dict[str, Any]:
    icons = registry.get("icons") or {}
    return {
        "icon_count": len(icons),
        "semantics": sorted(str(key) for key in icons.keys()),
    }

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

def _view_field_save_payload(field: dict[str, Any]) -> dict[str, Any]:
    payload = dict(strip_alterios_metadata(field))
    for key in ("contentType", "contentTypeField", "relatedViewField", "diagramsNames"):
        payload.pop(key, None)
    for key in ("attribute", "contentAttribute", "contentTypeFieldId", "contentTypeId", "processAttribute", "taskAttribute"):
        if payload.get(key) is None:
            payload.pop(key, None)
    return payload

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

def _report_template_has_marker(report: Any, marker: str | None = None) -> bool:
    template = _report_template_payload(report)
    return isinstance(template, dict) and template.get("CodexMarker") == (marker or None)

def _operation_result_shape(value: Any) -> str:
    if isinstance(value, dict):
        return "dict:" + ",".join(sorted(str(key) for key in value.keys())[:8])
    if isinstance(value, list):
        return f"list:{len(value)}"
    return type(value).__name__

def _material_resolve_content_name_template(template: str | None, fields: list[dict[str, Any]]) -> str | None:
    if template is None:
        return None
    resolved = template
    for field in fields:
        requested_mname = str(field.get("requested_mname") or "").strip()
        actual_mname = str(field.get("mname") or "").strip()
        if not requested_mname or not actual_mname or requested_mname == actual_mname:
            continue
        resolved = re.sub(r"{{\s*" + re.escape(requested_mname) + r"\s*}}", "{{" + actual_mname + "}}", resolved)
    return resolved

def _material_edit_from_view_action(
    *,
    icon_id: str | None,
    edit_form_id: str,
    edit_form_name: str,
    view_entity_id: str,
) -> dict[str, Any]:
    container: dict[str, Any] = {
        "type": "action",
        "title": "",
        "tooltip": "Редактировать",
        "styles": {},
        "actions": [
            {
                "_id": edit_form_id,
                "name": edit_form_name,
                "type": "forms",
                "openInDialog": True,
                "openInNewTab": False,
                "viewEntityId": view_entity_id,
                "argumentsConfig": {},
            }
        ],
        "position": "top_left",
        "conditions": [],
    }
    if icon_id:
        container["iconId"] = icon_id
    return container

def _material_open_form_container(
    *,
    tooltip: str,
    icon_id: str | None,
    form_id: str,
    form_name: str,
    view_entity_id: str,
    position: str,
    default: bool = False,
) -> dict[str, Any]:
    container: dict[str, Any] = {
        "type": "action",
        "title": "",
        "tooltip": tooltip,
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
        "default": default,
        "conditions": [],
    }
    if icon_id:
        container["iconId"] = icon_id
    return container

def _material_close_action_container(icon_id: str | None) -> dict[str, Any]:
    container: dict[str, Any] = {
        "type": "action",
        "title": "Закрыть",
        "styles": {},
        "actions": [
            {
                "_id": None,
                "type": "routing",
                "routingType": "redirect_back",
                "argumentsConfig": {},
            }
        ],
        "position": "bottom_left",
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

__all__ = ['_write_service_operation', '_manual_script_operation', '_rest_write_operation', '_add_comment_operation', '_content_fields_operation', '_file_upload_operation', '_content_summary', '_decode_file_payload', '_project_icon_operation', '_project_icon_library_operation', '_icon_registry_summary', '_resource_operation', '_resource_summary', '_security_resource_summary', '_security_resource_operation', '_security_payload', '_view_field_save_payload', '_report_template_payload', '_report_template_has_marker', '_operation_result_shape', '_material_resolve_content_name_template', '_material_edit_from_view_action', '_material_open_form_container', '_material_close_action_container', '_material_save_action_container']
