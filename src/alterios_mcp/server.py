from __future__ import annotations

import base64
import binascii
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
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
from .gitea_workboard import (
    GiteaClient,
    GiteaConfig,
    agent_report_body,
    assert_gitea_write_allowed,
    build_issue_payload,
    gitea_write_enabled,
    load_standard_labels,
    planned_gitea_result,
    sync_board_by_labels,
    transition_issue_stage,
)
from .local_workboard import (
    LocalWorkboardConfig,
    add_local_agent_report,
    create_local_work_item,
    ensure_local_workboard,
    list_local_work_items,
)
from .profile_smoke import run_profile_smoke
from .printable_render import render_printable_pdf
from .project_health import run_project_health
from .replay_smoke import run_replay_smoke
from .runtime_info import MCP_TOOL_SCHEMA_VERSION, build_runtime_fingerprint, collect_alterios_mcp_processes
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
from .write_plan import artifact_root, assert_plan_matches_audit, list_write_journal, list_write_plans, load_write_plan
from .ux_contract import BLOCKING_FORM_ISSUE_CODES, UX_CONTRACT_VERSION

mcp = FastMCP("alterios")

ALTERIOS_SCRIPT_TYPES = {"web", "cron", "manual", "event", "library", "diagram"}


def _client(profile: str | None = None, project_id: str | None = None) -> AlteriosClient:
    return AlteriosClient(AlteriosConfig.from_env(profile=profile).with_project_id(project_id))


def _write_enabled() -> bool:
    return os.environ.get("ALTERIOS_MCP_ALLOW_WRITE") == "1"


def _dangerous_write_enabled() -> bool:
    return os.environ.get("ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE") == "1"


def _runtime_fingerprint() -> dict[str, Any]:
    tool_count = len(re.findall(r"^@mcp\.tool\(\)", Path(__file__).read_text(encoding="utf-8"), flags=re.MULTILINE))
    return build_runtime_fingerprint(tool_count=tool_count)


def _assert_runtime_gate(expected_runtime_fingerprint: str | None = None) -> dict[str, Any]:
    runtime = _runtime_fingerprint()
    if runtime.get("stale"):
        raise ValueError("Alterios MCP runtime is stale: restart Codex/MCP before applying writes.")
    expected = (expected_runtime_fingerprint or os.environ.get("ALTERIOS_MCP_EXPECTED_RUNTIME_FINGERPRINT") or "").strip()
    if expected and runtime.get("fingerprint") != expected:
        raise ValueError("Alterios MCP runtime fingerprint does not match the reviewed runtime.")
    return runtime


def _assert_delivery_evidence(delivery_evidence: dict[str, Any] | None) -> dict[str, Any]:
    evidence = dict(delivery_evidence or {})
    work_item_ref = str(evidence.get("work_item_ref") or "").strip()
    handoffs = evidence.get("agent_handoff_refs")
    contract_version = str(evidence.get("ux_contract_version") or "").strip()
    if not work_item_ref:
        raise ValueError("delivery_evidence.work_item_ref is required for scenario apply.")
    if not isinstance(handoffs, list) or not [item for item in handoffs if str(item).strip()]:
        raise ValueError("delivery_evidence.agent_handoff_refs must contain at least one handoff reference.")
    if contract_version != UX_CONTRACT_VERSION:
        raise ValueError(
            f"delivery_evidence.ux_contract_version must be {UX_CONTRACT_VERSION!r}."
        )
    return {
        "work_item_ref": work_item_ref,
        "agent_handoff_refs": [str(item).strip() for item in handoffs if str(item).strip()],
        "ux_contract_version": contract_version,
    }


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


def _validate_script_type_config(script_type: str, config: dict[str, Any]) -> None:
    if script_type not in ALTERIOS_SCRIPT_TYPES:
        allowed = ", ".join(sorted(ALTERIOS_SCRIPT_TYPES))
        raise ValueError(f"script_type must be one of: {allowed}.")
    if script_type != "cron":
        return
    cron = config.get("cron")
    if not isinstance(cron, str) or not cron.strip():
        raise ValueError("cron script requires config.cron as a six-part string: second minute hour day month week.")
    if len(cron.split()) != 6:
        raise ValueError("cron script config.cron must contain six parts: second minute hour day month week.")


def _script_active_default(script_type: str, existing: dict[str, Any] | None, active: bool | None) -> bool:
    if active is not None:
        return active
    if existing and "active" in existing:
        return bool(existing["active"])
    return script_type not in {"web", "cron"}


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

