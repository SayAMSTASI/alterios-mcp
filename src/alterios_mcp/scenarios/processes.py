from __future__ import annotations

from .._support import *
from .views_forms import alterios_upsert_form

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
    """Plan or create/update an Alterios web/cron/manual/event/library/diagram script."""
    if not name.strip():
        raise ValueError("name must not be empty.")
    client = _client(profile, project_id)
    existing = _find_script(client, script_id=script_id, name=name)
    if existing:
        _assert_managed_or_allowed(existing, kind="Script", allow_unmanaged_update=allow_unmanaged_update)
    elif body is None:
        raise ValueError("body is required when creating a new script.")

    effective_type = script_type or (existing or {}).get("type") or "manual"
    payload = {
        **(existing or {}),
        "name": name,
        "description": description if description is not None else (existing or {}).get("description") or f"{MANAGED_MARKER}: alterios-mcp script.",
        "type": effective_type,
        "active": _script_active_default(effective_type, existing, active),
        "body": body if body is not None else (existing or {}).get("body") or "",
        "share": share if share is not None else (existing or {}).get("share", False),
        "config": config if config is not None else (existing or {}).get("config") or {},
        "librariesIds": libraries_ids if libraries_ids is not None else (existing or {}).get("librariesIds") or [],
    }
    effective_config = payload["config"] if isinstance(payload["config"], dict) else {}
    _validate_script_type_config(effective_type, effective_config)
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
    delivery_evidence: dict[str, Any] | None = None,
    expected_runtime_fingerprint: str | None = None,
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
    verified_delivery_evidence = _assert_delivery_evidence(delivery_evidence)
    runtime_gate = _assert_runtime_gate(expected_runtime_fingerprint)
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())
    assert_plan_matches_audit(plan_id=plan_id, audit=audit.as_dict())

    form_result = alterios_upsert_form(
        normalized_task_form_name,
        form_id=task_form_id,
        page_title=task_form_page_title or normalized_task_form_name,
        tabs=planned_tabs,
        form_action_containers=planned_actions,
        description=task_form_description or f"{MANAGED_MARKER}: alterios-mcp process task form.",
        enforce_ux_contract=True,
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
    response_payload["delivery_evidence"] = verified_delivery_evidence
    response_payload["runtime_gate"] = runtime_gate
    return controlled_write_result(audit=audit, response=response_payload, plan_id=plan_id)

__all__ = ['alterios_view_data', 'alterios_upsert_script', 'alterios_validate_script', 'alterios_upsert_bpmn_diagram', 'alterios_list_process_tasks', 'alterios_start_process', 'alterios_complete_task', 'alterios_validate_process_result', 'alterios_create_process_flow']
