from __future__ import annotations

from .._support import *
from ..ux_contract import assert_form_contract
from .views_forms import alterios_upsert_form

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

def alterios_validate_printable_render(
    report_id: str | None = None,
    template: str | dict[str, Any] | None = None,
    sample_rows: list[dict[str, Any]] | None = None,
    output_path: str | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Render a printable Stimulsoft report in Chromium and export PDF evidence."""
    if not report_id and template is None:
        raise ValueError("Pass report_id or template.")
    client = _client(profile, project_id)
    report = client.report_by_id(report_id).body if report_id else None
    if report_id and not isinstance(report, dict):
        raise ValueError("Report readback returned unexpected payload.")
    source: Any = report if report_id else {"template": template}
    normalized = _report_template_payload(source)
    if not isinstance(normalized, dict):
        raise ValueError("Report has no parseable Stimulsoft template.")
    if not _report_has_printable_page({"template": normalized}):
        raise ValueError("Printable render validation requires at least one StiPage.")
    layout = analyze_stimulsoft_layout(normalized)
    if not layout.get("ok"):
        raise ValueError("Printable report layout has blocking errors; fix them before render validation.")
    rows = sample_rows or _printable_smoke_rows(normalized)
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("sample_rows must contain JSON objects.")
    scripts_dir = _ensure_stimulsoft_assets(client.config.base_url)
    target = output_path or str(
        artifact_root()
        / "report-renders"
        / f"{report_id or 'template'}-{int(time.time())}.pdf"
    )
    render = render_printable_pdf(
        normalized,
        rows=rows,
        reports_script=scripts_dir / "stimulsoft.reports.pack.js",
        output_path=target,
    )
    return {
        "readonly": True,
        "report": _resource_summary(report) if isinstance(report, dict) else None,
        "layout": layout,
        "sample_row_count": len(rows),
        "render": render,
    }

def alterios_create_report_tab(
    source_view_id: str,
    target_form_id: str,
    report_name: str,
    report_id: str | None = None,
    tab_name: str = "Отчет",
    cell_name: str | None = None,
    report_type: str = "report",
    template: str | dict[str, Any] | None = None,
    marker: str | None = None,
    expected_source_view_name: str | None = None,
    context_content_id: str | None = None,
    expected_context_row_count: int | None = 1,
    open_id: bool = True,
    fullscreen_mode: bool = False,
    replace_existing_tab: bool = True,
    delivery_evidence: dict[str, Any] | None = None,
    expected_runtime_fingerprint: str | None = None,
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
    requested_report_type = report_type.strip().lower() or "report"
    if requested_report_type not in {"report", "printable", "dashboard"}:
        raise ValueError("report_type must be 'report'/'printable' or 'dashboard'.")
    normalized_report_type = "report" if requested_report_type == "printable" else requested_report_type
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
    report_columns = _project_database_columns(view_fields)
    client_config = getattr(client, "config", None)
    base_url = str(getattr(client_config, "base_url", "") or "")
    if template is not None:
        template_payload: str | dict[str, Any] = template
    elif normalized_report_type == "report":
        template_payload = _project_database_native_printable_template(
            report_name=normalized_report_name,
            marker=resolved_marker,
            source_view_id=normalized_view_id,
            source_view_name=source_view_name,
            columns=report_columns,
            base_url=base_url,
        )
    else:
        template_payload = _project_database_native_dashboard_template(
            report_name=normalized_report_name,
            marker=resolved_marker,
            source_view_id=normalized_view_id,
            source_view_name=source_view_name,
            columns=report_columns,
            base_url=base_url,
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
    planned_form = {**target_form, "tabs": planned_tabs}
    form_contract = analyze_form_surface(planned_form, strict=True)
    printable_template = _report_template_payload({"template": template_payload})
    printable_summary = _printable_band_summary(printable_template)
    required_bands = list(PRINTABLE_REPORT_DEFAULT["required_bands"])
    missing_bands = [band for band in required_bands if band not in printable_summary["bands"]]
    printable_contract = {
        "ok": normalized_report_type != "report" or not missing_bands,
        "required_bands": required_bands,
        "missing_bands": missing_bands,
        "summary": printable_summary,
    }
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
            "form_contract": form_contract,
            "printable_contract": printable_contract,
        },
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)

    if not plan_id:
        raise ValueError("plan_id is required when dry_run=false for alterios_create_report_tab.")
    assert_plan_matches_audit(plan_id=plan_id, audit=audit.as_dict())
    assert_form_contract(form_contract)
    if not printable_contract["ok"]:
        raise ValueError(
            "Printable report template is missing required bands: "
            + ", ".join(printable_contract["missing_bands"])
        )
    verified_delivery_evidence = _assert_delivery_evidence(delivery_evidence)
    runtime_gate = _assert_runtime_gate(expected_runtime_fingerprint)
    assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=_write_enabled())

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
    form_result = alterios_upsert_form(
        str(target_form.get("name") or ""),
        form_id=normalized_form_id,
        tabs=next_tabs,
        enforce_ux_contract=True,
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
    report_validation["kind_matches_report_type"] = (
        report_validation["has_printable_page"]
        if normalized_report_type == "report"
        else report_validation["has_dashboard_page"]
    )
    if not report_validation["kind_matches_report_type"]:
        raise ValueError(
            f"Saved report template kind does not match report_type={normalized_report_type!r}."
        )
    if normalized_report_type == "report":
        saved_missing_bands = [
            band
            for band in required_bands
            if band not in report_validation["printable"]["bands"]
        ]
        if saved_missing_bands:
            raise ValueError(
                "Saved printable report is missing required bands: "
                + ", ".join(saved_missing_bands)
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
            "delivery_evidence": verified_delivery_evidence,
            "runtime_gate": runtime_gate,
        }
    )
    return controlled_write_result(audit=audit, response=response_payload, plan_id=plan_id)

__all__ = ['alterios_upsert_report', 'alterios_patch_report_template', 'alterios_validate_report_project_base', 'alterios_validate_stimulsoft_layout', 'alterios_validate_printable_render', 'alterios_create_report_tab']