PROJECT_ICON_SCHEMA_VERSION = 1
PROJECT_PUBLIC_FOLDER_HASH = "public_L3B1YmxpYw"
PROJECT_ICON_DEFAULTS = {
    "save": "save",
    "back": "arrow_back",
    "close": "close",
    "edit": "edit",
    "view": "visibility",
    "delete": "delete",
    "menu": "more_vert",
    "info": "info",
    "add": "add",
    "sync": "sync",
    "files": "attach_file",
    "bulk": "checklist",
    "report": "analytics",
    "process": "account_tree",
    "task": "task_alt",
    "group": "folder",
    "search": "search",
    "filter": "filter_alt",
}
PROJECT_ICON_FOLDER_HASH = "public_L3B1YmxpYy9pY29ucw"
PROJECT_ICON_LIBRARY_RELATIVE_DIR = Path("assets") / "icons" / "project-public"
PROJECT_ICON_EXTENSIONS = {".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp"}
PROJECT_ICON_USAGE_HINTS = {
    "add": "Добавление записи, строки, вкладки, вложения или нового элемента.",
    "add_2": "Добавление записи или элемента; проектный вариант иконки add.",
    "add_task": "Добавление задачи или этапа процесса.",
    "analytics": "Открытие аналитики, отчета, дашборда или расчетного среза.",
    "arrow_back": "Возврат на предыдущую форму или к списку.",
    "arrow_drop_down": "Раскрытие списка, выпадающего меню или компактного выбора.",
    "arrow_outward": "Переход наружу, открытие в новой вкладке или внешний переход.",
    "attach_file": "Работа с файлами, вложениями и file-field.",
    "attach_file_add": "Добавление файла, вложения или загрузка в file-field.",
    "automation": "Автоматизация, запуск сценария, робота, скрипта или фоновой обработки.",
    "build": "Настройка, техническое обслуживание или сборка параметров.",
    "calendar_check": "Проверка даты, календарного срока, планового события или дедлайна.",
    "cancel": "Отмена, отрицательный результат, признак Н или отклонение.",
    "category": "Категория, классификатор, тип или группировка сущностей.",
    "chat": "Комментарии, обсуждение, чат, обратная связь или поддержка.",
    "check_circle": "Подтверждение, успешный результат, признак С или согласование.",
    "checklist": "Массовый выбор, bulk-действие или пакетная обработка строк.",
    "close": "Закрытие формы, диалога или панели без дополнительного действия.",
    "content_copy": "Копирование, дублирование записи или перенос настроек по образцу.",
    "delete": "Удаление. Должно применяться только для destructive-действий.",
    "description": "Описание, документ, карточка описания или справочный текст.",
    "design_services": "Настройка конструктора, дизайна формы или пользовательского интерфейса.",
    "directory_sync": "Синхронизация справочника, каталога, файлов или связанных данных.",
    "docs": "Документы, инструкции, регламенты или пакет файлов.",
    "download": "Скачивание файла, экспорт или выгрузка результата.",
    "dynamic_form": "Динамическая форма, форма ввода или настройка формы.",
    "edit": "Редактирование существующей записи.",
    "edit_document": "Редактирование документа, шаблона, текста или печатной формы.",
    "error": "Ошибка, проблема валидации, предупреждение или критичный статус.",
    "event_note": "Событие, запись журнала, протокол или календарная заметка.",
    "experiment": "Экспериментальный режим, тестовая функция или лабораторная проверка.",
    "extension": "Расширение, модуль, плагин или подключаемая функция.",
    "filter_alt": "Фильтр списка, формы или представления.",
    "folder": "Группа, раздел меню, каталог или контейнер объектов.",
    "forms_apps_script": "Скрипт формы, обработчик, пользовательское приложение или связка forms/scripts.",
    "free_cancellation": "Отмена, аннулирование, сброс выбранного действия или безопасный отказ.",
    "help": "Справка, вопрос, неопределенный результат или пояснение НП.",
    "history": "История изменений, журнал действий, аудит или предыдущие версии.",
    "info": "Информационная подсказка, help/dialog без изменения данных.",
    "keyboard_return": "Возврат/закрытие, когда в текущем проекте уже принят такой стиль.",
    "list…82159 tokens truncated…    if not normalized_cell_name:
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
    verified_delivery_evidence = _assert_delivery_evidence(delivery_evidence)
    runtime_gate = _assert_runtime_gate(expected_runtime_fingerprint)
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
    report_validation["kind_matches_report_type"] = (
        report_validation["has_printable_page"]
        if normalized_report_type == "report"
        else report_validation["has_dashboard_page"]
    )
    if not report_validation["kind_matches_report_type"]:
        raise ValueError(
            f"Saved report template kind does not match report_type={normalized_report_type!r}."
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


@mcp.tool()
def alterios_project_health(
    profile: str | None = None,
    project_id: str | None = None,
    refresh: bool = False,
    use_cache: bool = True,
    write_cache: bool = True,
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
        include_processes=include_processes,
        include_report_templates=include_report_templates,
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
