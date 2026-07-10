from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from alterios_mcp.client import (
    AlteriosClient,
    AlteriosConfig,
    AlteriosConfigError,
    AlteriosRequestError,
    encode_filter,
    parse_response_body,
    safe_error,
)
from alterios_mcp.write_control import (
    ControlledWriteError,
    WriteOperation,
    assert_write_allowed,
    build_write_audit,
    collect_target_ids,
)


DEFAULT_PROFILE = "artx"
PROJECT_ID = "4e247a6b-55ef-4665-b88c-3c156fee19ba"
CONTENT_TYPE_NAME = "MCP Practice. Песочница"
CONTENT_TYPE_MARKER = "Codex-managed: alterios-mcp metadata write practice. Safe to modify."
FIELD_PREFIX = "mcp_practice"
VIEW_NAME = "MCP Practice. Список"
ADD_FORM_NAME = "MCP Practice. Добавить запись"
EDIT_FORM_NAME = "MCP Practice. Карточка записи"
MAIN_FORM_NAME = "MCP Practice"
GROUP_NAME = "MCP Practice"
CONTENT_ROW_TITLE = "MCP Practice. Тестовая запись"
OPENID_CONTROL_ROW_TITLE = "MCP Practice. OpenId control row"

SAVE_ICON_ID = "95ec6613-fdcc-4ad5-b93f-16e871b8cbbc"
ADD_ICON_ID = "de3b1bed-27d2-4963-8024-64e7d71d9fb2"
EDIT_ICON_ID = "aa4c573e-104e-46a2-934f-780e105f3b1b"
COMMENT_ENTITY = "any"
COMMENT_TEXT = "MCP Practice comment: comments write/readback coverage."
COMMENTS_BLOCK_TITLE = "Обсуждение"
UPLOAD_FILENAME = "mcp-practice-upload.txt"
UPLOAD_BYTES = b"alterios-mcp file-field upload sandbox\n"
MANUAL_SCRIPT_NAME = "MCP Practice. Manual Script Sandbox"
MANUAL_SCRIPT_MARKER = "Codex-managed: alterios-mcp manual script sandbox."
BPMN_DIAGRAM_NAME = "MCP Practice. BPMN Sandbox"
BPMN_DIAGRAM_MARKER = "Codex-managed: alterios-mcp BPMN/process/task sandbox."
REPORT_NAME = "MCP Practice. Report Sandbox"
REPORT_MARKER = "Codex-managed: alterios-mcp report sandbox."
OPENID_BOUND_REPORT_NAME = "MCP Practice. OpenId Bound Report"
OPENID_BOUND_REPORT_MARKER = "Codex-managed: alterios-mcp openId data-bound report sandbox."
OPENID_REPORT_TAB_NAME = "\u041e\u0442\u0447\u0435\u0442 openId"
OPENID_REPORT_CELL_NAME = "\u041e\u0442\u0447\u0435\u0442 openId"

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
CAMUNDA_NS = "http://camunda.org/schema/1.0/bpmn"


@dataclass(frozen=True)
class Result:
    action: str
    kind: str
    name: str
    id: str | None = None
    details: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"action": self.action, "kind": self.kind, "name": self.name}
        if self.id:
            payload["id"] = self.id
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass(frozen=True)
class FieldSpec:
    suffix: str
    name: str
    field_type: str
    help: str
    tooltip: str
    settings: dict[str, Any]

    @property
    def mname(self) -> str:
        return f"field_{FIELD_PREFIX}_{self.suffix}"

    @property
    def create_mname(self) -> str:
        return self.suffix


