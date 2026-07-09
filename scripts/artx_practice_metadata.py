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
            "format": "DD.MM.YYYY",
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
    parser = argparse.ArgumentParser(description="Create or update the ARTX MCP metadata practice chain.")
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
    expected = {key: value for key, value in payload.items() if key != "mname"}
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
    return {
        "content_type_found": bool(content_type),
        "content_type_id": content_type.get("_id") if content_type else None,
        "content_type_name": content_type.get("name") if content_type else None,
        "field_count": len(fields),
        "field_mnames": [field.get("mname") for field in fields if field.get("mname")],
        "expected_field_names_present": sorted(spec.name for spec in FIELD_SPECS if any(field.get("name") == spec.name for field in fields)),
    }


def list_content_types(client: AlteriosClient) -> list[dict[str, Any]]:
    response = client.request("GET", "/api/content-types/listandcount", params={"limit": 1000, "offset": 0})
    return listandcount_items(response.body)


def list_fields(client: AlteriosClient, content_type_id: str) -> list[dict[str, Any]]:
    response = client.request("GET", "/api/fields", params={"contentTypeId": content_type_id})
    if not isinstance(response.body, list):
        raise RuntimeError("GET /api/fields returned unexpected payload")
    return [item for item in response.body if isinstance(item, dict)]


def listandcount_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        if payload and isinstance(payload[0], list):
            return [item for item in payload[0] if isinstance(item, dict)]
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "rows", "data", "results"):
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
