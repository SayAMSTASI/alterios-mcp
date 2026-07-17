from __future__ import annotations

from .._support import *
from ..validators.module_contract import is_meaningful_description

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
        "description": description if description is not None else (existing or {}).get("description"),
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
        "module_contract": {
            "ok": is_meaningful_description(payload.get("description")),
            "blocking_issue": None
            if is_meaningful_description(payload.get("description"))
            else {
                "code": "content_type_description_missing",
                "path": "description",
                "message": "A low-level content type upsert requires a meaningful user-facing description before apply.",
            },
        },
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    if not response_payload["module_contract"]["ok"]:
        raise ValueError(
            "Alterios module UX contract failed: content_type_description_missing at description. "
            "Pass a meaningful content type description before apply."
        )
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    saved = client.save_content_type(payload).as_dict()
    saved_id = _extract_response_id(saved) or payload.get("_id")
    readback = client.content_type_by_id(saved_id).as_dict() if saved_id else {"body": _find_content_type(client, name=name)}
    response_payload.update({"saved": saved, "readback": readback})
    return controlled_write_result(audit=audit, response=response_payload)

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

__all__ = ['alterios_list_comments', 'alterios_add_comment', 'alterios_upsert_content_type', 'alterios_plan_content_type_publish', 'alterios_clone_shared_content_type', 'alterios_upsert_field', 'alterios_create_content', 'alterios_upsert_group', 'alterios_upsert_help', 'alterios_update_content_fields', 'alterios_bulk_update_selected_content_fields', 'alterios_file_upload_to_field']