FIELD_SPECS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "title",
        "Название",
        "text",
        "Основное название тестовой записи MCP.",
        "Используется как шаблон имени записи и контрольное текстовое поле.",
        {"widget": "text", "required": True, "maxLength": 255, "valueCount": 1, "defaultValue": [None]},
    ),
    FieldSpec(
        "status",
        "Статус",
        "list",
        "Проверяет настройки управляемого списка.",
        "Используется для тестирования одиночного выбора и сохранения enum-значений.",
        {
            "type": "string",
            "values": [
                {"name": "Черновик", "value": "draft"},
                {"name": "Проверяется", "value": "checking"},
                {"name": "Проверено", "value": "checked"},
            ],
            "valueCount": 1,
            "required": False,
            "defaultValue": [None],
        },
    ),
    FieldSpec(
        "score",
        "Оценка",
        "number",
        "Проверяет числовой ввод с ограничением диапазона.",
        "Используется для тестирования min, max и precision.",
        {"min": 0, "max": 100, "precision": 0, "valueCount": 1, "required": False, "defaultValue": [None]},
    ),
    FieldSpec(
        "checked_at",
        "Дата проверки",
        "date",
        "Проверяет календарный ввод.",
        "Используется для тестирования сохранения даты без времени.",
        {
            "min": None,
            "max": None,
            "format": "dd.MM.yyyy",
            "precision": None,
            "granularity": "day",
            "valueCount": 1,
            "required": False,
            "defaultValue": [None],
        },
    ),
    FieldSpec(
        "verified",
        "Проверено",
        "boolean",
        "Проверяет логическое поле.",
        "Используется для тестирования чекбокса/boolean-значения.",
        {"valueCount": 1, "required": False, "defaultValue": [False]},
    ),
    FieldSpec(
        "comment",
        "Комментарий",
        "text",
        "Проверяет многострочный текст.",
        "Используется для тестирования textarea и длинных значений.",
        {"widget": "textarea", "required": False, "maxLength": 2000, "valueCount": 1, "defaultValue": [None]},
    ),
    FieldSpec(
        "attachment",
        "Файл",
        "file",
        "Проверяет загрузку файла в file-field.",
        "Используется для тестирования multipart upload и сохранения file value в content row.",
        {
            "storage": "public",
            "folder": "mcp-practice",
            "extensions": ["txt"],
            "valueCount": 1,
            "required": False,
            "defaultValue": [],
        },
    ),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create or update the ARTX MCP practice chain.")
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="Alterios profile to use.")
    parser.add_argument("--project-id", default=PROJECT_ID, help="Target Alterios workspace id.")
    parser.add_argument("--execute", action="store_true", help="Run writes. Without this flag only a dry-run plan is returned.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args(argv)

    try:
        config = AlteriosConfig.from_env(profile=args.profile).with_project_id(args.project_id)
        client = AlteriosClient(config)
        results, verification = setup_metadata(client, profile=args.profile, project_id=args.project_id, execute=args.execute)
    except (AlteriosConfigError, AlteriosRequestError, ControlledWriteError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    payload = {
        "profile": args.profile,
        "project_id": args.project_id,
        "execute": args.execute,
        "write_enabled": write_enabled(),
        "results": [result.as_dict() for result in results],
        "verification": verification,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for result in results:
            suffix = f" ({result.id})" if result.id else ""
            print(f"{result.action}: {result.kind} {result.name}{suffix}")
        print("verification:")
        for key, value in verification.items():
            print(f"  {key}: {value}")
    return 0


def setup_metadata(
    client: AlteriosClient,
    *,
    profile: str,
    project_id: str,
    execute: bool,
) -> tuple[list[Result], dict[str, Any]]:
    results: list[Result] = []
    content_type = ensure_content_type(client, results, profile=profile, project_id=project_id, execute=execute)
    if not content_type or not content_type.get("_id"):
        results.append(Result("blocked", "fields", "Representative fields", details={"reason": "content type does not exist in dry-run"}))
        return results, verify_metadata(client, None)

    fields = ensure_fields(client, results, content_type["_id"], profile=profile, project_id=project_id, execute=execute)
    content_type = ensure_content_type_template(client, results, content_type, fields, profile=profile, project_id=project_id, execute=execute)
    view = ensure_view(client, results, profile=profile, project_id=project_id, execute=execute)
    if not view or not view.get("_id"):
        results.append(Result("blocked", "ui_chain", "Forms/views/content", details={"reason": "view does not exist in dry-run"}))
        return results, verify_metadata(client, content_type["_id"])

    entity = ensure_view_entity(client, results, view["_id"], content_type["_id"], profile=profile, project_id=project_id, execute=execute)
    if not entity or not entity.get("_id"):
        results.append(Result("blocked", "ui_chain", "Forms/views/content", details={"reason": "view entity does not exist in dry-run"}))
        return results, verify_metadata(client, content_type["_id"])

    view_fields = ensure_view_fields(client, results, view["_id"], entity["_id"], fields, profile=profile, project_id=project_id, execute=execute)
    report = ensure_report(client, results, view["_id"], view_fields, profile=profile, project_id=project_id, execute=execute)
    openid_report = ensure_openid_bound_report(client, results, view["_id"], view_fields, profile=profile, project_id=project_id, execute=execute)
    add_form = ensure_form(
        client,
        results,
        ADD_FORM_NAME,
        build_add_form(content_type["_id"], fields),
        profile=profile,
        project_id=project_id,
        execute=execute,
    )
    edit_form = ensure_form(
        client,
        results,
        EDIT_FORM_NAME,
        build_edit_form(view["_id"], view_fields, report_id=(openid_report or report or {}).get("_id")),
        profile=profile,
        project_id=project_id,
        execute=execute,
    )
    if not add_form or not add_form.get("_id") or not edit_form or not edit_form.get("_id"):
        results.append(Result("blocked", "ui_chain", "Main form/group/content", details={"reason": "add/edit forms do not exist in dry-run"}))
        return results, verify_metadata(client, content_type["_id"])

    main_form = ensure_form(
        client,
        results,
        MAIN_FORM_NAME,
        build_main_form(
            view["_id"],
            entity["_id"],
            add_form["_id"],
            edit_form["_id"],
            view_fields,
            report_id=report.get("_id") if report else None,
        ),
        profile=profile,
        project_id=project_id,
        execute=execute,
    )
    if not main_form or not main_form.get("_id"):
        results.append(Result("blocked", "ui_chain", "Group/content", details={"reason": "main form does not exist in dry-run"}))
        return results, verify_metadata(client, content_type["_id"])

    ensure_group(client, results, main_form["_id"], profile=profile, project_id=project_id, execute=execute)
    content = ensure_practice_content(client, results, content_type["_id"], fields, profile=profile, project_id=project_id, execute=execute)
    ensure_openid_control_content(client, results, content_type["_id"], fields, profile=profile, project_id=project_id, execute=execute)
    if content and content.get("_id"):
        ensure_practice_comment(client, results, content["_id"], profile=profile, project_id=project_id, execute=execute)
        ensure_file_upload(client, results, content_type["_id"], fields, content, profile=profile, project_id=project_id, execute=execute)
        manual_script = ensure_manual_script(client, results, profile=profile, project_id=project_id, execute=execute)
        if manual_script and manual_script.get("_id"):
            execute_manual_script(client, results, manual_script["_id"], content["_id"], profile=profile, project_id=project_id, execute=execute)
        else:
            results.append(Result("blocked", "manual_script_execution", MANUAL_SCRIPT_NAME, details={"reason": "manual script does not exist in dry-run"}))
        diagram = ensure_bpmn_diagram(
            client,
            results,
            content_type["_id"],
            edit_form["_id"],
            profile=profile,
            project_id=project_id,
            execute=execute,
        )
        if diagram and diagram.get("_id"):
            ensure_process_task_side_effect(client, results, diagram["_id"], content["_id"], profile=profile, project_id=project_id, execute=execute)
        else:
            results.append(Result("blocked", "process_task", BPMN_DIAGRAM_NAME, details={"reason": "diagram does not exist in dry-run"}))
    else:
        results.append(Result("blocked", "comment", COMMENT_TEXT, details={"reason": "content row does not exist in dry-run"}))
    return results, verify_metadata(client, content_type["_id"])


def ensure_content_type(
    client: AlteriosClient,
    results: list[Result],
    *,
    profile: str,
    project_id: str,
    execute: bool,
) -> dict[str, Any] | None:
    existing = find_named(list_content_types(client), CONTENT_TYPE_NAME)
    payload = {
        "name": CONTENT_TYPE_NAME,
        "settings": {"maxRefDepth": 0},
        "description": CONTENT_TYPE_MARKER,
        "share": False,
        "shareCreating": False,
        "shareEditing": False,
        "shareDeleting": False,
        "fieldNamePrefix": FIELD_PREFIX,
    }

    if existing:
        if CONTENT_TYPE_MARKER not in str(existing.get("description") or ""):
            raise RuntimeError(f"Content type {CONTENT_TYPE_NAME!r} exists but is not Codex-managed; refusing to update it.")
        needs_update = any(existing.get(key) != value for key, value in payload.items())
        if not needs_update:
            results.append(Result("exists", "content_type", CONTENT_TYPE_NAME, existing["_id"]))
            return existing
        updated = strip_metadata({**existing, **payload})
        saved = write_rest(client, "POST", "/api/content-types/save", updated, profile=profile, project_id=project_id, execute=execute)
        if not execute:
            results.append(Result("planned", "content_type", CONTENT_TYPE_NAME, existing["_id"]))
            return existing
        result = saved if isinstance(saved, dict) else {**existing, **payload}
        results.append(Result("updated", "content_type", CONTENT_TYPE_NAME, existing["_id"]))
        return result

    write_rest(client, "POST", "/api/content-types/save", payload, profile=profile, project_id=project_id, execute=execute)
    if not execute:
        results.append(Result("planned", "content_type", CONTENT_TYPE_NAME))
        return None

    refreshed = find_named(list_content_types(client), CONTENT_TYPE_NAME)
    if not refreshed or not refreshed.get("_id"):
        raise RuntimeError(f"Create content type {CONTENT_TYPE_NAME!r} was not visible on readback.")
    results.append(Result("created", "content_type", CONTENT_TYPE_NAME, refreshed["_id"]))
    return refreshed


def ensure_content_type_template(
    client: AlteriosClient,
    results: list[Result],
    content_type: dict[str, Any],
    fields: list[dict[str, Any]],
    *,
    profile: str,
    project_id: str,
    execute: bool,
) -> dict[str, Any]:
    title_spec = FIELD_SPECS[0]
    title_field = next((field for field in fields if field.get("name") == title_spec.name or mname_matches(field, title_spec)), None)
    if not title_field:
        return content_type
    expected_template = f"{{{{{title_field['mname']}}}}}"
    if content_type.get("contentNameTemplate") == expected_template:
        results.append(Result("exists", "content_type_template", CONTENT_TYPE_NAME, content_type["_id"]))
        return content_type
    payload = strip_metadata({**content_type, "contentNameTemplate": expected_template})
    saved = write_rest(client, "POST", "/api/content-types/save", payload, profile=profile, project_id=project_id, execute=execute)
    if not execute:
        results.append(Result("planned", "content_type_template", CONTENT_TYPE_NAME, content_type["_id"]))
        return content_type
    results.append(Result("updated", "content_type_template", CONTENT_TYPE_NAME, content_type["_id"]))
    return saved if isinstance(saved, dict) else {**content_type, "contentNameTemplate": expected_template}


def ensure_fields(
    client: AlteriosClient,
    results: list[Result],
    content_type_id: str,
    *,
    profile: str,
    project_id: str,
    execute: bool,
) -> list[dict[str, Any]]:
    existing_fields = list_fields(client, content_type_id)
    ensured: list[dict[str, Any]] = []
    for order, spec in enumerate(FIELD_SPECS):
        payload = field_payload(spec, content_type_id, order)
        existing = next((field for field in existing_fields if mname_matches(field, spec) or field.get("name") == spec.name), None)
        if existing:
            if not needs_field_update(existing, payload, spec):
                results.append(Result("exists", "field", spec.name, existing["_id"], {"mname": existing.get("mname"), "type": existing.get("type")}))
                ensured.append(existing)
                continue
            updated = strip_metadata({**existing, **payload, "mname": existing.get("mname") or spec.mname})
            saved = write_rest(client, "POST", "/api/fields/save", updated, profile=profile, project_id=project_id, execute=execute)
            if not execute:
                results.append(Result("planned", "field", spec.name, existing["_id"], {"mname": spec.mname, "type": spec.field_type}))
                ensured.append(existing)
                continue
            result = saved if isinstance(saved, dict) else {**existing, **payload, "mname": spec.mname}
            results.append(Result("updated", "field", spec.name, existing["_id"], {"mname": result.get("mname"), "type": result.get("type")}))
            ensured.append(result)
            continue

        write_rest(client, "POST", "/api/fields/save", payload, profile=profile, project_id=project_id, execute=execute)
        if not execute:
            results.append(Result("planned", "field", spec.name, details={"mname": spec.mname, "type": spec.field_type}))
            ensured.append({**payload, "_id": f"dry-run-{spec.suffix}", "mname": spec.mname})
            continue
        refreshed = list_fields(client, content_type_id)
        created = next((field for field in refreshed if mname_matches(field, spec) or field.get("name") == spec.name), None)
        if not created or not created.get("_id"):
            raise RuntimeError(f"Create field {spec.name!r} was not visible on readback.")
        results.append(Result("created", "field", spec.name, created["_id"], {"mname": created.get("mname"), "type": created.get("type")}))
        ensured.append(created)
        existing_fields.append(created)
    return ensured


def field_payload(spec: FieldSpec, content_type_id: str, order: int) -> dict[str, Any]:
    return {
        "name": spec.name,
        "mname": spec.create_mname,
        "type": spec.field_type,
        "contentTypeId": content_type_id,
        "order": order,
        "help": spec.help,
        "tooltip": spec.tooltip,
        "description": f"{spec.field_type}: {spec.help} {spec.tooltip}",
        "required": False,
        "defaultValue": [],
        "formDisplay": {},
        "settings": spec.settings,
    }


def needs_field_update(existing: dict[str, Any], payload: dict[str, Any], spec: FieldSpec) -> bool:
    expected = {key: value for key, value in payload.items() if key not in {"mname", "order"}}
    return any(existing.get(key) != value for key, value in expected.items()) or not mname_matches(existing, spec)


def mname_matches(field: dict[str, Any], spec: FieldSpec) -> bool:
    actual = str(field.get("mname") or "")
    generated_tail = f"{FIELD_PREFIX}_{spec.suffix}"
    return (
        actual == spec.mname
        or actual == generated_tail
        or actual.endswith(f"_{generated_tail}")
        or actual.endswith(f"__{generated_tail}")
    )


def ensure_view(
    client: AlteriosClient,
    results: list[Result],
    *,
    profile: str,
    project_id: str,
    execute: bool,
) -> dict[str, Any] | None:
    existing = find_named(list_views(client), VIEW_NAME)
    payload = {
        "name": VIEW_NAME,
        "description": CONTENT_TYPE_MARKER,
        "format": "table",
        "settings": {"engineVersion": "v2"},
        "strict": False,
    }
    if existing:
        ensure_codex_managed("View", VIEW_NAME, existing)
        if not resource_needs_update(existing, payload, ("description", "format", "settings", "strict")):
            results.append(Result("exists", "view", VIEW_NAME, existing["_id"]))
            return existing
        updated = strip_metadata({**existing, **payload})
        saved = update_resource(client, "views", updated, profile=profile, project_id=project_id, execute=execute)
        if not execute:
            results.append(Result("planned", "view", VIEW_NAME, existing["_id"]))
            return existing
        results.append(Result("updated", "view", VIEW_NAME, existing["_id"]))
        return saved if isinstance(saved, dict) else updated

    write_rest(client, "POST", "/api/views", payload, profile=profile, project_id=project_id, execute=execute)
    if not execute:
        results.append(Result("planned", "view", VIEW_NAME))
        return None
    refreshed = find_named(list_views(client), VIEW_NAME)
    if not refreshed or not refreshed.get("_id"):
        raise RuntimeError(f"Create view {VIEW_NAME!r} was not visible on readback.")
    results.append(Result("created", "view", VIEW_NAME, refreshed["_id"]))
    return refreshed


def ensure_view_entity(
    client: AlteriosClient,
    results: list[Result],
    view_id: str,
    content_type_id: str,
    *,
    profile: str,
    project_id: str,
    execute: bool,
) -> dict[str, Any] | None:
    entities = list_view_entities(client, view_id)
    existing = next(
        (
            entity
            for entity in entities
            if entity.get("name") == CONTENT_TYPE_NAME
            and entity.get("type") == "content"
            and content_type_id in (entity.get("config") or {}).get("contentTypesIds", [])
        ),
        None,
    )
    payload = {
        "name": CONTENT_TYPE_NAME,
        "type": "content",
        "viewId": view_id,
        "config": {"main": True, "position": {"x": -260, "y": -180}, "contentTypesIds": [content_type_id]},
        "joins": [],
    }
    if existing:
        if not resource_needs_update(existing, payload, ("name", "type", "viewId", "config", "joins")):
            results.append(Result("exists", "view_entity", CONTENT_TYPE_NAME, existing["_id"]))
            return existing
        updated = strip_metadata({**existing, **payload})
        saved = update_resource(client, "view-entities", updated, profile=profile, project_id=project_id, execute=execute)
        if not execute:
            results.append(Result("planned", "view_entity", CONTENT_TYPE_NAME, existing["_id"]))
            return existing
        results.append(Result("updated", "view_entity", CONTENT_TYPE_NAME, existing["_id"]))
        return saved if isinstance(saved, dict) else updated

    write_rest(client, "POST", "/api/view-entities", payload, profile=profile, project_id=project_id, execute=execute)
    if not execute:
        results.append(Result("planned", "view_entity", CONTENT_TYPE_NAME))
        return None
    refreshed = list_view_entities(client, view_id)
    created = next((entity for entity in refreshed if entity.get("name") == CONTENT_TYPE_NAME and entity.get("type") == "content"), None)
    if not created or not created.get("_id"):
        raise RuntimeError(f"Create view entity {CONTENT_TYPE_NAME!r} was not visible on readback.")
    results.append(Result("created", "view_entity", CONTENT_TYPE_NAME, created["_id"]))
    return created


def ensure_view_fields(
    client: AlteriosClient,
    results: list[Result],
    view_id: str,
    entity_id: str,
    fields: list[dict[str, Any]],
    *,
    profile: str,
    project_id: str,
    execute: bool,
) -> dict[str, dict[str, Any]]:
    existing_fields = list_view_fields(client, view_id)
    ensured: dict[str, dict[str, Any]] = {}
    id_field = next((field for field in existing_fields if field.get("entityId") == entity_id and field.get("mname") == "_id"), None)
    if not id_field:
        write_rest(
            client,
            "POST",
            "/api/view-entities/add-one-field",
            {"entityId": entity_id, "attribute": "_id"},
            profile=profile,
            project_id=project_id,
            execute=execute,
        )
        if execute:
            id_field = next(
                (
                    field
                    for field in list_view_fields(client, view_id)
                    if field.get("entityId") == entity_id and field.get("mname") == "_id"
                ),
                None,
            )
            if not id_field:
                raise RuntimeError("Create _id view field was not visible on readback.")
            results.append(Result("created", "view_field", "ID", id_field.get("_id", "_id")))
        else:
            results.append(Result("planned", "view_field", "ID"))
    else:
        results.append(Result("exists", "view_field", "ID", id_field.get("_id", "_id")))
    if id_field:
        ensured["_id"] = id_field

    for order, field in enumerate(fields, start=1):
        existing = next(
            (
                item
                for item in existing_fields
                if item.get("entityId") == entity_id and item.get("contentTypeFieldId") == field.get("_id")
            ),
            None,
        )
        if not existing:
            write_rest(
                client,
                "POST",
                "/api/view-entities/add-one-field",
                {"entityId": entity_id, "contentTypeFieldId": field["_id"]},
                profile=profile,
                project_id=project_id,
                execute=execute,
            )
            if not execute:
                results.append(Result("planned", "view_field", field["name"], details={"contentTypeFieldId": field["_id"]}))
                continue
            refreshed = list_view_fields(client, view_id)
            existing = next(
                (
                    item
                    for item in refreshed
                    if item.get("entityId") == entity_id and item.get("contentTypeFieldId") == field.get("_id")
                ),
                None,
            )
            if not existing:
                raise RuntimeError(f"Create view field {field['name']!r} was not visible on readback.")
            existing_fields.append(existing)
            results.append(Result("created", "view_field", field["name"], existing.get("_id", field["_id"])))
        else:
            results.append(Result("exists", "view_field", field["name"], existing.get("_id", field["_id"])))

        expected_mname = view_mname(field["mname"])
        if existing.get("mname") != expected_mname or existing.get("alias") != field["name"] or existing.get("order") != order:
            updated = view_field_save_payload({**existing, "mname": expected_mname, "alias": field["name"], "order": order})
            saved = write_rest(client, "POST", "/api/view-fields/save", updated, profile=profile, project_id=project_id, execute=execute)
            if not execute:
                results.append(Result("planned", "view_field_config", field["name"], existing.get("_id")))
            else:
                existing = saved if isinstance(saved, dict) else {**existing, **updated}
                results.append(Result("updated", "view_field_config", field["name"], existing.get("_id", field["_id"])))
        ensured[field["mname"]] = existing
    return ensured


def ensure_form(
    client: AlteriosClient,
    results: list[Result],
    name: str,
    payload: dict[str, Any],
    *,
    profile: str,
    project_id: str,
    execute: bool,
) -> dict[str, Any] | None:
    existing = find_named(list_forms(client), name)
    payload = dict(payload)
    payload["description"] = CONTENT_TYPE_MARKER
    if existing:
        ensure_codex_managed("Form", name, existing)
        updated = strip_metadata({**existing, **payload})
        if not resource_needs_update(existing, payload, ("description", "pageTitle", "tabs", "formActionContainers")):
            results.append(Result("exists", "form", name, existing["_id"]))
            return existing
        saved = update_resource(client, "forms", updated, profile=profile, project_id=project_id, execute=execute)
        if not execute:
            results.append(Result("planned", "form", name, existing["_id"]))
            return existing
        results.append(Result("updated", "form", name, existing["_id"]))
        return saved if isinstance(saved, dict) else updated

    write_rest(client, "POST", "/api/forms", payload, profile=profile, project_id=project_id, execute=execute)
    if not execute:
        results.append(Result("planned", "form", name))
        return None
    refreshed = find_named(list_forms(client), name)
    if not refreshed or not refreshed.get("_id"):
        raise RuntimeError(f"Create form {name!r} was not visible on readback.")
    results.append(Result("created", "form", name, refreshed["_id"]))
    return refreshed


def ensure_group(
    client: AlteriosClient,
    results: list[Result],
    form_id: str,
    *,
    profile: str,
    project_id: str,
    execute: bool,
) -> dict[str, Any] | None:
    groups = list_groups(client)
    existing = next((group for group in groups if group.get("name") == GROUP_NAME and not group.get("root")), None)
    root = next((group for group in groups if group.get("root") or group.get("name") == "root"), None)
    if not root:
        raise RuntimeError("Root group was not found.")
    payload = {
        "name": GROUP_NAME,
        "description": CONTENT_TYPE_MARKER,
        "publish": True,
        "parentGroupId": root["_id"],
        "root": False,
        "children": [],
        "order": None,
        "formId": form_id,
        "iconId": None,
    }
    if existing:
        ensure_codex_managed("Group", GROUP_NAME, existing)
        updated = strip_metadata({**existing, **payload})
        if not resource_needs_update(existing, payload, ("description", "publish", "parentGroupId", "root", "formId", "iconId")):
            results.append(Result("exists", "group", GROUP_NAME, existing["_id"]))
            return existing
        saved = update_resource(client, "groups", updated, profile=profile, project_id=project_id, execute=execute)
        if not execute:
            results.append(Result("planned", "group", GROUP_NAME, existing["_id"]))
            return existing
        results.append(Result("updated", "group", GROUP_NAME, existing["_id"]))
        return saved if isinstance(saved, dict) else updated

    write_rest(client, "POST", "/api/groups", payload, profile=profile, project_id=project_id, execute=execute)
    if not execute:
        results.append(Result("planned", "group", GROUP_NAME))
        return None
    refreshed = next((group for group in list_groups(client) if group.get("name") == GROUP_NAME and not group.get("root")), None)
    if not refreshed or not refreshed.get("_id"):
        raise RuntimeError(f"Create group {GROUP_NAME!r} was not visible on readback.")
    results.append(Result("created", "group", GROUP_NAME, refreshed["_id"]))
    return refreshed


def ensure_practice_content(
    client: AlteriosClient,
    results: list[Result],
    content_type_id: str,
    fields: list[dict[str, Any]],
    *,
    profile: str,
    project_id: str,
    execute: bool,
) -> dict[str, Any] | None:
    field_mnames = field_mnames_by_suffix(fields)
    rows = list_content_rows(client, content_type_id, limit=500)
    existing = next((row for row in rows if first((row.get("fields") or {}).get(field_mnames["title"])) == CONTENT_ROW_TITLE), None)
    payload_fields = {
        field_mnames["title"]: [CONTENT_ROW_TITLE],
        field_mnames["status"]: ["checked"],
        field_mnames["score"]: [87],
        field_mnames["checked_at"]: ["2026-07-10"],
        field_mnames["verified"]: [True],
        field_mnames["comment"]: ["Создано alterios-mcp practice chain: metadata -> form -> view -> content."],
    }
    if existing:
        updated = dict(existing)
        updated["fields"] = dict(existing.get("fields") or {})
        if all(updated["fields"].get(key) == value for key, value in payload_fields.items()):
            results.append(Result("exists", "content", CONTENT_ROW_TITLE, existing["_id"]))
            return existing
        updated["fields"].update(payload_fields)
        payload = content_save_payload(updated)
        saved = write_rest(client, "PATCH", "/api/contents/save", payload, profile=profile, project_id=project_id, execute=execute)
        if not execute:
            results.append(Result("planned", "content", CONTENT_ROW_TITLE, existing["_id"]))
            return existing
        results.append(Result("updated", "content", CONTENT_ROW_TITLE, existing["_id"]))
        return saved if isinstance(saved, dict) else updated

    payload = {"contentTypeId": content_type_id, "fields": payload_fields}
    write_rest(client, "POST", "/api/contents/save", payload, profile=profile, project_id=project_id, execute=execute)
    if not execute:
        results.append(Result("planned", "content", CONTENT_ROW_TITLE))
        return None
    refreshed_rows = list_content_rows(client, content_type_id, limit=500)
    created = next((row for row in refreshed_rows if first((row.get("fields") or {}).get(field_mnames["title"])) == CONTENT_ROW_TITLE), None)
    if not created or not created.get("_id"):
        raise RuntimeError(f"Create content {CONTENT_ROW_TITLE!r} was not visible on readback.")
    results.append(Result("created", "content", CONTENT_ROW_TITLE, created["_id"]))
    return created


def ensure_openid_control_content(
    client: AlteriosClient,
    results: list[Result],
    content_type_id: str,
    fields: list[dict[str, Any]],
    *,
    profile: str,
    project_id: str,
    execute: bool,
) -> dict[str, Any] | None:
    field_mnames = field_mnames_by_suffix(fields)
    rows = list_content_rows(client, content_type_id, limit=500)
    existing = next((row for row in rows if first((row.get("fields") or {}).get(field_mnames["title"])) == OPENID_CONTROL_ROW_TITLE), None)
    payload_fields = {
        field_mnames["title"]: [OPENID_CONTROL_ROW_TITLE],
        field_mnames["status"]: ["draft"],
        field_mnames["score"]: [13],
        field_mnames["checked_at"]: ["2026-07-10"],
        field_mnames["verified"]: [False],
        field_mnames["comment"]: ["OpenId context control row for embedded report and view-data checks."],
    }
    if existing:
        updated = dict(existing)
        updated["fields"] = dict(existing.get("fields") or {})
        if all(updated["fields"].get(key) == value for key, value in payload_fields.items()):
            results.append(Result("exists", "content", OPENID_CONTROL_ROW_TITLE, existing["_id"]))
            return existing
        updated["fields"].update(payload_fields)
        payload = content_save_payload(updated)
        saved = write_rest(client, "PATCH", "/api/contents/save", payload, profile=profile, project_id=project_id, execute=execute)
        if not execute:
            results.append(Result("planned", "content", OPENID_CONTROL_ROW_TITLE, existing["_id"]))
            return existing
        results.append(Result("updated", "content", OPENID_CONTROL_ROW_TITLE, existing["_id"]))
        return saved if isinstance(saved, dict) else updated

    payload = {"contentTypeId": content_type_id, "fields": payload_fields}
    write_rest(client, "POST", "/api/contents/save", payload, profile=profile, project_id=project_id, execute=execute)
    if not execute:
        results.append(Result("planned", "content", OPENID_CONTROL_ROW_TITLE))
        return None
    refreshed_rows = list_content_rows(client, content_type_id, limit=500)
    created = next((row for row in refreshed_rows if first((row.get("fields") or {}).get(field_mnames["title"])) == OPENID_CONTROL_ROW_TITLE), None)
    if not created or not created.get("_id"):
        raise RuntimeError(f"Create content {OPENID_CONTROL_ROW_TITLE!r} was not visible on readback.")
    results.append(Result("created", "content", OPENID_CONTROL_ROW_TITLE, created["_id"]))
    return created


def ensure_practice_comment(
    client: AlteriosClient,
    results: list[Result],
    content_id: str,
    *,
    profile: str,
    project_id: str,
    execute: bool,
) -> dict[str, Any] | None:
    comments = list_comments(client, content_id, entity=COMMENT_ENTITY)
    existing = find_comment_by_body(comments, COMMENT_TEXT)
    details = {"entity": COMMENT_ENTITY, "entityId": content_id}
    if existing:
        results.append(Result("exists", "comment", COMMENT_TEXT, existing.get("_id"), details))
        return existing

    payload = {"entity": COMMENT_ENTITY, "entityId": content_id, "body": COMMENT_TEXT}
    write_rest(client, "POST", "/api/v1/comments", payload, profile=profile, project_id=project_id, execute=execute)
    if not execute:
        results.append(Result("planned", "comment", COMMENT_TEXT, details=details))
        return None

    refreshed = find_comment_by_body(list_comments(client, content_id, entity=COMMENT_ENTITY), COMMENT_TEXT)
    if not refreshed or not refreshed.get("_id"):
        raise RuntimeError("Create practice comment was not visible on comments readback.")
    results.append(Result("created", "comment", COMMENT_TEXT, refreshed["_id"], details))
    return refreshed


def ensure_file_upload(
    client: AlteriosClient,
    results: list[Result],
    content_type_id: str,
    fields: list[dict[str, Any]],
    content: dict[str, Any],
    *,
    profile: str,
    project_id: str,
    execute: bool,
) -> dict[str, Any] | None:
    file_field = field_by_suffix(fields, "attachment")
    values = normalize_file_values((content.get("fields") or {}).get(file_field["mname"]))
    existing = find_uploaded_value(client, values, UPLOAD_FILENAME)
    if existing:
        results.append(
            Result(
                "exists",
                "file_upload",
                UPLOAD_FILENAME,
                file_value_id(existing),
                {"field": file_field["mname"], "filename": UPLOAD_FILENAME},
            )
        )
        return existing

    if not execute:
        audit_file_upload(profile=profile, project_id=project_id, content_type_id=content_type_id, field_id=file_field["_id"], execute=False)
        results.append(Result("planned", "file_upload", UPLOAD_FILENAME, details={"field": file_field["mname"]}))
        return None

    uploaded = upload_multipart(
        client,
        UPLOAD_BYTES,
        {
            "filename": UPLOAD_FILENAME,
            "mimeType": "text/plain",
            "size": len(UPLOAD_BYTES),
        },
        content_type_id,
        file_field["_id"],
        profile=profile,
        project_id=project_id,
        execute=execute,
    )
    uploaded_id = uploaded.get("_id") if isinstance(uploaded, dict) else None
    if not uploaded_id:
        raise RuntimeError(f"POST /api/file/upload/field returned no _id: {safe_error(uploaded)}")

    uploaded_value = {
        "id": uploaded_id,
        "filename": uploaded.get("filename") or UPLOAD_FILENAME,
        "name": uploaded.get("filename") or UPLOAD_FILENAME,
        "mimeType": uploaded.get("mimeType") or "text/plain",
        "size": uploaded.get("size") or len(UPLOAD_BYTES),
    }
    updated = dict(content)
    updated["fields"] = dict(content.get("fields") or {})
    updated["fields"][file_field["mname"]] = [uploaded_value]
    write_rest(
        client,
        "PATCH",
        "/api/contents/save",
        content_save_payload(updated),
        profile=profile,
        project_id=project_id,
        execute=execute,
    )
    metadata = list_file_metadata(client, [uploaded_id])
    if not metadata:
        raise RuntimeError(f"Uploaded file {uploaded_id} was not visible through /api/file/list.")
    results.append(
        Result(
            "created",
            "file_upload",
            UPLOAD_FILENAME,
            uploaded_id,
            {"field": file_field["mname"], "size": len(UPLOAD_BYTES), "metadata_found": True},
        )
    )
    return uploaded_value


def ensure_manual_script(
    client: AlteriosClient,
    results: list[Result],
    *,
    profile: str,
    project_id: str,
    execute: bool,
) -> dict[str, Any] | None:
    body = build_manual_script_body()
    payload = {
        "name": MANUAL_SCRIPT_NAME,
        "description": MANUAL_SCRIPT_MARKER,
        "type": "manual",
        "active": True,
        "body": body,
        "share": False,
        "apiKey": client.config.api_token,
        "config": {"cron": None, "arguments": [{"key": "contentId"}, {"key": "source"}, {"key": "mode"}]},
        "librariesIds": [],
    }
    existing = find_named(list_scripts(client), MANUAL_SCRIPT_NAME)
    if existing:
        ensure_marked("Script", MANUAL_SCRIPT_NAME, existing, MANUAL_SCRIPT_MARKER)
        comparable_keys = ("description", "type", "active", "body", "share", "config", "librariesIds")
        if not resource_needs_update(existing, payload, comparable_keys):
            results.append(Result("exists", "manual_script", MANUAL_SCRIPT_NAME, existing["_id"]))
            return existing
        updated = {**strip_metadata(existing), **payload, "_id": existing["_id"]}
        saved = write_rest(client, "PUT", "/api/scripts", updated, profile=profile, project_id=project_id, execute=execute)
        if not execute:
            results.append(Result("planned", "manual_script", MANUAL_SCRIPT_NAME, existing["_id"]))
            return existing
        results.append(Result("updated", "manual_script", MANUAL_SCRIPT_NAME, existing["_id"]))
        return saved if isinstance(saved, dict) else updated

    write_rest(client, "POST", "/api/scripts", payload, profile=profile, project_id=project_id, execute=execute)
    if not execute:
        results.append(Result("planned", "manual_script", MANUAL_SCRIPT_NAME))
        return None
    refreshed = find_named(list_scripts(client), MANUAL_SCRIPT_NAME)
    if not refreshed or not refreshed.get("_id"):
        raise RuntimeError(f"Create script {MANUAL_SCRIPT_NAME!r} was not visible on readback.")
    results.append(Result("created", "manual_script", MANUAL_SCRIPT_NAME, refreshed["_id"]))
    return refreshed


def execute_manual_script(
    client: AlteriosClient,
    results: list[Result],
    script_id: str,
    content_id: str,
    *,
    profile: str,
    project_id: str,
    execute: bool,
) -> Any:
    payload = {"_id": script_id, "args": {"contentId": content_id, "source": "alterios-mcp", "mode": "sandbox"}}
    response = write_rest(
        client,
        "POST",
        "/api/scripts/execute-manual",
        payload,
        profile=profile,
        project_id=project_id,
        execute=execute,
        risk_level="manual_script",
    )
    if not execute:
        results.append(Result("planned", "manual_script_execution", MANUAL_SCRIPT_NAME, script_id, {"contentId": content_id}))
        return None
    results.append(
        Result(
            "executed",
            "manual_script_execution",
            MANUAL_SCRIPT_NAME,
            script_id,
            {"contentId": content_id, "response_shape": response_shape(response)},
        )
    )
    return response


def ensure_bpmn_diagram(
    client: AlteriosClient,
    results: list[Result],
    content_type_id: str,
    task_form_id: str,
    *,
    profile: str,
    project_id: str,
    execute: bool,
) -> dict[str, Any] | None:
    xml = build_process_xml(task_form_id)
    payload = {
        "name": BPMN_DIAGRAM_NAME,
        "description": BPMN_DIAGRAM_MARKER,
        "value": xml,
        "contentTypeId": content_type_id,
        "createOnStart": False,
        "delayedStart": False,
    }
    existing = find_named(list_diagrams(client), BPMN_DIAGRAM_NAME)
    if existing:
        ensure_marked("Diagram", BPMN_DIAGRAM_NAME, existing, BPMN_DIAGRAM_MARKER)
        if not resource_needs_update(existing, payload, ("description", "value", "contentTypeId", "createOnStart", "delayedStart")):
            results.append(Result("exists", "diagram", BPMN_DIAGRAM_NAME, existing["_id"]))
            return existing
        updated = strip_metadata({**existing, **payload})
        saved = update_resource(client, "diagrams", updated, profile=profile, project_id=project_id, execute=execute)
        if not execute:
            results.append(Result("planned", "diagram", BPMN_DIAGRAM_NAME, existing["_id"]))
            return existing
        results.append(Result("updated", "diagram", BPMN_DIAGRAM_NAME, existing["_id"]))
        return saved if isinstance(saved, dict) else updated

    write_rest(client, "POST", "/api/diagrams", payload, profile=profile, project_id=project_id, execute=execute)
    if not execute:
        results.append(Result("planned", "diagram", BPMN_DIAGRAM_NAME))
        return None
    refreshed = find_named(list_diagrams(client), BPMN_DIAGRAM_NAME)
    if not refreshed or not refreshed.get("_id"):
        raise RuntimeError(f"Create diagram {BPMN_DIAGRAM_NAME!r} was not visible on readback.")
    results.append(Result("created", "diagram", BPMN_DIAGRAM_NAME, refreshed["_id"]))
    return refreshed


def ensure_process_task_side_effect(
    client: AlteriosClient,
    results: list[Result],
    diagram_id: str,
    content_id: str,
    *,
    profile: str,
    project_id: str,
    execute: bool,
) -> dict[str, Any] | None:
    processes = list_processes(client, diagram_id=diagram_id, content_id=content_id)
    completed = next((process for process in processes if process.get("completed") and not process.get("error")), None)
    if completed:
        results.append(Result("exists", "process_task", BPMN_DIAGRAM_NAME, completed.get("_id"), {"completed": True, "contentId": content_id}))
        return completed

    active_tasks = active_tasks_for_processes(client, processes, diagram_id=diagram_id, content_id=content_id)
    if not active_tasks and not processes:
        payload = {"diagramId": diagram_id, "contentId": content_id, "params": {"source": "alterios-mcp", "sandbox": True}}
        start_response = write_rest(
            client,
            "POST",
            "/api/processes",
            payload,
            profile=profile,
            project_id=project_id,
            execute=execute,
            risk_level="workflow_side_effect",
        )
        if not execute:
            results.append(Result("planned", "process_start", BPMN_DIAGRAM_NAME, diagram_id, {"contentId": content_id}))
            return None
        process_id = process_id_from_response(start_response)
        active_tasks = wait_for_tasks(client, diagram_id=diagram_id, content_id=content_id, process_id=process_id)
        processes = list_processes(client, diagram_id=diagram_id, content_id=content_id)
        results.append(Result("started", "process", BPMN_DIAGRAM_NAME, process_id or (processes[0].get("_id") if processes else None), {"contentId": content_id}))

    task = active_tasks[0] if active_tasks else None
    if task and task.get("_id"):
        response = write_rest(
            client,
            "DELETE",
            "/api/tasks/complete",
            {"_id": task["_id"], "nextFlowId": "Flow_to_end", "processContent": None, "contents": []},
            profile=profile,
            project_id=project_id,
            execute=execute,
            risk_level="workflow_side_effect",
        )
        if not execute:
            results.append(Result("planned", "task_complete", task.get("name") or "MCP Practice task", task["_id"]))
            return None
        completed_process = wait_for_completed_process(client, diagram_id=diagram_id, content_id=content_id)
        results.append(
            Result(
                "completed",
                "task",
                task.get("name") or "MCP Practice task",
                task["_id"],
                {"processId": (completed_process or {}).get("_id"), "response_shape": response_shape(response)},
            )
        )
        return completed_process

    latest = processes[0] if processes else None
    results.append(
        Result(
            "blocked",
            "process_task",
            BPMN_DIAGRAM_NAME,
            latest.get("_id") if latest else None,
            {"reason": "process exists but no active task or completed process was found", "contentId": content_id},
        )
    )
    return latest


def ensure_report(
    client: AlteriosClient,
    results: list[Result],
    view_id: str,
    view_fields: dict[str, dict[str, Any]],
    *,
    profile: str,
    project_id: str,
    execute: bool,
) -> dict[str, Any] | None:
    template = build_dashboard_template(client.config.base_url, view_id, view_fields)
    return ensure_dashboard_report(
        client,
        results,
        name=REPORT_NAME,
        marker=REPORT_MARKER,
        template=template,
        profile=profile,
        project_id=project_id,
        execute=execute,
    )


def ensure_openid_bound_report(
    client: AlteriosClient,
    results: list[Result],
    view_id: str,
    view_fields: dict[str, dict[str, Any]],
    *,
    profile: str,
    project_id: str,
    execute: bool,
) -> dict[str, Any] | None:
    title_column = dashboard_column_name(view_fields, "title")
    template = build_openid_bound_dashboard_template(client.config.base_url, view_id, view_fields)
    return ensure_dashboard_report(
        client,
        results,
        name=OPENID_BOUND_REPORT_NAME,
        marker=OPENID_BOUND_REPORT_MARKER,
        template=template,
        required_texts=(title_column, "OpenIdCurrentRowTitle"),
        profile=profile,
        project_id=project_id,
        execute=execute,
    )


def ensure_dashboard_report(
    client: AlteriosClient,
    results: list[Result],
    *,
    name: str,
    marker: str,
    template: str,
    profile: str,
    project_id: str,
    execute: bool,
    required_texts: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    payload = {"name": name, "description": marker, "type": "dashboard", "template": template}
    existing = find_named(list_reports(client), name)
    if existing:
        full = report_full_payload(client, existing["_id"])
        if not report_is_manageable(existing, full, name=name, marker=marker):
            raise RuntimeError(f"Report {name!r} exists but is not Codex-managed; refusing to update it.")
        full_type = (full or {}).get("type") if isinstance(full, dict) else None
        needs_update = (
            (existing.get("type") or full_type) != payload["type"]
            or not report_has_dashboard_page(full)
            or not report_template_has_marker(full, marker)
            or any(not report_template_contains_text(full, required_text) for required_text in required_texts)
        )
        if not needs_update:
            results.append(Result("exists", "report", name, existing["_id"]))
            return existing
        updated = strip_metadata({**existing, **payload})
        saved = write_rest(client, "PUT", "/api/reports", updated, profile=profile, project_id=project_id, execute=execute)
        if not execute:
            results.append(Result("planned", "report", name, existing["_id"]))
            return existing
        results.append(Result("updated", "report", name, existing["_id"]))
        return saved if isinstance(saved, dict) else updated

    write_rest(client, "POST", "/api/reports", payload, profile=profile, project_id=project_id, execute=execute)
    if not execute:
        results.append(Result("planned", "report", name))
        return None
    refreshed = find_named(list_reports(client), name)
    if not refreshed or not refreshed.get("_id"):
        raise RuntimeError(f"Create report {name!r} was not visible on readback.")
    full = report_full_payload(client, refreshed["_id"])
    if not full:
        raise RuntimeError(f"Create report {name!r} was not visible through /api/reports/full.")
    results.append(Result("created", "report", name, refreshed["_id"], {"full_readback": True}))
    return refreshed


def build_add_form(content_type_id: str, fields: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "name": ADD_FORM_NAME,
        "pageTitle": ADD_FORM_NAME,
        "tabs": [{"name": None, "rows": [content_form_row(content_type_id, fields, create_new=True)]}],
        "formActionContainers": [save_action_container()],
    }


def build_edit_form(view_id: str, view_fields: dict[str, dict[str, Any]], *, report_id: str | None = None) -> dict[str, Any]:
    tabs = [{"name": None, "rows": [view_data_row(view_id, view_fields, editable=True), comments_row()]}]
    if report_id:
        tabs.append({"name": OPENID_REPORT_TAB_NAME, "rows": [report_row(report_id, name=OPENID_REPORT_CELL_NAME, open_id=True)]})
    return {
        "name": EDIT_FORM_NAME,
        "pageTitle": EDIT_FORM_NAME,
        "tabs": tabs,
        "formActionContainers": [save_action_container()],
    }


def build_main_form(
    view_id: str,
    entity_id: str,
    add_form_id: str,
    edit_form_id: str,
    view_fields: dict[str, dict[str, Any]],
    *,
    report_id: str | None,
) -> dict[str, Any]:
    rows = [
        {
            "cells": [
                {
                    "name": VIEW_NAME,
                    "type": "view_data_list",
                    "adding": {"items": []},
                    "params": {"openId": True, "viewId": view_id, "engineVersion": "v2"},
                    "styles": flex_styles(),
                    "editing": {},
                    "emitting": {"listeners": []},
                    "reporting": {"reports": []},
                    "displaying": {"list": {"pageSizeOptions": []}, "fields": view_display_fields(view_fields), "header": {}, "editForm": {}},
                    "cellActionContainers": [open_form_container("Добавить", ADD_ICON_ID, add_form_id, ADD_FORM_NAME, entity_id, "top_left")],
                    "valueActionContainers": [open_form_container("Редактировать", EDIT_ICON_ID, edit_form_id, EDIT_FORM_NAME, entity_id, "toolbar")],
                }
            ],
            "styles": row_styles(),
            "reverse": False,
        }
    ]
    if report_id:
        rows.append(report_row(report_id))
    return {
        "name": MAIN_FORM_NAME,
        "pageTitle": MAIN_FORM_NAME,
        "tabs": [{"name": None, "rows": rows}],
        "formActionContainers": [],
    }


def report_row(report_id: str, *, name: str = REPORT_NAME, open_id: bool = False) -> dict[str, Any]:
    params = {"reportId": report_id, "fullscreenMode": False}
    if open_id:
        params["openId"] = True
    return {
        "cells": [
            {
                "name": name,
                "type": "report",
                "adding": {},
                "params": params,
                "styles": flex_styles(),
                "editing": {},
                "emitting": {},
                "reporting": {"reports": []},
                "displaying": {"fields": {}, "header": {}},
                "cellActionContainers": [],
            }
        ],
        "styles": row_styles(),
        "reverse": False,
    }


def content_form_row(content_type_id: str, fields: list[dict[str, Any]], *, create_new: bool) -> dict[str, Any]:
    return {
        "cells": [
            {
                "name": CONTENT_TYPE_NAME,
                "type": "content",
                "adding": {},
                "params": {"openId": False, "createNew": create_new, "contentTypeId": content_type_id, "engineVersion": None},
                "styles": flex_styles(),
                "editing": {},
                "emitting": {},
                "reporting": {"reports": []},
                "displaying": {"fields": content_display_fields(fields), "header": {}, "editForm": {}},
                "cellActionContainers": [],
            }
        ],
        "styles": row_styles(),
        "reverse": False,
    }


def view_data_row(view_id: str, view_fields: dict[str, dict[str, Any]], *, editable: bool) -> dict[str, Any]:
    return {
        "cells": [
            {
                "name": VIEW_NAME,
                "type": "view_data",
                "adding": {},
                "params": {"openId": True, "viewId": view_id, "engineVersion": "v2"},
                "styles": flex_styles(),
                "editing": {"enabled": bool(editable)},
                "emitting": {},
                "reporting": {"reports": []},
                "displaying": {"fields": view_display_fields(view_fields), "header": {}, "editForm": {}},
                "cellActionContainers": [],
            }
        ],
        "styles": row_styles(),
        "reverse": False,
    }


def comments_row() -> dict[str, Any]:
    return {
        "cells": [
            {
                "name": COMMENTS_BLOCK_TITLE,
                "type": "comments_list",
                "adding": {},
                "params": {"openId": True, "entity": COMMENT_ENTITY},
                "styles": flex_styles(),
                "editing": {},
                "emitting": {},
                "reporting": {},
                "displaying": {"fields": {}, "header": {"title": COMMENTS_BLOCK_TITLE, "position": "top_left"}},
                "cellActionContainers": [],
            }
        ],
        "styles": row_styles(),
        "reverse": False,
    }


def content_display_fields(fields: list[dict[str, Any]]) -> dict[str, Any]:
    display: dict[str, Any] = {}
    for order, field in enumerate(fields):
        display[field["mname"]] = {"order": order, "title": field["name"]}
    return display


def view_display_fields(view_fields: dict[str, dict[str, Any]]) -> dict[str, Any]:
    display: dict[str, Any] = {"_id": {"order": 0, "hidden": True}}
    for order, field in enumerate(FIELD_SPECS, start=1):
        view_field = next((item for key, item in view_fields.items() if key.endswith(f"_{field.suffix}")), None)
        mname = (view_field or {}).get("mname")
        if mname:
            display[mname] = {"order": order, "hidden": False, "title": field.name}
    return display


def open_form_container(title: str, icon_id: str, form_id: str, form_name: str, view_entity_id: str, position: str) -> dict[str, Any]:
    return {
        "type": "action",
        "title": title,
        "iconId": icon_id,
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


def save_action_container() -> dict[str, Any]:
    return {
        "type": "action",
        "title": "Сохранить",
        "iconId": SAVE_ICON_ID,
        "styles": {},
        "actions": [{"_id": None, "type": "data_managing", "argumentsConfig": {}, "dataManagingType": "submit_all"}],
        "position": "bottom_left",
        "conditions": [],
    }


def field_by_suffix(fields: list[dict[str, Any]], suffix: str) -> dict[str, Any]:
    spec = next((item for item in FIELD_SPECS if item.suffix == suffix), None)
    if not spec:
        raise RuntimeError(f"Unknown field suffix {suffix!r}.")
    field = next((item for item in fields if item.get("name") == spec.name or mname_matches(item, spec)), None)
    if not field or not field.get("_id") or not field.get("mname"):
        raise RuntimeError(f"Field {spec.name!r} was not found.")
    return field


def normalize_file_values(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value] if file_value_id(value) else []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict) and file_value_id(item)]
    return []


def file_value_id(value: dict[str, Any]) -> str | None:
    raw = value.get("id") or value.get("_id") or value.get("fileId")
    return str(raw) if raw else None


def find_uploaded_value(client: AlteriosClient, values: list[dict[str, Any]], filename: str) -> dict[str, Any] | None:
    ids = [file_id for value in values if (file_id := file_value_id(value))]
    if not ids:
        return None
    metadata = list_file_metadata(client, ids)
    by_id = {str(item.get("_id")): item for item in metadata if item.get("_id")}
    for value in values:
        file_id = file_value_id(value)
        meta = by_id.get(str(file_id)) if file_id else None
        names = {str(item) for item in (value.get("filename"), value.get("name"), (meta or {}).get("filename")) if item}
        if filename in names:
            return value
    return None


def audit_file_upload(*, profile: str, project_id: str, content_type_id: str, field_id: str, execute: bool) -> None:
    operation = WriteOperation(
        name="POST /api/file/upload/field",
        kind="file_upload",
        risk_level="write",
        summary="Upload a file into an Alterios file field.",
        method="POST",
        path="/api/file/upload/field",
        target_ids=collect_target_ids({"contentTypeId": content_type_id, "fieldId": field_id}),
        request={"filename": UPLOAD_FILENAME, "size": len(UPLOAD_BYTES), "contentTypeId": content_type_id, "fieldId": field_id},
    )
    build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=not execute,
        write_enabled=write_enabled(),
    )
    if execute:
        assert_write_allowed(profile=profile, project_id=project_id, operation=operation, write_enabled=write_enabled())


def upload_multipart(
    client: AlteriosClient,
    data: bytes,
    meta: dict[str, Any],
    content_type_id: str,
    field_id: str,
    *,
    profile: str,
    project_id: str,
    execute: bool,
) -> Any:
    audit_file_upload(profile=profile, project_id=project_id, content_type_id=content_type_id, field_id=field_id, execute=execute)
    if not execute:
        return None
    boundary = "----CodexAlteriosBoundary" + uuid.uuid4().hex
    filename = str(meta.get("filename") or "upload.bin")
    mime_type = str(meta.get("mimeType") or mimetypes.guess_type(filename)[0] or "application/octet-stream")
    body = build_multipart(boundary, "upload", filename, mime_type, data)
    headers = dict(client._headers())  # Uses the same project/auth headers as JSON requests.
    headers.update(
        {
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
            "contenttype": content_type_id,
            "field": field_id,
            "ngsw-bypass": "true",
        }
    )
    url = client.config.base_url.rstrip("/") + "/api/file/upload/field"
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=client.config.timeout_seconds) as response:
            return parse_response_body(response.read(), response.headers.get("Content-Type", ""))
    except HTTPError as exc:
        parsed = parse_response_body(exc.read(), exc.headers.get("Content-Type", "") if exc.headers else "")
        raise RuntimeError(f"POST /api/file/upload/field failed with HTTP {exc.code}: {safe_error(parsed)}") from exc
    except URLError as exc:
        raise RuntimeError(f"POST /api/file/upload/field failed: {exc.reason}") from exc


def build_multipart(boundary: str, field_name: str, filename: str, mime_type: str, data: bytes) -> bytes:
    safe_filename = filename.replace('"', "'")
    head_text = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{safe_filename}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    )
    head = head_text.encode("cp1251", errors="replace")
    tail = f"\r\n--{boundary}--\r\n".encode("ascii")
    return head + data + tail


