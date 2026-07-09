from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any

from alterios_mcp.client import AlteriosClient, AlteriosConfig, AlteriosConfigError, AlteriosRequestError
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

SAVE_ICON_ID = "95ec6613-fdcc-4ad5-b93f-16e871b8cbbc"
ADD_ICON_ID = "de3b1bed-27d2-4963-8024-64e7d71d9fb2"
EDIT_ICON_ID = "aa4c573e-104e-46a2-934f-780e105f3b1b"
COMMENT_ENTITY = "any"
COMMENT_TEXT = "MCP Practice comment: comments write/readback coverage."
COMMENTS_BLOCK_TITLE = "Обсуждение"


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
        build_edit_form(view["_id"], view_fields),
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
        build_main_form(view["_id"], entity["_id"], add_form["_id"], edit_form["_id"], view_fields),
        profile=profile,
        project_id=project_id,
        execute=execute,
    )
    if not main_form or not main_form.get("_id"):
        results.append(Result("blocked", "ui_chain", "Group/content", details={"reason": "main form does not exist in dry-run"}))
        return results, verify_metadata(client, content_type["_id"])

    ensure_group(client, results, main_form["_id"], profile=profile, project_id=project_id, execute=execute)
    content = ensure_practice_content(client, results, content_type["_id"], fields, profile=profile, project_id=project_id, execute=execute)
    if content and content.get("_id"):
        ensure_practice_comment(client, results, content["_id"], profile=profile, project_id=project_id, execute=execute)
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


def build_add_form(content_type_id: str, fields: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "name": ADD_FORM_NAME,
        "pageTitle": ADD_FORM_NAME,
        "tabs": [{"name": None, "rows": [content_form_row(content_type_id, fields, create_new=True)]}],
        "formActionContainers": [save_action_container()],
    }


def build_edit_form(view_id: str, view_fields: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "name": EDIT_FORM_NAME,
        "pageTitle": EDIT_FORM_NAME,
        "tabs": [{"name": None, "rows": [view_data_row(view_id, view_fields, editable=True), comments_row()]}],
        "formActionContainers": [save_action_container()],
    }


def build_main_form(
    view_id: str,
    entity_id: str,
    add_form_id: str,
    edit_form_id: str,
    view_fields: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "name": MAIN_FORM_NAME,
        "pageTitle": MAIN_FORM_NAME,
        "tabs": [
            {
                "name": None,
                "rows": [
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
                ],
            }
        ],
        "formActionContainers": [],
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
) -> Any:
    operation = WriteOperation(
        name=f"{method} {path}",
        kind="rest",
        risk_level="destructive" if method.upper() == "DELETE" else "write",
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
    if field_mnames:
        content = next(
            (
                row
                for row in rows
                if first((row.get("fields") or {}).get(field_mnames["title"])) == CONTENT_ROW_TITLE
            ),
            None,
        )
    comments = list_comments(client, content["_id"], entity=COMMENT_ENTITY) if content else []
    practice_comment = find_comment_by_body(comments, COMMENT_TEXT)
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
        "group_id": group.get("_id") if group else None,
        "group_form_id": group.get("formId") if group else None,
        "content_id": content.get("_id") if content else None,
        "content_title": first((content.get("fields") or {}).get(field_mnames["title"])) if content and field_mnames else None,
        "comment_found": bool(practice_comment),
        "comment_id": practice_comment.get("_id") if practice_comment else None,
        "comment_count": len(flatten_comments(comments)),
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
