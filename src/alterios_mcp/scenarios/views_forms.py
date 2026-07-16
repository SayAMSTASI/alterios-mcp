from __future__ import annotations

from .._support import *
from ..ux_contract import assert_form_contract
from .content import (
    alterios_upsert_content_type,
    alterios_upsert_field,
    alterios_upsert_group,
)

def alterios_upsert_view(
    name: str,
    view_id: str | None = None,
    description: str | None = None,
    format: str | None = None,
    settings: dict[str, Any] | None = None,
    strict: bool | None = None,
    allow_legacy_mode: bool = False,
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
    merged_settings = dict((existing or {}).get("settings") or {})
    if settings is not None:
        merged_settings.update(settings)
    if not allow_legacy_mode and merged_settings.get("engineVersion") not in (None, "v2"):
        raise ValueError("Alterios views must use experimental mode: settings.engineVersion must be 'v2'.")
    if not allow_legacy_mode:
        merged_settings["engineVersion"] = "v2"
    effective_format = format if format is not None else (existing or {}).get("format") or "table"
    format_warnings = _validate_view_format_settings(effective_format, merged_settings)
    payload = {
        **(existing or {}),
        "name": name,
        "description": description if description is not None else (existing or {}).get("description") or f"{MANAGED_MARKER}: alterios-mcp view.",
        "format": effective_format,
        "settings": merged_settings,
        "strict": strict if strict is not None else (existing or {}).get("strict") or False,
    }
    operation = _resource_operation(
        name=("PATCH /api/views/{id}" if existing else "POST /api/views"),
        kind="view",
        method="PATCH" if existing else "POST",
        path=f"/api/views/{existing.get('_id')}" if existing else "/api/views",
        summary="Create or update an Alterios view with preflight and readback.",
        request={"_id": payload.get("_id"), "name": name, "allowLegacyMode": allow_legacy_mode},
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
        "format_warnings": format_warnings,
        "planned_payload": strip_alterios_metadata(payload),
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    saved = client.save_view(payload).as_dict()
    saved_id = ((saved.get("body") or {}) if isinstance(saved, dict) else {}).get("_id") or payload.get("_id")
    readback_body = client.view_by_id(saved_id).as_dict() if saved_id else {"body": _find_view(client, name=name)}
    readback_resource = readback_body.get("body") if isinstance(readback_body, dict) else None
    readback_settings = readback_resource.get("settings") if isinstance(readback_resource, dict) else None
    response_payload.update(
        {
            "saved": saved,
            "readback": readback_body,
            "readback_warnings": _view_format_readback_warnings(effective_format, merged_settings, readback_settings),
        }
    )
    return controlled_write_result(audit=audit, response=response_payload)

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
    entity = _find_view_entity(client, view_id=view_id, entity_id=entity_id)
    if not entity:
        raise ValueError(f"View entity {entity_id!r} was not found in view {view_id!r}.")
    existing = _find_view_field(
        client,
        view_id=view_id,
        view_field_id=view_field_id,
        entity_id=entity_id,
        attribute=attribute,
        content_type_field_id=content_type_field_id,
    )
    add_request = _view_entity_field_add_request(
        entity,
        attribute=attribute,
        content_type_field_id=content_type_field_id,
    )
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
        "planned_payload": (
            _view_field_save_payload(_normalize_view_field_payload_for_entity(payload, entity, attribute=attribute))
            if existing
            else None
        ),
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
            content_type_id=add_request.get("contentTypeId"),
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
    payload = _normalize_view_field_payload_for_entity(payload, entity, attribute=attribute)
    saved = client.save_view_field(_view_field_save_payload(payload)).as_dict()
    readback = _find_view_field(client, view_id=view_id, view_field_id=payload.get("_id"))
    response_payload.update({"added": add_response, "saved": saved, "readback": readback})
    return controlled_write_result(audit=audit, response=response_payload)

def alterios_upsert_form(
    name: str,
    form_id: str | None = None,
    page_title: str | None = None,
    tabs: list[dict[str, Any]] | None = None,
    form_action_containers: list[dict[str, Any]] | None = None,
    description: str | None = None,
    enforce_ux_contract: bool = False,
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
    ux_contract = analyze_form_surface(payload, strict=enforce_ux_contract)
    operation = _resource_operation(
        name=("PATCH /api/forms/{id}" if existing else "POST /api/forms"),
        kind="form",
        method="PATCH" if existing else "POST",
        path=f"/api/forms/{existing.get('_id')}" if existing else "/api/forms",
        summary="Create or update an Alterios form with managed-object guard and readback.",
        request={"_id": payload.get("_id"), "name": name, "enforceUxContract": enforce_ux_contract},
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
        "ux_contract": ux_contract,
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    if enforce_ux_contract and not ux_contract["ok"]:
        blocking = ", ".join(ux_contract.get("blocking_issues_by_code", {}))
        raise ValueError(f"Alterios UX contract blocks form apply: {blocking}")
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    saved = client.save_form(payload).as_dict()
    saved_id = ((saved.get("body") or {}) if isinstance(saved, dict) else {}).get("_id") or payload.get("_id")
    readback_body = client.form_by_id(saved_id).as_dict() if saved_id else {"body": _find_form(client, name=name)}
    response_payload.update({"saved": saved, "readback": readback_body})
    return controlled_write_result(audit=audit, response=response_payload)

def alterios_create_material_module(
    module_name: str,
    field_name_prefix: str,
    fields: list[dict[str, Any]],
    content_type_id: str | None = None,
    view_id: str | None = None,
    add_form_id: str | None = None,
    edit_form_id: str | None = None,
    view_form_id: str | None = None,
    list_form_id: str | None = None,
    group_id: str | None = None,
    names: dict[str, str] | None = None,
    content_name_template: str | None = None,
    content_type_description: str | None = None,
    parent_group_id: str | None = None,
    icon_id: str | None = "inventory_2",
    add_icon_id: str | None = "add",
    edit_icon_id: str | None = "edit",
    view_icon_id: str | None = "preview",
    delete_icon_id: str | None = "delete",
    menu_icon_id: str | None = "menu",
    close_icon_id: str | None = "keyboard_return",
    save_icon_id: str | None = "save",
    delivery_evidence: dict[str, Any] | None = None,
    expected_runtime_fingerprint: str | None = None,
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
    icon_contract = _material_module_icon_contract(
        icon_id=icon_id,
        add_icon_id=add_icon_id,
        edit_icon_id=edit_icon_id,
        view_icon_id=view_icon_id,
        delete_icon_id=delete_icon_id,
        menu_icon_id=menu_icon_id,
        close_icon_id=close_icon_id,
        save_icon_id=save_icon_id,
    )
    operation = _material_module_operation(
        module_name=normalized_module_name,
        field_name_prefix=normalized_prefix,
        fields=normalized_fields,
        content_type_id=content_type_id,
        view_id=view_id,
        add_form_id=add_form_id,
        edit_form_id=edit_form_id,
        view_form_id=view_form_id,
        list_form_id=list_form_id,
        group_id=group_id,
        parent_group_id=parent_group_id,
        names=resolved_names,
        content_name_template=content_name_template,
        content_type_description=content_type_description,
        icon_id=icon_id,
        add_icon_id=add_icon_id,
        edit_icon_id=edit_icon_id,
        view_icon_id=view_icon_id,
        delete_icon_id=delete_icon_id,
        menu_icon_id=menu_icon_id,
        close_icon_id=close_icon_id,
        save_icon_id=save_icon_id,
        delivery_evidence=delivery_evidence,
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
        view_form_id=view_form_id,
        list_form_id=list_form_id,
        group_id=group_id,
        parent_group_id=parent_group_id,
        allow_unmanaged_update=allow_unmanaged_update,
    )
    planned_preview = _material_module_plan_preview(
        module_name=normalized_module_name,
        names=resolved_names,
        fields=normalized_fields,
        field_name_prefix=normalized_prefix,
        content_type_id=content_type_id or (preflight.get("content_type") or {}).get("_id"),
        view_id=view_id or (preflight.get("view") or {}).get("_id"),
        add_form_id=add_form_id or ((preflight.get("forms") or {}).get("add") or {}).get("_id"),
        edit_form_id=edit_form_id or ((preflight.get("forms") or {}).get("edit") or {}).get("_id"),
        view_form_id=view_form_id or ((preflight.get("forms") or {}).get("view") or {}).get("_id"),
        list_form_id=list_form_id or ((preflight.get("forms") or {}).get("list") or {}).get("_id"),
        group_id=group_id or (preflight.get("group") or {}).get("_id"),
        parent_group_id=parent_group_id or (preflight.get("parent_group") or {}).get("_id"),
        icon_id=icon_id,
        add_icon_id=add_icon_id,
        edit_icon_id=edit_icon_id,
        view_icon_id=view_icon_id,
        delete_icon_id=delete_icon_id,
        menu_icon_id=menu_icon_id,
        close_icon_id=close_icon_id,
        save_icon_id=save_icon_id,
    )
    form_contracts = {
        role: analyze_form_surface(
            {
                "name": form["name"],
                "pageTitle": form["page_title"],
                "tabs": form["tabs"],
                "formActionContainers": form["formActionContainers"],
            },
            strict=True,
        )
        for role, form in planned_preview["forms"].items()
    }
    response_payload: dict[str, Any] = {
        "module_name": normalized_module_name,
        "names": resolved_names,
        "icon_contract": icon_contract,
        "form_contracts": form_contracts,
        "preflight": preflight,
        "planned": planned_preview,
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)

    if not plan_id:
        raise ValueError("plan_id is required when dry_run=false for alterios_create_material_module.")
    assert_plan_matches_audit(plan_id=plan_id, audit=audit.as_dict())
    if not icon_contract["ok"]:
        invalid = ", ".join(icon_contract["invalid"])
        raise ValueError(
            "Material module apply requires target-project-local UUID iconIds. "
            f"Resolve icons with alterios_ensure_project_icon_library first: {invalid}."
        )
    for form_contract in form_contracts.values():
        assert_form_contract(form_contract)
    verified_delivery_evidence = _assert_delivery_evidence(delivery_evidence)
    runtime_gate = _assert_runtime_gate(expected_runtime_fingerprint)
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())

    steps: list[dict[str, Any]] = []

    content_type_result = alterios_upsert_content_type(
        resolved_names["content_type"],
        content_type_id=content_type_id,
        field_name_prefix=normalized_prefix,
        content_name_template=content_name_template,
        description=_managed_description(
            content_type_description,
            f"справочник «{resolved_names['content_type']}» для хранения пользовательских записей модуля.",
        ),
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
        saved_field = {**field, "_id": field_id, "requested_mname": field["mname"]}
        if isinstance(field_body, dict):
            saved_field.update({key: value for key, value in field_body.items() if key in {"_id", "name", "mname", "type"}})
        saved_field["view_mname"] = _material_view_mname(str(saved_field.get("mname") or field["mname"]), normalized_prefix)
        saved_fields.append(saved_field)
        steps.append(
            {
                "step": "field",
                "id": field_id,
                "mname": saved_field.get("mname"),
                "requested_mname": field["mname"],
                "result": field_result,
            }
        )

    resolved_content_name_template = _material_resolve_content_name_template(content_name_template, saved_fields)
    if resolved_content_name_template and resolved_content_name_template != content_name_template:
        content_type_template_result = alterios_upsert_content_type(
            resolved_names["content_type"],
            content_type_id=content_type_id,
            field_name_prefix=normalized_prefix,
            content_name_template=resolved_content_name_template,
            description=_managed_description(
                content_type_description,
                f"справочник «{resolved_names['content_type']}» для хранения пользовательских записей модуля.",
            ),
            allow_unmanaged_update=allow_unmanaged_update,
            dry_run=False,
            profile=profile,
            project_id=project_id,
        )
        steps.append(
            {
                "step": "content_type_template",
                "id": content_type_id,
                "content_name_template": resolved_content_name_template,
                "result": content_type_template_result,
            }
        )

    view_result = alterios_upsert_view(
        resolved_names["view"],
        view_id=view_id,
        format="table",
        settings={"engineVersion": "v2"},
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
        view_field_id = _extract_response_id(view_field_body)
        if isinstance(view_field_body, dict) and view_field_body.get("mname"):
            field["view_mname"] = str(view_field_body["mname"])
        saved_view_fields.append(
            {
                "field_id": field["_id"],
                "field_mname": field["mname"],
                "requested_field_mname": field.get("requested_mname"),
                "view_field_id": view_field_id,
                "view_mname": field["view_mname"],
            }
        )
        steps.append({"step": "view_field", "field_id": field["_id"], "result": view_field_result})

    view_settings_result = alterios_upsert_view(
        resolved_names["view"],
        view_id=view_id,
        format="table",
        settings={"engineVersion": "v2", "title": saved_fields[0]["view_mname"]},
        allow_unmanaged_update=True,
        dry_run=False,
        profile=profile,
        project_id=project_id,
    )
    steps.append(
        {
            "step": "view_settings",
            "id": view_id,
            "settings": {"engineVersion": "v2", "title": saved_fields[0]["view_mname"]},
            "result": view_settings_result,
        }
    )

    add_tabs = [
        {
            "name": None,
            "rows": [_material_content_form_row(normalized_module_name, content_type_id, saved_fields)],
        }
    ]
    add_form_result = alterios_upsert_form(
        resolved_names["add_form"],
        form_id=add_form_id,
        page_title=resolved_names["add_page_title"],
        tabs=add_tabs,
        form_action_containers=_material_edit_form_actions(close_icon_id=close_icon_id, save_icon_id=save_icon_id),
        enforce_ux_contract=True,
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
        page_title=resolved_names["edit_page_title"],
        tabs=edit_tabs,
        form_action_containers=_material_edit_form_actions(close_icon_id=close_icon_id, save_icon_id=save_icon_id),
        enforce_ux_contract=True,
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

    view_tabs = [
        {
            "name": None,
            "rows": [
                _material_view_form_row(
                    module_name=normalized_module_name,
                    view_id=view_id,
                    fields=saved_fields,
                    edit_form_id=edit_form_id,
                    edit_form_name=resolved_names["edit_form"],
                    view_entity_id=view_entity_id,
                    edit_icon_id=edit_icon_id,
                ),
            ],
        }
    ]
    view_form_result = alterios_upsert_form(
        resolved_names["view_form"],
        form_id=view_form_id,
        page_title=resolved_names["view_page_title"],
        tabs=view_tabs,
        form_action_containers=[_material_close_action_container(close_icon_id)],
        enforce_ux_contract=True,
        allow_unmanaged_update=allow_unmanaged_update,
        dry_run=False,
        profile=profile,
        project_id=project_id,
    )
    view_form_body = _response_body((view_form_result.get("response") or {}).get("readback"))
    view_form_id = _extract_response_id(view_form_body) or _extract_response_id(view_form_result) or view_form_id
    if not view_form_id:
        raise ValueError("View form id was not resolved after save.")
    steps.append({"step": "view_form", "id": view_form_id, "result": view_form_result})

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
                    view_form_id=view_form_id,
                    view_form_name=resolved_names["view_form"],
                    fields=saved_fields,
                    add_icon_id=add_icon_id,
                    edit_icon_id=edit_icon_id,
                    view_icon_id=view_icon_id,
                    delete_icon_id=delete_icon_id,
                    menu_icon_id=menu_icon_id,
                )
            ],
        }
    ]
    list_form_result = alterios_upsert_form(
        resolved_names["list_form"],
        form_id=list_form_id,
        page_title=resolved_names["list_page_title"],
        tabs=list_tabs,
        form_action_containers=[],
        enforce_ux_contract=True,
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
            "view": _resource_summary(_find_form(client, form_id=view_form_id)),
            "list": _resource_summary(_find_form(client, form_id=list_form_id)),
        },
        "group": _resource_summary(_find_group(client, group_id=group_id)),
    }
    response_payload.update(
        {
            "ids": {
                "content_type_id": content_type_id,
                "field_ids": {field["mname"]: field["_id"] for field in saved_fields},
                "requested_field_ids": {field["requested_mname"]: field["_id"] for field in saved_fields},
                "view_id": view_id,
                "view_entity_id": view_entity_id,
                "add_form_id": add_form_id,
                "edit_form_id": edit_form_id,
                "view_form_id": view_form_id,
                "list_form_id": list_form_id,
                "group_id": group_id,
            },
            "steps": steps,
            "readback": readback,
            "delivery_evidence": verified_delivery_evidence,
            "runtime_gate": runtime_gate,
        }
    )
    return controlled_write_result(audit=audit, response=response_payload, plan_id=plan_id)

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


def _material_module_icon_contract(**icon_ids: str | None) -> dict[str, Any]:
    invalid = sorted(name for name, value in icon_ids.items() if not value or not looks_like_uuid(str(value)))
    return {
        "ok": not invalid,
        "required": sorted(icon_ids),
        "invalid": invalid,
        "resolution_tool": "alterios_ensure_project_icon_library",
    }

def alterios_upsert_form_manual_script_action(
    form_id: str,
    script_id: str,
    scope: str,
    title: str,
    icon_id: str,
    argument_bindings: dict[str, str] | None = None,
    argument_entity_ids: dict[str, str] | None = None,
    action_view_entity_id: str | None = None,
    view_id: str | None = None,
    tab_index: int | None = None,
    row_index: int | None = None,
    cell_index: int | None = None,
    menu_icon_id: str | None = None,
    tooltip: str | None = None,
    position: str | None = None,
    default: bool = False,
    save_before_execute: bool = False,
    expected_form_name: str | None = None,
    expected_script_name: str | None = None,
    expected_script_active: bool = True,
    enforce_ux_contract: bool = False,
    allow_unmanaged_update: bool = False,
    dry_run: bool = True,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or upsert a manual script action on a page, element, or row value with verified id bindings."""
    normalized_scope = str(scope or "").strip().lower()
    if normalized_scope not in {"page", "element", "value"}:
        raise ValueError("scope must be one of: page, element, value.")
    if not looks_like_uuid(script_id):
        raise ValueError("script_id must be a saved manual script UUID.")
    if not looks_like_uuid(icon_id):
        raise ValueError("icon_id must be a project-local icon UUID.")
    if menu_icon_id and not looks_like_uuid(menu_icon_id):
        raise ValueError("menu_icon_id must be a project-local icon UUID.")

    client = _client(profile, project_id)
    existing = _find_form(client, form_id=form_id)
    if not existing:
        raise ValueError(f"Form {form_id!r} was not found.")
    if expected_form_name and existing.get("name") != expected_form_name:
        raise ValueError(f"Form name mismatch: expected {expected_form_name!r}, got {existing.get('name')!r}.")
    _assert_managed_or_allowed(existing, kind="Form", allow_unmanaged_update=allow_unmanaged_update)

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
    cell = None
    if normalized_scope != "page":
        cell = form_cell(
            existing,
            tab_index=tab_index,
            row_index=row_index,
            cell_index=cell_index,
        )
    cell_bound_view_id = cell_view_id(cell)
    if view_id and cell_bound_view_id and view_id != cell_bound_view_id:
        raise ValueError(
            f"view_id {view_id!r} does not match the target cell viewId {cell_bound_view_id!r}."
        )
    resolved_view_id = view_id or cell_bound_view_id
    needs_view_fields = bool(argument_entity_ids) or (
        normalized_scope in {"element", "value"} and bool(argument_bindings)
    )
    if needs_view_fields and not resolved_view_id:
        raise ValueError("A viewId is required to validate or resolve element/value action bindings.")
    view_fields = _view_fields_body(client, resolved_view_id) if resolved_view_id else []
    bindings, resolved_entities = normalize_argument_bindings(
        argument_bindings,
        argument_entity_ids,
        view_fields=view_fields,
    )
    normalized_action_view_entity_id = str(action_view_entity_id or "").strip() or None
    entity_ids = {
        str(entity_id or "").strip()
        for entity_id in (argument_entity_ids or {}).values()
        if str(entity_id or "").strip()
    }
    if normalized_scope == "value" and normalized_action_view_entity_id is None and len(entity_ids) == 1:
        normalized_action_view_entity_id = next(iter(entity_ids))
    binding_validation = validate_manual_script_bindings(
        script=script,
        scope=normalized_scope,
        bindings=bindings,
        available_provider_keys=available_cell_provider_keys(cell, view_fields),
        action_view_entity_id=normalized_action_view_entity_id,
    )
    if not binding_validation["ok"]:
        codes = ", ".join(issue["code"] for issue in binding_validation["issues"] if issue["severity"] == "error")
        raise ValueError(f"Manual script action binding validation failed: {codes}.")

    action_container = build_manual_script_action_container(
        script=script,
        scope=normalized_scope,
        title=title,
        tooltip=tooltip,
        icon_id=icon_id,
        bindings=bindings,
        action_view_entity_id=normalized_action_view_entity_id,
        position=position,
        default=default,
        save_before_execute=save_before_execute,
    )
    updated, action_location = upsert_manual_script_action(
        existing,
        scope=normalized_scope,
        action_container=action_container,
        script_id=script_id,
        tab_index=tab_index,
        row_index=row_index,
        cell_index=cell_index,
        menu_icon_id=menu_icon_id,
    )
    ux_contract = analyze_form_surface(updated, strict=enforce_ux_contract)
    operation = _resource_operation(
        name="PATCH /api/forms/{id}",
        kind="form_manual_script_action",
        method="PATCH",
        path=f"/api/forms/{form_id}",
        summary="Upsert a typed manual script form action with verified context and view id bindings.",
        request={
            "_id": form_id,
            "scriptId": script_id,
            "scope": normalized_scope,
            "viewId": resolved_view_id,
            "argumentBindings": bindings,
            "actionViewEntityId": normalized_action_view_entity_id,
        },
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
    )
    response_payload: dict[str, Any] = {
        "form": _resource_summary(existing),
        "script": _resource_summary(script),
        "scope": normalized_scope,
        "view_id": resolved_view_id,
        "action_location": action_location,
        "resolved_argument_bindings": bindings,
        "resolved_entity_fields": resolved_entities,
        "binding_validation": binding_validation,
        "ux_contract": ux_contract,
        "diff": _resource_diff(existing, updated, ("tabs", "formActionContainers")),
        "planned_action": action_container,
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    if enforce_ux_contract and not ux_contract["ok"]:
        blocking = ", ".join(ux_contract.get("blocking_issues_by_code", {}))
        raise ValueError(f"Alterios UX contract blocks form apply: {blocking}")
    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=_write_enabled(),
    )
    saved = client.save_form(updated).as_dict()
    readback_response = client.form_by_id(form_id).as_dict()
    readback_body = readback_response.get("body") if isinstance(readback_response, dict) else None
    readback_action = (
        find_manual_script_action(readback_body, script_id)
        if isinstance(readback_body, dict)
        else None
    )
    if not readback_action:
        raise ValueError("Manual script action was not visible in form readback.")
    response_payload.update(
        {
            "saved": saved,
            "readback": readback_response,
            "readback_action": readback_action,
        }
    )
    return controlled_write_result(audit=audit, response=response_payload)

def alterios_analyze_form_surface(
    form_id: str | None = None,
    form: dict[str, Any] | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Analyze an Alterios form for layout gaps, data sources, roles, styles, and icon-first actions."""
    return _form_surface_result(
        form_id=form_id,
        form=form,
        profile=profile,
        project_id=project_id,
        strict=False,
    )

def alterios_validate_form_contract(
    form_id: str | None = None,
    form: dict[str, Any] | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Validate an Alterios form against the blocking UX contract."""
    return _form_surface_result(
        form_id=form_id,
        form=form,
        profile=profile,
        project_id=project_id,
        strict=True,
    )

def _form_surface_result(
    *,
    form_id: str | None,
    form: dict[str, Any] | None,
    profile: str | None,
    project_id: str | None,
    strict: bool,
) -> dict[str, Any]:
    if not form_id and form is None:
        raise ValueError("Provide form_id for live read or form JSON for offline analysis.")
    if form_id and form is not None:
        raise ValueError("Provide either form_id or form, not both.")
    if form_id:
        client = _client(profile, project_id)
        form_body = _find_form(client, form_id=form_id)
        if not form_body:
            raise ValueError(f"Form {form_id!r} was not found.")
        field_type_map = _form_field_type_map(client, form_body)
    else:
        form_body = form
        field_type_map = {}
    if not isinstance(form_body, dict):
        raise ValueError("Form payload must be a JSON object.")
    return {
        "form": _resource_summary(form_body),
        "surface": analyze_form_surface(form_body, field_type_map=field_type_map, strict=strict),
    }

def _form_field_type_map(client: AlteriosClient, form: dict[str, Any]) -> dict[str, str]:
    field_types: dict[str, str] = {}
    for view_id in sorted(_form_view_ids(form)):
        try:
            body = client.view_fields_populated(view_id).body
        except Exception:
            continue
        rows = body if isinstance(body, list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            mname = row.get("mname")
            if not mname:
                continue
            content_field = row.get("contentTypeField")
            field_type = ""
            if isinstance(content_field, dict):
                field_type = str(content_field.get("type") or "")
            if not field_type:
                field_type = str(row.get("type") or "")
            if field_type:
                field_types[str(mname)] = field_type
    return field_types

def _form_view_ids(form: dict[str, Any]) -> set[str]:
    view_ids: set[str] = set()
    for value in _walk_values(form):
        if not isinstance(value, dict):
            continue
        params = value.get("params")
        if isinstance(params, dict) and params.get("viewId"):
            view_ids.add(str(params["viewId"]))
    return view_ids

__all__ = ['alterios_upsert_view', 'alterios_upsert_view_entity', 'alterios_upsert_view_field', 'alterios_upsert_form', 'alterios_create_material_module', 'alterios_patch_form_actions', 'alterios_patch_form_tabs', 'alterios_patch_form_cell_listeners', 'alterios_upsert_form_manual_script_action', 'alterios_analyze_form_surface', 'alterios_validate_form_contract']