def build_manual_script_body() -> str:
    return r"""
var Handler = class McpPracticeManualSandbox {
  async onStart(startArgs) {
    const input = startArgs && typeof startArgs === "object" ? startArgs : {};
    if (typeof args !== "undefined" && args) {
      for (const key in args) input[key] = args[key];
    }
    if (typeof contentId !== "undefined" && contentId) input.contentId = contentId;
    if (typeof source !== "undefined" && source) input.source = source;
    if (typeof mode !== "undefined" && mode) input.mode = mode;
    const result = {
      ok: true,
      marker: "alterios-mcp manual script sandbox",
      contentId: input.contentId || null,
      source: input.source || null,
      mode: input.mode || null,
      receivedKeys: Object.keys(input).sort()
    };
    if (typeof writeLog === "function") {
      await writeLog("alterios-mcp manual script sandbox: " + JSON.stringify(result), "info");
      result.writeLog = true;
    }
    return result;
  }
}

new Handler();
""".strip()


def build_process_xml(task_form_id: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<bpmn2:definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:bpmn2="{BPMN_NS}" xmlns:bpmndi="{BPMNDI_NS}" xmlns:dc="{DC_NS}" xmlns:di="{DI_NS}" xmlns:camunda="{CAMUNDA_NS}" id="mcp-practice-sandbox" targetNamespace="http://bpmn.io/schema/bpmn" xsi:schemaLocation="{BPMN_NS} BPMN20.xsd">
  <bpmn2:process id="Process_mcp_practice_sandbox" name="{BPMN_DIAGRAM_NAME}" isExecutable="true">
    <bpmn2:startEvent id="StartEvent_mcp_practice" camunda:formKey="{task_form_id}">
      <bpmn2:outgoing>Flow_to_task</bpmn2:outgoing>
      <camunda:nextTasks>Activity_mcp_practice_task</camunda:nextTasks>
    </bpmn2:startEvent>
    <bpmn2:sequenceFlow id="Flow_to_task" sourceRef="StartEvent_mcp_practice" targetRef="Activity_mcp_practice_task" />
    <bpmn2:userTask id="Activity_mcp_practice_task" name="MCP Practice task" camunda:formKey="{task_form_id}" camunda:savable="true" camunda:candidateUsers="" camunda:candidateGroups="">
      <bpmn2:incoming>Flow_to_task</bpmn2:incoming>
      <bpmn2:outgoing>Flow_to_end</bpmn2:outgoing>
    </bpmn2:userTask>
    <bpmn2:sequenceFlow id="Flow_to_end" name="Complete sandbox task" sourceRef="Activity_mcp_practice_task" targetRef="EndEvent_mcp_practice" />
    <bpmn2:endEvent id="EndEvent_mcp_practice" name="Done">
      <bpmn2:incoming>Flow_to_end</bpmn2:incoming>
      <bpmn2:terminateEventDefinition id="TerminateEventDefinition_mcp_practice" />
    </bpmn2:endEvent>
  </bpmn2:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_mcp_practice">
    <bpmndi:BPMNPlane id="BPMNPlane_mcp_practice" bpmnElement="Process_mcp_practice_sandbox">
      <bpmndi:BPMNShape id="StartEvent_mcp_practice_di" bpmnElement="StartEvent_mcp_practice"><dc:Bounds x="180" y="210" width="36" height="36" /></bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="Activity_mcp_practice_task_di" bpmnElement="Activity_mcp_practice_task"><dc:Bounds x="300" y="188" width="190" height="80" /></bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="EndEvent_mcp_practice_di" bpmnElement="EndEvent_mcp_practice"><dc:Bounds x="570" y="210" width="36" height="36" /></bpmndi:BPMNShape>
      <bpmndi:BPMNEdge id="Flow_to_task_di" bpmnElement="Flow_to_task"><di:waypoint x="216" y="228" /><di:waypoint x="300" y="228" /></bpmndi:BPMNEdge>
      <bpmndi:BPMNEdge id="Flow_to_end_di" bpmnElement="Flow_to_end"><di:waypoint x="490" y="228" /><di:waypoint x="570" y="228" /></bpmndi:BPMNEdge>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn2:definitions>"""


def process_id_from_response(response: Any) -> str | None:
    if isinstance(response, dict):
        raw = response.get("processId") or response.get("_id") or response.get("id")
        return str(raw) if raw else None
    return None


def wait_for_tasks(
    client: AlteriosClient,
    *,
    diagram_id: str,
    content_id: str,
    process_id: str | None,
    attempts: int = 20,
) -> list[dict[str, Any]]:
    for _ in range(attempts):
        if process_id:
            tasks = list_tasks_by_process(client, process_id)
        else:
            tasks = list_tasks(client, diagram_id=diagram_id, content_id=content_id)
        if tasks:
            return tasks
        time.sleep(0.5)
    return []


def active_tasks_for_processes(
    client: AlteriosClient,
    processes: list[dict[str, Any]],
    *,
    diagram_id: str,
    content_id: str,
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for process in processes:
        process_id = process.get("_id")
        if process_id:
            tasks.extend(list_tasks_by_process(client, str(process_id)))
    if tasks:
        return tasks
    return list_tasks(client, diagram_id=diagram_id, content_id=content_id)


def wait_for_completed_process(
    client: AlteriosClient,
    *,
    diagram_id: str,
    content_id: str,
    attempts: int = 20,
) -> dict[str, Any] | None:
    for _ in range(attempts):
        processes = list_processes(client, diagram_id=diagram_id, content_id=content_id)
        completed = next((process for process in processes if process.get("completed") and not process.get("error")), None)
        if completed:
            return completed
        time.sleep(0.5)
    return None


def response_shape(value: Any) -> str:
    if isinstance(value, dict):
        return "dict:" + ",".join(sorted(str(key) for key in value.keys())[:8])
    if isinstance(value, list):
        return f"list:{len(value)}"
    return type(value).__name__


def build_dashboard_template(base_url: str, view_id: str, view_fields: dict[str, dict[str, Any]]) -> str:
    return build_stimulsoft_dashboard_template(
        base_url,
        view_id,
        view_fields,
        report_name=REPORT_NAME,
        marker=REPORT_MARKER,
        template_kind="static",
    )


def build_openid_bound_dashboard_template(base_url: str, view_id: str, view_fields: dict[str, dict[str, Any]]) -> str:
    return build_stimulsoft_dashboard_template(
        base_url,
        view_id,
        view_fields,
        report_name=OPENID_BOUND_REPORT_NAME,
        marker=OPENID_BOUND_REPORT_MARKER,
        template_kind="openid_bound",
        title_column=dashboard_column_name(view_fields, "title"),
    )


def build_stimulsoft_dashboard_template(
    base_url: str,
    view_id: str,
    view_fields: dict[str, dict[str, Any]],
    *,
    report_name: str,
    marker: str,
    template_kind: str,
    title_column: str | None = None,
) -> str:
    node_path = find_node()
    scripts_dir = ensure_stimulsoft_assets(base_url)
    helper_path = Path(tempfile.gettempdir()) / "alterios-stimulsoft" / "build_mcp_practice_dashboard.js"
    helper_path.write_text(STIMULSOFT_TEMPLATE_HELPER, encoding="utf-8")
    payload = {
        "scriptsDir": str(scripts_dir),
        "reportName": report_name,
        "marker": marker,
        "templateKind": template_kind,
        "viewName": VIEW_NAME,
        "viewId": view_id,
        "columns": dashboard_columns(view_fields),
        "titleColumn": title_column,
    }
    completed = subprocess.run(
        [str(node_path), str(helper_path)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Stimulsoft dashboard template generation failed: {completed.stderr.strip()[:800]}")
    template = completed.stdout.strip()
    if not template.startswith("{") or "StiDashboard" not in template:
        raise RuntimeError("Stimulsoft dashboard template generation returned unexpected output.")
    return template


def dashboard_columns(view_fields: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    columns: list[dict[str, str]] = [{"name": "_id", "alias": "ID", "type": "System.String"}]
    for field in FIELD_SPECS:
        view_field = next((item for key, item in view_fields.items() if key.endswith(f"_{field.suffix}")), None)
        mname = (view_field or {}).get("mname")
        if not mname:
            continue
        column_type = "System.String"
        if field.field_type == "number":
            column_type = "System.Decimal"
        elif field.field_type == "boolean":
            column_type = "System.Boolean"
        elif field.field_type == "date":
            column_type = "System.DateTime"
        columns.append({"name": mname, "alias": field.name, "type": column_type})
    return columns


def dashboard_column_name(view_fields: dict[str, dict[str, Any]], suffix: str) -> str:
    view_field = next((item for key, item in view_fields.items() if key.endswith(f"_{suffix}")), None)
    mname = (view_field or {}).get("mname")
    if not mname:
        raise RuntimeError(f"View field mname for suffix {suffix!r} was not found.")
    return str(mname)


def find_node() -> Path:
    node = shutil.which("node")
    if node:
        return Path(node)
    runtime_node = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node.exe"
    if runtime_node.exists():
        return runtime_node
    raise RuntimeError(f"Node.js is required to generate a Stimulsoft dashboard template. Checked PATH and {runtime_node}.")


def ensure_stimulsoft_assets(base_url: str) -> Path:
    if not base_url:
        raise RuntimeError("ALTERIOS_BASE_URL is required to download Stimulsoft assets.")
    target = Path(tempfile.gettempdir()) / "alterios-stimulsoft"
    target.mkdir(parents=True, exist_ok=True)
    for filename in ("stimulsoft.reports.pack.js", "stimulsoft.dashboards.pack.js"):
        path = target / filename
        if path.exists() and path.stat().st_size > 1000:
            continue
        request = Request(base_url.rstrip("/") + f"/assets/stimulsoft/{filename}", headers={"User-Agent": "AlteriosCodex/1.0"})
        try:
            with urlopen(request, timeout=45) as response:
                path.write_bytes(response.read())
        except OSError as exc:
            raise RuntimeError(f"Download Stimulsoft asset failed: {filename}: {exc}") from exc
    return target


def ensure_marked(kind: str, name: str, existing: dict[str, Any], marker: str) -> None:
    if marker not in str(existing.get("description") or ""):
        raise RuntimeError(f"{kind} {name!r} exists but is not Codex-managed; refusing to update it.")


STIMULSOFT_TEMPLATE_HELPER = r"""
const fs = require('fs');
const path = require('path');

const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const reports = require(path.join(input.scriptsDir, 'stimulsoft.reports.pack.js'));
const dashboards = require(path.join(input.scriptsDir, 'stimulsoft.dashboards.pack.js'));
const Stimulsoft = dashboards.Stimulsoft || reports.Stimulsoft;
const S = Stimulsoft;
const PROJECT_DATABASE_SERVICE = 'Project Database';

function guid() {
  return 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'.replace(/x/g, () => Math.floor(Math.random() * 16).toString(16));
}

function addProjectDatabase(report) {
  const connection = JSON.stringify({ type: 'view-data-v2', filter: { viewId: input.viewId } });
  const database = new S.Report.Dictionary.StiCustomDatabase(input.viewName, PROJECT_DATABASE_SERVICE, connection);
  database.serviceName = PROJECT_DATABASE_SERVICE;
  database.castToColumnType = 'CastToColumnType';
  report.dictionary.databases.add(database);

  const dataSource = new S.Report.Dictionary.StiCustomSource(input.viewName, 'data', input.viewName);
  dataSource.serviceName = PROJECT_DATABASE_SERVICE;
  dataSource.sqlCommand = 'data';
  for (const column of input.columns) {
    let type = S.System.String;
    if (column.type === 'System.DateTime') type = S.System.DateTime;
    if (column.type === 'System.Decimal') type = S.System.Decimal;
    if (column.type === 'System.Boolean') type = S.System.Boolean;
    dataSource.columns.add(new S.Report.Dictionary.StiDataColumn(column.name, column.name, column.alias, type));
  }
  report.dictionary.dataSources.add(dataSource);
}

function finalize(report) {
  addProjectDatabase(report);
  const saved = JSON.parse(report.saveToJsonString());
  saved.CodexMarker = input.marker;
  const connection = JSON.stringify({ type: 'view-data-v2', filter: { viewId: input.viewId } });
  for (const key of Object.keys(saved.Dictionary?.Databases || {})) {
    saved.Dictionary.Databases[key].CastToColumnType = 'CastToColumnType';
    saved.Dictionary.Databases[key].ConnectionString = connection;
    delete saved.Dictionary.Databases[key].ConnectionStringEncrypted;
  }
  return JSON.stringify(saved);
}

function makeStaticTemplate() {
  const source = S.Report.StiReport.createNewDashboard();
  const json = JSON.parse(source.saveToJsonString());
  json.ReportName = input.reportName;
  json.ReportAlias = input.reportName;
  json.Pages['0'].Name = 'McpPracticeDashboard';
  json.Pages['0'].Width = 1280;
  json.Pages['0'].Height = 720;
  json.Pages['0'].Components = {
    '0': {
      Ident: 'StiTextElement',
      Name: 'DashboardTitle',
      Guid: guid(),
      ClientRectangle: '24,24,900,56',
      Border: ';;;;',
      Text: 'MCP Practice sandbox report',
      ForeColor: '30,41,59',
      SizeMode: 'Fit',
      VertAlignment: 'Center',
      CornerRadius: '0,0,0,0',
      Shadow: ';;;'
    }
  };

  const loaded = new S.Report.StiReport();
  loaded.load(JSON.stringify(json));
  loaded.reportName = input.reportName;
  loaded.reportAlias = input.reportName;
  return finalize(loaded);
}

function makeOpenIdBoundTemplate() {
  if (!input.titleColumn) {
    throw new Error('titleColumn is required for openid_bound dashboard template');
  }
  const source = S.Report.StiReport.createNewDashboard();
  const json = JSON.parse(source.saveToJsonString());
  json.ReportName = input.reportName;
  json.ReportAlias = input.reportName;
  json.Pages['0'].Name = 'McpPracticeOpenIdDashboard';
  json.Pages['0'].Width = 1280;
  json.Pages['0'].Height = 720;
  json.Pages['0'].Components = {
    '0': {
      Ident: 'StiTextElement',
      Name: 'OpenIdReportTitle',
      Guid: guid(),
      ClientRectangle: '24,24,900,56',
      Border: ';;;;',
      Text: 'MCP Practice openId current row',
      ForeColor: '30,41,59',
      SizeMode: 'Fit',
      VertAlignment: 'Center',
      CornerRadius: '0,0,0,0',
      Shadow: ';;;'
    },
    '1': {
      Ident: 'StiTextElement',
      Name: 'OpenIdCurrentRowTitle',
      Guid: guid(),
      ClientRectangle: '24,104,1100,72',
      Border: ';;;;',
      Text: `{data.${input.titleColumn}}`,
      ForeColor: '15,23,42',
      SizeMode: 'Fit',
      VertAlignment: 'Center',
      Measures: {
        '0': {
          Ident: 'TextMeter',
          Key: `data.${input.titleColumn}`,
          Expression: `data.${input.titleColumn}`,
          Label: 'Current row title'
        }
      },
      CornerRadius: '0,0,0,0',
      Shadow: ';;;'
    }
  };

  const loaded = new S.Report.StiReport();
  loaded.load(JSON.stringify(json));
  loaded.reportName = input.reportName;
  loaded.reportAlias = input.reportName;
  return finalize(loaded);
}

function makeTemplate() {
  if (input.templateKind === 'static') {
    return makeStaticTemplate();
  }
  if (input.templateKind === 'openid_bound') {
    return makeOpenIdBoundTemplate();
  }
  throw new Error(`Unknown templateKind: ${input.templateKind}`);
}

process.stdout.write(makeTemplate());
"""


def update_resource(
    client: AlteriosClient,
    collection: str,
    resource: dict[str, Any],
    *,
    profile: str,
    project_id: str,
    execute: bool,
) -> Any:
    resource_id = resource.get("_id")
    if not resource_id:
        raise RuntimeError(f"Cannot update /api/{collection}: resource has no _id.")
    payload = strip_metadata(resource)
    if not execute:
        write_rest(client, "PATCH", f"/api/{collection}/{resource_id}", payload, profile=profile, project_id=project_id, execute=False)
        return None
    errors: list[str] = []
    for method, path in (
        ("PATCH", f"/api/{collection}/{resource_id}"),
        ("PUT", f"/api/{collection}/{resource_id}"),
        ("PUT", f"/api/{collection}"),
        ("POST", f"/api/{collection}"),
    ):
        try:
            return write_rest(client, method, path, payload, profile=profile, project_id=project_id, execute=True)
        except AlteriosRequestError as exc:
            errors.append(str(exc))
    raise RuntimeError(f"Update /api/{collection}/{resource_id} failed: {'; '.join(errors)}")


def resource_needs_update(existing: dict[str, Any], payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return any(existing.get(key) != payload.get(key) for key in keys)


def ensure_codex_managed(kind: str, name: str, existing: dict[str, Any]) -> None:
    if CONTENT_TYPE_MARKER not in str(existing.get("description") or ""):
        raise RuntimeError(f"{kind} {name!r} exists but is not Codex-managed; refusing to update it.")


def view_field_save_payload(field: dict[str, Any]) -> dict[str, Any]:
    payload = dict(strip_metadata(field))
    for key in ("contentType", "contentTypeField", "relatedViewField", "diagramsNames"):
        payload.pop(key, None)
    return payload


def content_save_payload(content: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in strip_metadata(content).items()
        if key in {"_id", "contentTypeId", "fields", "groupsIds", "name"}
    }


def field_mnames_by_suffix(fields: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for spec in FIELD_SPECS:
        field = next((item for item in fields if item.get("name") == spec.name or mname_matches(item, spec)), None)
        if not field or not field.get("mname"):
            raise RuntimeError(f"Field {spec.name!r} mname was not found.")
        result[spec.suffix] = field["mname"]
    return result


def view_mname(field_mname: str) -> str:
    return field_mname.removeprefix("field_")


def flex_styles() -> dict[str, Any]:
    return {"flexGrow": 1, "flexBasis": 0, "flexShrink": 1, "flexBasisUnit": "%"}


def row_styles() -> dict[str, Any]:
    return flex_styles()


def first(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def write_rest(
    client: AlteriosClient,
    method: str,
    path: str,
    body: dict[str, Any],
    *,
    profile: str,
    project_id: str,
    execute: bool,
    risk_level: str | None = None,
) -> Any:
    operation = WriteOperation(
        name=f"{method} {path}",
        kind="rest",
        risk_level=risk_level or ("destructive" if method.upper() == "DELETE" else "write"),
        summary=f"Run {method} against an Alterios REST API path.",
        method=method.upper(),
        path=path,
        target_ids=collect_target_ids(body),
        request=body,
    )
    build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=not execute,
        write_enabled=write_enabled(),
    )
    if not execute:
        return None
    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=write_enabled(),
    )
    return client.request(method, path, body=body).body


def verify_metadata(client: AlteriosClient, content_type_id: str | None) -> dict[str, Any]:
    content_type = find_named(list_content_types(client), CONTENT_TYPE_NAME)
    if not content_type_id and content_type:
        content_type_id = content_type.get("_id")
    fields = list_fields(client, content_type_id) if content_type_id else []
    field_mnames = field_mnames_by_suffix(fields) if len(fields) >= len(FIELD_SPECS) else {}
    view = find_named(list_views(client), VIEW_NAME)
    forms = {name: find_named(list_forms(client), name) for name in (ADD_FORM_NAME, EDIT_FORM_NAME, MAIN_FORM_NAME)}
    group = next((item for item in list_groups(client) if item.get("name") == GROUP_NAME and not item.get("root")), None)
    rows = list_content_rows(client, content_type_id, limit=500) if content_type_id else []
    content = None
    openid_control_content = None
    if field_mnames:
        content = next(
            (
                row
                for row in rows
                if first((row.get("fields") or {}).get(field_mnames["title"])) == CONTENT_ROW_TITLE
            ),
            None,
        )
        openid_control_content = next(
            (
                row
                for row in rows
                if first((row.get("fields") or {}).get(field_mnames["title"])) == OPENID_CONTROL_ROW_TITLE
            ),
            None,
        )
    comments = list_comments(client, content["_id"], entity=COMMENT_ENTITY) if content else []
    practice_comment = find_comment_by_body(comments, COMMENT_TEXT)
    file_values = normalize_file_values((content.get("fields") or {}).get(field_mnames.get("attachment"))) if content and field_mnames else []
    file_ids = [file_id for value in file_values if (file_id := file_value_id(value))]
    file_metadata = list_file_metadata(client, file_ids) if file_ids else []
    manual_script = find_named(list_scripts(client), MANUAL_SCRIPT_NAME)
    diagram = find_named(list_diagrams(client), BPMN_DIAGRAM_NAME)
    reports = list_reports(client)
    report = find_named(reports, REPORT_NAME)
    openid_bound_report = find_named(reports, OPENID_BOUND_REPORT_NAME)
    processes = list_processes(client, diagram_id=diagram["_id"], content_id=content["_id"]) if diagram and content else []
    tasks = active_tasks_for_processes(client, processes, diagram_id=diagram["_id"], content_id=content["_id"]) if diagram and content else []
    full_report = report_full_payload(client, report["_id"]) if report and report.get("_id") else None
    full_openid_bound_report = (
        report_full_payload(client, openid_bound_report["_id"]) if openid_bound_report and openid_bound_report.get("_id") else None
    )
    view_probe = view_data_probe(client, view.get("_id") if view else None)
    return {
        "content_type_found": bool(content_type),
        "content_type_id": content_type.get("_id") if content_type else None,
        "content_type_name": content_type.get("name") if content_type else None,
        "field_count": len(fields),
        "field_mnames": [field.get("mname") for field in fields if field.get("mname")],
        "expected_field_names_present": sorted(spec.name for spec in FIELD_SPECS if any(field.get("name") == spec.name for field in fields)),
        "view_id": view.get("_id") if view else None,
        "view_field_count": len(list_view_fields(client, view["_id"])) if view else 0,
        "forms": {name: form.get("_id") if form else None for name, form in forms.items()},
        "edit_form_openid_report_tab": form_has_openid_report_tab(
            forms.get(EDIT_FORM_NAME),
            (openid_bound_report or report or {}).get("_id"),
        ),
        "group_id": group.get("_id") if group else None,
        "group_form_id": group.get("formId") if group else None,
        "content_id": content.get("_id") if content else None,
        "content_title": first((content.get("fields") or {}).get(field_mnames["title"])) if content and field_mnames else None,
        "content_count": len(rows),
        "openid_control_content_id": openid_control_content.get("_id") if openid_control_content else None,
        "openid_control_content_title": (
            first((openid_control_content.get("fields") or {}).get(field_mnames["title"]))
            if openid_control_content and field_mnames
            else None
        ),
        "comment_found": bool(practice_comment),
        "comment_id": practice_comment.get("_id") if practice_comment else None,
        "comment_count": len(flatten_comments(comments)),
        "file_upload_found": bool(file_metadata),
        "file_upload_ids": file_ids,
        "file_upload_names": [item.get("filename") for item in file_metadata],
        "manual_script_id": manual_script.get("_id") if manual_script else None,
        "manual_script_active": manual_script.get("active") is True if manual_script else False,
        "diagram_id": diagram.get("_id") if diagram else None,
        "process_count": len(processes),
        "process_completed": any(process.get("completed") and not process.get("error") for process in processes),
        "task_count": len(tasks),
        "report_id": report.get("_id") if report else None,
        "report_full_readback": bool(full_report),
        "report_has_dashboard_page": report_has_dashboard_page(full_report),
        "openid_bound_report_id": openid_bound_report.get("_id") if openid_bound_report else None,
        "openid_bound_report_full_readback": bool(full_openid_bound_report),
        "openid_bound_report_has_dashboard_page": report_has_dashboard_page(full_openid_bound_report),
        "openid_bound_report_has_project_database": report_has_project_database(full_openid_bound_report),
        "openid_bound_report_has_title_column": report_template_contains_text(full_openid_bound_report, "mcp_practice_title"),
        "view_data_probe": view_probe,
    }


def list_content_types(client: AlteriosClient) -> list[dict[str, Any]]:
    response = client.request("GET", "/api/content-types/listandcount", params={"limit": 1000, "offset": 0})
    return listandcount_items(response.body)


def list_fields(client: AlteriosClient, content_type_id: str) -> list[dict[str, Any]]:
    response = client.request("GET", "/api/fields", params={"contentTypeId": content_type_id})
    if not isinstance(response.body, list):
        raise RuntimeError("GET /api/fields returned unexpected payload")
    return [item for item in response.body if isinstance(item, dict)]


def list_views(client: AlteriosClient) -> list[dict[str, Any]]:
    response = client.request("GET", "/api/views/listandcount", params={"limit": 1000, "offset": 0})
    return listandcount_items(response.body)


def list_forms(client: AlteriosClient) -> list[dict[str, Any]]:
    response = client.request("GET", "/api/forms/listandcount", params={"limit": 1000, "offset": 0})
    return listandcount_items(response.body)


def list_groups(client: AlteriosClient) -> list[dict[str, Any]]:
    response = client.request("GET", "/api/groups")
    if not isinstance(response.body, list):
        raise RuntimeError("GET /api/groups returned unexpected payload")
    return [item for item in response.body if isinstance(item, dict)]


def list_scripts(client: AlteriosClient) -> list[dict[str, Any]]:
    response = client.request("GET", "/api/scripts/listandcount", params={"limit": 5000, "offset": 0})
    return listandcount_items(response.body)


def list_diagrams(client: AlteriosClient) -> list[dict[str, Any]]:
    response = client.request("GET", "/api/diagrams/listandcount", params={"limit": 1000, "offset": 0})
    return listandcount_items(response.body)


def list_reports(client: AlteriosClient) -> list[dict[str, Any]]:
    response = client.request("GET", "/api/reports/listandcount/" + encode_filter({}), params={"limit": 1000, "offset": 0})
    return listandcount_items(response.body)


def report_full_payload(client: AlteriosClient, report_id: str) -> Any:
    body = client.report_full(report_id).body
    if isinstance(body, list):
        return body[0] if body else None
    if isinstance(body, dict):
        for key in ("items", "rows", "data", "results", "values"):
            value = body.get(key)
            if isinstance(value, list):
                return value[0] if value else None
        return body
    return body


def list_file_metadata(client: AlteriosClient, file_ids: list[str]) -> list[dict[str, Any]]:
    if not file_ids:
        return []
    response = client.request("GET", "/api/file/list", params={"id": file_ids})
    body = response.body
    if isinstance(body, list):
        return [item for item in body if isinstance(item, dict)]
    if isinstance(body, dict):
        for key in ("items", "rows", "data", "results", "values"):
            value = body.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise RuntimeError("GET /api/file/list returned unexpected payload")


def list_processes(client: AlteriosClient, *, diagram_id: str, content_id: str) -> list[dict[str, Any]]:
    response = client.request(
        "GET",
        "/api/processes/listandcount",
        params={"diagramId": diagram_id, "contentId": content_id, "limit": 20, "offset": 0},
    )
    return listandcount_items(response.body)


def list_tasks(client: AlteriosClient, *, diagram_id: str, content_id: str) -> list[dict[str, Any]]:
    response = client.request("GET", "/api/tasks/", params={"diagramId": diagram_id, "contentId": content_id})
    body = response.body
    if isinstance(body, list):
        return [item for item in body if isinstance(item, dict)]
    if isinstance(body, dict):
        for key in ("items", "rows", "data", "results", "values"):
            value = body.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise RuntimeError("GET /api/tasks/ returned unexpected payload")


def list_tasks_by_process(client: AlteriosClient, process_id: str) -> list[dict[str, Any]]:
    response = client.request("GET", "/api/tasks/", params={"processId": process_id})
    body = response.body
    if isinstance(body, list):
        return [item for item in body if isinstance(item, dict)]
    if isinstance(body, dict):
        for key in ("items", "rows", "data", "results", "values"):
            value = body.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise RuntimeError("GET /api/tasks/ returned unexpected payload")


def list_view_entities(client: AlteriosClient, view_id: str) -> list[dict[str, Any]]:
    response = client.request("GET", f"/api/view-entities/by-view/{view_id}")
    if not isinstance(response.body, list):
        raise RuntimeError("GET /api/view-entities/by-view returned unexpected payload")
    return [item for item in response.body if isinstance(item, dict)]


def list_view_fields(client: AlteriosClient, view_id: str) -> list[dict[str, Any]]:
    response = client.request("GET", f"/api/view-fields/populated/{view_id}")
    if not isinstance(response.body, list):
        raise RuntimeError("GET /api/view-fields/populated returned unexpected payload")
    return [item for item in response.body if isinstance(item, dict)]


def list_content_rows(client: AlteriosClient, content_type_id: str, *, limit: int) -> list[dict[str, Any]]:
    response = client.request("GET", "/api/contents/listandcount", params={"contentTypeId": content_type_id, "limit": limit, "offset": 0})
    return listandcount_items(response.body)


def list_comments(client: AlteriosClient, entity_id: str, *, entity: str, limit: int = 50, depth: int = 4, page: int = 1) -> list[dict[str, Any]]:
    response = client.request(
        "GET",
        "/api/v1/comments",
        params={"entity": entity, "entityId": entity_id, "limit": limit, "depth": depth, "page": page},
    )
    body = response.body
    if isinstance(body, list):
        return [item for item in body if isinstance(item, dict)]
    if isinstance(body, dict):
        for key in ("items", "comments", "rows", "data", "results", "values"):
            value = body.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise RuntimeError("GET /api/v1/comments returned unexpected payload")


def flatten_comments(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for comment in comments:
        flattened.append(comment)
        children = comment.get("children")
        if isinstance(children, list):
            flattened.extend(flatten_comments([item for item in children if isinstance(item, dict)]))
    return flattened


def find_comment_by_body(comments: list[dict[str, Any]], body: str) -> dict[str, Any] | None:
    return next((comment for comment in flatten_comments(comments) if (comment.get("body") or "").strip() == body), None)


def view_data_probe(client: AlteriosClient, view_id: str | None) -> dict[str, Any]:
    if not view_id:
        return {"ok": False, "reason": "view is missing"}
    try:
        response = client.request("POST", "/api/views/v2/get-data-simplified", body={"viewId": view_id, "limit": 5, "offset": 0})
    except AlteriosRequestError as exc:
        return {"ok": False, "error": str(exc)}
    body = response.body
    if isinstance(body, list):
        return {"ok": True, "status_code": response.status_code, "row_count": len(body)}
    if isinstance(body, dict):
        rows = next((body.get(key) for key in ("items", "rows", "data", "results") if isinstance(body.get(key), list)), None)
        return {"ok": True, "status_code": response.status_code, "shape": "dict", "row_count": len(rows) if rows is not None else None}
    return {"ok": True, "status_code": response.status_code, "shape": type(body).__name__}


def report_has_dashboard_page(report: Any) -> bool:
    if not isinstance(report, dict):
        return False
    template = report.get("template")
    if isinstance(template, str):
        try:
            template = json.loads(template)
        except json.JSONDecodeError:
            return False
    if not isinstance(template, dict):
        return False
    page = (template.get("Pages") or {}).get("0")
    return isinstance(page, dict) and page.get("Ident") == "StiDashboard"


def report_template_has_marker(report: Any, marker: str) -> bool:
    template = report_template_payload(report)
    return isinstance(template, dict) and template.get("CodexMarker") == marker


def report_is_manageable(existing: dict[str, Any], full: Any, *, name: str, marker: str) -> bool:
    if marker in str(existing.get("description") or "") or marker in str((full or {}).get("description") if isinstance(full, dict) else ""):
        return True
    if report_template_has_marker(full, marker):
        return True
    return existing.get("name") == name and report_has_dashboard_page(full)


def report_template_contains_text(report: Any, expected: str) -> bool:
    if not expected:
        return True
    template = report_template_payload(report)
    return any(expected in item for item in walk_values(template) if isinstance(item, str))


def report_has_project_database(report: Any) -> bool:
    template = report_template_payload(report)
    for value in walk_values(template):
        if isinstance(value, dict) and value.get("ServiceName") == "Project Database":
            return True
        if isinstance(value, str) and value == "Project Database":
            return True
    return False


def walk_values(value: Any) -> list[Any]:
    values = [value]
    if isinstance(value, dict):
        for child in value.values():
            values.extend(walk_values(child))
    elif isinstance(value, list):
        for child in value:
            values.extend(walk_values(child))
    return values


def form_has_openid_report_tab(form: dict[str, Any] | None, report_id: str | None) -> bool:
    if not form or not report_id:
        return False
    for tab in form.get("tabs") or []:
        if tab.get("name") != OPENID_REPORT_TAB_NAME:
            continue
        for row in tab.get("rows") or []:
            for cell in row.get("cells") or []:
                params = cell.get("params") or {}
                if cell.get("type") == "report" and params.get("reportId") == report_id and params.get("openId") is True:
                    return True
    return False


def report_template_payload(report: Any) -> dict[str, Any] | None:
    if not isinstance(report, dict):
        return None
    template = report.get("template")
    if isinstance(template, str):
        try:
            template = json.loads(template)
        except json.JSONDecodeError:
            return None
    return template if isinstance(template, dict) else None


def listandcount_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        if payload and isinstance(payload[0], list):
            return [item for item in payload[0] if isinstance(item, dict)]
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "rows", "data", "results", "values"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise RuntimeError("listandcount returned unexpected payload")


def find_named(items: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((item for item in items if item.get("name") == name), None)


def strip_metadata(value: Any) -> Any:
    metadata_keys = {
        "apiKey",
        "author",
        "authorName",
        "createdAt",
        "emailConfirmationCode",
        "lastUpdate",
        "password",
        "passwordRecoverCode",
        "token",
    }
    if isinstance(value, dict):
        return {key: strip_metadata(item) for key, item in value.items() if key not in metadata_keys}
    if isinstance(value, list):
        return [strip_metadata(item) for item in value]
    return value


def write_enabled() -> bool:
    return os.environ.get("ALTERIOS_MCP_ALLOW_WRITE") == "1"


if __name__ == "__main__":
    raise SystemExit(main())
