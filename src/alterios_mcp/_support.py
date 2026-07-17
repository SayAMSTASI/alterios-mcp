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
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape as _xml_escape

from .builders.common import (
    _write_service_operation,
    _manual_script_operation,
    _rest_write_operation,
    _add_comment_operation,
    _content_fields_operation,
    _file_upload_operation,
    _content_summary,
    _decode_file_payload,
    _project_icon_operation,
    _project_icon_library_operation,
    _icon_registry_summary,
    _resource_operation,
    _resource_summary,
    _security_resource_summary,
    _security_resource_operation,
    _security_payload,
    _view_field_save_payload,
    _report_template_payload,
    _report_template_has_marker,
    _operation_result_shape,
    _material_resolve_content_name_template,
    _material_edit_from_view_action,
    _material_open_form_container,
    _material_close_action_container,
    _material_save_action_container,
)
from .validators.common import (
    _validate_script_type_config,
    _assert_expected_content,
    _normalize_google_icon_svg,
    _downloaded_icon_payload_valid,
    _assert_managed_or_allowed,
    _assert_help_managed_or_allowed,
    _assert_expected_task,
    _normalize_process_script_refs,
)
from .validators.module_contract import ICON_COLOR, ICON_RENDER_SIZE, ICON_SOURCE_SIZE, validate_icon_svg

from .bulk_live import (
    execute_bulk_delete,
    execute_bulk_manual_script,
    execute_bulk_process_start,
    load_bulk_content_targets,
    normalize_bulk_ids,
)
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
from .delivery_evidence import validate_delivery_evidence
from .form_surface import analyze_form_surface
from .form_script_actions import (
    available_cell_provider_keys,
    build_manual_script_action_container,
    cell_view_id,
    find_manual_script_action,
    form_cell,
    normalize_argument_bindings,
    script_argument_keys,
    upsert_manual_script_action,
    validate_manual_script_bindings,
)
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
from .live_task_preflight import run_live_task_preflight
from .live_write import run_fast_live_write
from .profile_smoke import run_profile_smoke
from .printable_render import render_printable_pdf
from .project_health import run_project_health
from .replay_smoke import run_replay_smoke
from .runtime_info import (
    MCP_TOOL_SCHEMA_VERSION,
    build_runtime_fingerprint,
    collect_alterios_mcp_instances,
    collect_alterios_mcp_process_snapshot,
    collect_alterios_mcp_processes,
)
from .services import get_service, list_services, service_to_dict
from .stimulsoft_layout import analyze_stimulsoft_layout
from .tool_profiles import apply_tool_profile, build_tool_profile_summary
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
from .ux_contract import (
    BLOCKING_FORM_ISSUE_CODES,
    BLOCKING_MODULE_ISSUE_CODES,
    PRINTABLE_REPORT_DEFAULT,
    SCENARIO_APPLY_REQUIRES,
    UX_CONTRACT_VERSION,
)

_ACTIVE_TOOL_PROFILE: dict[str, Any] | None = None

ALTERIOS_SCRIPT_TYPES = {"web", "cron", "manual", "event", "library", "diagram"}


def _client(profile: str | None = None, project_id: str | None = None) -> AlteriosClient:
    return AlteriosClient(AlteriosConfig.from_env(profile=profile).with_project_id(project_id))


def _write_enabled() -> bool:
    return os.environ.get("ALTERIOS_MCP_ALLOW_WRITE") == "1"


def _dangerous_write_enabled() -> bool:
    return os.environ.get("ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE") == "1"


def _runtime_fingerprint() -> dict[str, Any]:
    profile = _ACTIVE_TOOL_PROFILE or build_tool_profile_summary(_decorated_tool_names())
    runtime = build_runtime_fingerprint(tool_count=int(profile["enabled_count"]))
    runtime["tool_profile"] = {
        "profile": profile["profile"],
        "registered_count": profile["input_count"],
        "enabled_count": profile["enabled_count"],
        "removed_count": profile["removed_count"],
    }
    return runtime


_TOOL_NAME_PROVIDER: Callable[[], list[str]] | None = None


def configure_tool_name_provider(provider: Callable[[], list[str]]) -> None:
    global _TOOL_NAME_PROVIDER
    _TOOL_NAME_PROVIDER = provider


def set_active_tool_profile(profile: dict[str, Any]) -> None:
    global _ACTIVE_TOOL_PROFILE
    _ACTIVE_TOOL_PROFILE = profile


def _decorated_tool_names() -> list[str]:
    return list(_TOOL_NAME_PROVIDER()) if _TOOL_NAME_PROVIDER is not None else []


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
    receipt = _verify_delivery_evidence(
        work_item_ref=work_item_ref,
        handoff_refs=[str(item).strip() for item in handoffs if str(item).strip()],
    )
    if not receipt.get("ok"):
        codes = ", ".join(str(item.get("code")) for item in receipt.get("blockers", []))
        raise ValueError(f"Gitea delivery evidence verification failed: {codes or 'unknown blocker'}.")
    return {
        "work_item_ref": work_item_ref,
        "agent_handoff_refs": [str(item).strip() for item in handoffs if str(item).strip()],
        "ux_contract_version": contract_version,
        "verification_receipt": receipt,
    }


def _required_agent_roles(required_roles: list[str] | None = None) -> list[str]:
    if required_roles is not None:
        return [str(role).strip() for role in required_roles if str(role).strip()]
    configured = os.environ.get("ALTERIOS_MCP_REQUIRED_AGENT_ROLES", "analyst,implementer,verifier")
    return [role.strip() for role in configured.split(",") if role.strip()]


def _verify_delivery_evidence(
    *,
    work_item_ref: str,
    handoff_refs: list[str],
    required_roles: list[str] | None = None,
    allow_closed: bool = False,
    dotenv_path: str | None = None,
) -> dict[str, Any]:
    config = GiteaConfig.from_env(dotenv_path or ".env")
    missing = config.missing_for_repo_call()
    if missing:
        return {
            "ok": False,
            "fingerprint": None,
            "verified_roles": [],
            "verified_comment_ids": [],
            "blockers": [{"code": "gitea_config_missing", "missing": missing}],
        }
    return validate_delivery_evidence(
        client=GiteaClient(config),
        work_item_ref=work_item_ref,
        handoff_refs=handoff_refs,
        required_roles=_required_agent_roles(required_roles),
        allow_closed=allow_closed,
    )










def _script_active_default(script_type: str, existing: dict[str, Any] | None, active: bool | None) -> bool:
    if active is not None:
        return active
    if existing and "active" in existing:
        return bool(existing["active"])
    return script_type not in {"web", "cron"}












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
    "list_alt_add": "Массовое изменение или добавление строк из списка; создание связанного элемента.",
    "menu": "Главное меню, боковое меню или раскрытие навигации; для строковых действий лучше more_vert.",
    "more_vert": "Меню дополнительных действий строки или элемента.",
    "person_add": "Добавление пользователя, сотрудника, участника или ответственного.",
    "person_check": "Проверка, подтверждение, назначение или согласование пользователя.",
    "preview": "Предпросмотр записи, печатной формы или результата перед применением.",
    "print": "Печать формы, печатная форма или PDF/вывод на печать.",
    "recycling": "Повторное использование, переработка, возврат в цикл или переобработка.",
    "rule": "Правило, проверка, регламент, условие или валидатор.",
    "save": "Сохранение формы, записи или настроек.",
    "search": "Поиск по списку или данным.",
    "sync": "Синхронизация, обновление, повторное чтение или пересчет.",
    "task_alt": "Задача процесса, завершение/контроль task.",
    "visibility": "Просмотр записи без редактирования.",
}
ICON_SEMANTIC_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
GOOGLE_ICON_NAME_RE = re.compile(r"^[a-z0-9_]{1,80}$")
ICON_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")






def _normalize_project_icon_specs(
    icon_specs: list[dict[str, str]] | None,
    *,
    include_defaults: bool,
) -> list[dict[str, str]]:
    by_semantic: dict[str, dict[str, str]] = {}
    if include_defaults:
        for semantic, google_name in PROJECT_ICON_DEFAULTS.items():
            by_semantic[semantic] = {"semantic": semantic, "google_name": google_name}
    for raw in icon_specs or []:
        if not isinstance(raw, dict):
            raise ValueError("Each icon spec must be an object.")
        semantic = str(raw.get("semantic") or "").strip().lower()
        google_name = str(raw.get("google_name") or raw.get("name") or "").strip().lower()
        if not semantic:
            raise ValueError("Icon spec semantic must not be empty.")
        if not google_name:
            google_name = PROJECT_ICON_DEFAULTS.get(semantic, semantic)
        if not ICON_SEMANTIC_RE.fullmatch(semantic):
            raise ValueError(f"Invalid icon semantic {semantic!r}. Use lower-case ascii letters, digits, and underscores.")
        if not GOOGLE_ICON_NAME_RE.fullmatch(google_name):
            raise ValueError(f"Invalid Google icon name {google_name!r}.")
        by_semantic[semantic] = {"semantic": semantic, "google_name": google_name}
    if not by_semantic:
        raise ValueError("Pass at least one icon spec or keep include_defaults=True.")
    return [by_semantic[key] for key in sorted(by_semantic)]


def _project_icon_registry_path(*, profile: str, project_id: str) -> Path:
    return (
        artifact_root()
        / "project-icons"
        / _safe_artifact_component(profile)
        / _safe_artifact_component(project_id)
        / "registry.json"
    )


def _safe_artifact_component(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("._")
    return normalized or "default"


def _relative_artifact_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(artifact_root()))
    except ValueError:
        return str(path)


def _read_project_icon_registry(*, profile: str, project_id: str) -> dict[str, Any]:
    path = _project_icon_registry_path(profile=profile, project_id=project_id)
    if not path.exists():
        return {
            "schema_version": PROJECT_ICON_SCHEMA_VERSION,
            "profile": profile,
            "project_id": project_id,
            "icons": {},
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    icons = payload.get("icons")
    if not isinstance(icons, dict):
        icons = {}
    return {
        "schema_version": payload.get("schema_version") or PROJECT_ICON_SCHEMA_VERSION,
        "profile": payload.get("profile") or profile,
        "project_id": payload.get("project_id") or project_id,
        "icons": icons,
    }


def _write_project_icon_registry(*, profile: str, project_id: str, registry: dict[str, Any]) -> str:
    path = _project_icon_registry_path(profile=profile, project_id=project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": PROJECT_ICON_SCHEMA_VERSION,
        "profile": profile,
        "project_id": project_id,
        "icons": registry.get("icons") or {},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return _relative_artifact_path(path)


def _registry_icon_current(entry: Any, *, google_name: str, size: int, color: str, style: str) -> bool:
    return (
        isinstance(entry, dict)
        and looks_like_uuid(str(entry.get("file_id") or ""))
        and entry.get("google_name") == google_name
        and entry.get("size") == size
        and str(entry.get("color") or "").lower() == color.lower()
        and entry.get("style") == style
    )


def _file_metadata_contains_id(body: Any, file_id: str) -> bool:
    if isinstance(body, dict):
        if _extract_response_id(body) == file_id:
            return True
        for key in ("items", "rows", "data", "results", "values"):
            value = body.get(key)
            if isinstance(value, list) and _file_metadata_contains_id(value, file_id):
                return True
    if isinstance(body, list):
        if body and isinstance(body[0], list):
            return any(_file_metadata_contains_id(item, file_id) for item in body[0])
        return any(_file_metadata_contains_id(item, file_id) for item in body)
    return False


def _project_icon_file_exists(client: AlteriosClient, file_id: str) -> bool:
    try:
        return _file_metadata_contains_id(client.file_metadata([file_id]).body, file_id)
    except (AlteriosRequestError, ValueError):
        return False


def _google_icon_url(*, google_name: str, style: str) -> str:
    return f"https://fonts.gstatic.com/s/i/short-term/release/{style}/{google_name}/default/24px.svg"


def _download_google_icon_svg(*, google_name: str, style: str, size: int, color: str) -> bytes:
    url = _google_icon_url(google_name=google_name, style=style)
    try:
        with urlopen(url, timeout=20) as response:
            text = response.read().decode("utf-8")
    except HTTPError as exc:
        raise ValueError(f"Google icon {google_name!r} was not found: HTTP {exc.code}.") from exc
    except URLError as exc:
        raise ValueError(f"Google icon {google_name!r} download failed: {exc.reason}.") from exc
    return _normalize_google_icon_svg(text, size=size, color=color)




def _project_icon_filename(*, semantic: str, google_name: str, size: int, color: str) -> str:
    color_slug = color.lstrip("#").upper()
    return f"codex_icon_{semantic}_{google_name}_{size}dp_{color_slug}.svg"




def _normalize_elfinder_hash(value: str | None) -> str:
    normalized = (value or PROJECT_ICON_FOLDER_HASH).strip()
    if normalized.startswith("#"):
        normalized = normalized[1:]
    if normalized.startswith("elf_"):
        normalized = normalized[4:]
    if not normalized:
        raise ValueError("elFinder folder hash must not be empty.")
    return normalized


def _file_item_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("_id") or "").strip()


def _repair_mojibake_text(value: str) -> str:
    if not any(marker in value for marker in ("Ð", "Ñ", "Ã")):
        return value
    try:
        repaired = value.encode("latin1").decode("utf-8")
    except UnicodeError:
        return value
    return repaired if repaired.strip() else value


def _file_item_name(item: dict[str, Any]) -> str:
    return _repair_mojibake_text(str(item.get("name") or item.get("filename") or "").strip())


def _file_item_extension(item: dict[str, Any]) -> str:
    return Path(_file_item_name(item)).suffix.lower()


def _is_icon_file_item(item: dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        return False
    if item.get("mime") == "directory":
        return False
    if not _file_item_id(item):
        return False
    mime = str(item.get("mime") or "").lower()
    return mime.startswith("image/") or _file_item_extension(item) in PROJECT_ICON_EXTENSIONS


def _safe_download_filename(file_id: str, name: str) -> str:
    suffix = Path(name).suffix
    stem = Path(name).stem or "icon"
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._") or "icon"
    safe_suffix = re.sub(r"[^A-Za-z0-9.]+", "", suffix) or ".bin"
    return f"{file_id}_{safe_stem}{safe_suffix}"


def _safe_icon_library_filename(name: str) -> str:
    suffix = Path(name).suffix.lower() or ".bin"
    stem = re.sub(r"^[0-9a-fA-F-]{36}_", "", Path(name).stem)
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._") or "icon"
    safe_suffix = re.sub(r"[^A-Za-z0-9.]+", "", suffix) or ".bin"
    return f"{safe_stem}{safe_suffix}"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _project_icon_library_dir(library_dir: str | None = None) -> Path:
    if library_dir:
        return Path(library_dir).expanduser().resolve()
    return (_repo_root() / PROJECT_ICON_LIBRARY_RELATIVE_DIR).resolve()


def _normalize_icon_semantic_list(semantics: list[str] | None) -> set[str] | None:
    if semantics is None:
        return None
    selected: set[str] = set()
    for raw in semantics:
        semantic = str(raw or "").strip().lower()
        if not semantic:
            continue
        if not ICON_SEMANTIC_RE.fullmatch(semantic):
            raise ValueError(f"Invalid icon semantic {semantic!r}. Use lower-case ascii letters, digits, and underscores.")
        selected.add(semantic)
    return selected or None


def _icon_mime_type(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"




def _download_elfinder_icon_file(client: AlteriosClient, icon: dict[str, Any]) -> tuple[bytes, str, str]:
    filename = str(icon.get("name") or "icon")
    source = ""
    if icon.get("url"):
        source = str(icon["url"])
        data, content_type = client.download_file_url(source)
    else:
        source = str(icon["file_id"])
        data, content_type = client.download_file(source)
    if not _downloaded_icon_payload_valid(data, filename=filename, content_type=content_type):
        raise ValueError(
            f"Downloaded icon {filename!r} from {source!r} is not a valid icon payload; "
            "the response looks empty or HTML."
        )
    return data, content_type, source


def _read_project_icon_library(
    *,
    library_dir: str | None = None,
    semantics: list[str] | None = None,
) -> tuple[Path, list[dict[str, Any]]]:
    base_dir = _project_icon_library_dir(library_dir)
    selected = _normalize_icon_semantic_list(semantics)
    if not base_dir.exists():
        raise ValueError(f"Project icon library directory was not found: {base_dir}")

    manifest_path = base_dir / "manifest.json"
    manifest_icons: list[dict[str, Any]] = []
    if manifest_path.exists():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw_icons = payload.get("icons") if isinstance(payload, dict) else None
        if not isinstance(raw_icons, list):
            raise ValueError(f"Invalid icon library manifest: {manifest_path}")
        for raw in raw_icons:
            if isinstance(raw, dict):
                manifest_icons.append(raw)
    else:
        for path in sorted(base_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in PROJECT_ICON_EXTENSIONS:
                manifest_icons.append({"semantic": _icon_semantic_guess_from_filename(path.name), "filename": path.name})

    icons_by_semantic: dict[str, dict[str, Any]] = {}
    for raw in manifest_icons:
        filename = _safe_icon_library_filename(str(raw.get("filename") or raw.get("name") or ""))
        path = base_dir / filename
        semantic = str(raw.get("semantic") or _icon_semantic_guess_from_filename(filename)).strip().lower()
        if not ICON_SEMANTIC_RE.fullmatch(semantic):
            raise ValueError(f"Invalid icon semantic {semantic!r} in {manifest_path if manifest_path.exists() else base_dir}.")
        if selected and semantic not in selected:
            continue
        if not path.is_file():
            raise ValueError(f"Icon library file for semantic {semantic!r} was not found: {path}")
        data = path.read_bytes()
        content_type = str(raw.get("mime") or _icon_mime_type(filename))
        if not _downloaded_icon_payload_valid(data, filename=filename, content_type=content_type):
            raise ValueError(f"Icon library file {path} is not a valid icon payload.")
        if path.suffix.lower() == ".svg":
            svg_contract = validate_icon_svg(data)
            if not svg_contract["ok"]:
                raise ValueError(
                    f"Icon library file {path} violates the SVG contract: "
                    f"width={svg_contract.get('width')}, height={svg_contract.get('height')}, "
                    f"colors={svg_contract.get('colors')}."
                )
        icons_by_semantic[semantic] = {
            "semantic": semantic,
            "filename": filename,
            "path": path,
            "mime": content_type,
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "source_size": ICON_SOURCE_SIZE,
            "render_size": ICON_RENDER_SIZE,
            "color": ICON_COLOR,
            "file_contract_verified": path.suffix.lower() == ".svg",
            "usage_hint": raw.get("usage_hint") or _icon_usage_hint(semantic),
        }

    if selected:
        missing = sorted(selected.difference(icons_by_semantic))
        if missing:
            raise ValueError(f"Icon library does not contain requested semantics: {', '.join(missing)}")
    if not icons_by_semantic:
        raise ValueError(f"Icon library contains no icon files: {base_dir}")
    return base_dir, [icons_by_semantic[key] for key in sorted(icons_by_semantic)]


def _icon_semantic_guess_from_filename(name: str) -> str:
    stem = Path(name).stem.lower()
    stem = re.sub(r"_[0-9]+$", "", stem)
    stem = re.sub(r"[^a-z0-9_ -]+", "_", stem)
    stem = re.sub(r"[-\s]+", "_", stem)
    stem = re.sub(r"_\d{2}dp(_.*)?$", "", stem)
    stem = re.sub(r"_[0-9a-f]{6}_fill[01]_wght[0-9]+_grad-?[0-9]+_opsz[0-9]+(_.*)?$", "", stem)
    stem = re.sub(r"_+", "_", stem).strip("_")
    if stem in {"content_copy_17dp"}:
        stem = "content_copy"
    return stem or "icon"


def _icon_usage_hint(semantic: str) -> str:
    return PROJECT_ICON_USAGE_HINTS.get(
        semantic,
        "Использовать только после проверки смысла действия; назначение выведено из имени файла.",
    )


def _summarize_elfinder_icon_item(item: dict[str, Any]) -> dict[str, Any]:
    file_id = _file_item_id(item)
    name = _file_item_name(item)
    semantic = _icon_semantic_guess_from_filename(name)
    return {
        "file_id": file_id,
        "name": name,
        "semantic_guess": semantic,
        "usage_hint": _icon_usage_hint(semantic),
        "mime": item.get("mime"),
        "size": item.get("size"),
        "hash": item.get("hash"),
        "phash": item.get("phash"),
        "url": item.get("url"),
        "extension": _file_item_extension(item),
    }


def _elfinder_files(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        return []
    return [item for item in body.get("files") or [] if isinstance(item, dict)]


def _elfinder_direct_children(body: Any, parent_hash: str) -> list[dict[str, Any]]:
    return [item for item in _elfinder_files(body) if item.get("phash") == parent_hash]


def _find_child_folder(body: Any, *, parent_hash: str, folder_name: str) -> dict[str, Any] | None:
    expected = folder_name.strip().lower()
    for item in _elfinder_direct_children(body, parent_hash):
        if item.get("mime") == "directory" and _file_item_name(item).lower() == expected:
            return item
    return None


def _resolve_elfinder_icon_folder(client: AlteriosClient, *, folder_hash: str, icons_folder_name: str | None) -> tuple[str, dict[str, Any]]:
    normalized = _normalize_elfinder_hash(folder_hash)
    body = client.file_elfinder(command="open", target=normalized).body
    cwd = body.get("cwd") if isinstance(body, dict) else None
    cwd_name = _file_item_name(cwd) if isinstance(cwd, dict) else None
    if not icons_folder_name:
        return normalized, {"source_hash": normalized, "folder_hash": normalized, "folder_name": cwd_name}
    if isinstance(cwd, dict) and _file_item_name(cwd).lower() == icons_folder_name.strip().lower():
        return normalized, {"source_hash": normalized, "folder_hash": normalized, "folder_name": _file_item_name(cwd)}
    folder = _find_child_folder(body, parent_hash=normalized, folder_name=icons_folder_name)
    if not folder or not folder.get("hash"):
        raise ValueError(f"Folder {icons_folder_name!r} was not found under elFinder target {normalized!r}.")
    return str(folder["hash"]), {
        "source_hash": normalized,
        "folder_hash": str(folder["hash"]),
        "folder_name": _file_item_name(folder),
    }


def _collect_elfinder_icon_items(
    client: AlteriosClient,
    *,
    folder_hash: str,
    recurse: bool,
    max_files: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    queue = [folder_hash]
    seen_dirs: set[str] = set()
    icons: list[dict[str, Any]] = []
    directories: list[dict[str, Any]] = []
    while queue:
        current_hash = queue.pop(0)
        if current_hash in seen_dirs:
            continue
        seen_dirs.add(current_hash)
        body = client.file_elfinder(command="open", target=current_hash).body
        for item in _elfinder_direct_children(body, current_hash):
            if item.get("mime") == "directory":
                directories.append(
                    {
                        "hash": item.get("hash"),
                        "name": _file_item_name(item),
                        "phash": item.get("phash"),
                    }
                )
                if recurse and item.get("hash"):
                    queue.append(str(item["hash"]))
                continue
            if _is_icon_file_item(item):
                icons.append(_summarize_elfinder_icon_item(item))
                if len(icons) > max_files:
                    raise ValueError(f"Refusing to process more than {max_files} icon files.")
    return icons, directories


def _group_icon_catalog(icons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for icon in icons:
        semantic = str(icon.get("semantic_guess") or "icon")
        group = grouped.setdefault(
            semantic,
            {
                "semantic": semantic,
                "usage_hint": _icon_usage_hint(semantic),
                "count": 0,
                "representative_file_id": icon.get("file_id"),
                "representative_name": icon.get("name"),
                "mimes": set(),
            },
        )
        group["count"] += 1
        if icon.get("mime"):
            group["mimes"].add(str(icon["mime"]))
    result: list[dict[str, Any]] = []
    for semantic in sorted(grouped):
        group = grouped[semantic]
        result.append(
            {
                **{key: value for key, value in group.items() if key != "mimes"},
                "mimes": sorted(group["mimes"]),
                "standard_semantic": semantic in PROJECT_ICON_DEFAULTS,
                "standard_google_name": PROJECT_ICON_DEFAULTS.get(semantic),
            }
        )
    return result


def _write_icon_usage_guide(path: Path, *, profile: str, project_id: str, catalog: list[dict[str, Any]], icons: list[dict[str, Any]]) -> None:
    lines = [
        "# Каталог иконок проекта",
        "",
        "Файл сгенерирован MCP по файловому менеджеру Alterios. Реальные адреса и токены не сохраняются.",
        "",
        f"- profile: `{profile}`",
        f"- project_id: `{project_id}`",
        f"- уникальных назначений: {len(catalog)}",
        f"- файлов иконок: {len(icons)}",
        "",
        "## Правила",
        "",
        "- `iconId` в формах, группах и действиях должен быть UUID файла из проекта.",
        "- Для новых действий сначала использовать стандарт Google Fonts Icons: size 16, color #4B77D1.",
        "- Существующую проектную иконку можно переиспользовать, если ее смысл совпадает с действием.",
        "- Если назначение выведено только из имени файла, перед применением нужно проверить UI-смысл.",
        "",
        "## Когда какую использовать",
        "",
        "| Семантика | Когда использовать | Файлов | Пример |",
        "|---|---|---:|---|",
    ]
    for item in catalog:
        lines.append(
            "| "
            + str(item["semantic"]).replace("|", "\\|")
            + " | "
            + str(item["usage_hint"]).replace("|", "\\|")
            + " | "
            + str(item["count"])
            + " | "
            + str(item.get("representative_name") or "").replace("|", "\\|")
            + " |"
        )
    lines.extend(
        [
            "",
            "## Файлы",
            "",
            "| iconId | Файл | Семантика | Когда использовать |",
            "|---|---|---|---|",
        ]
    )
    for icon in icons:
        lines.append(
            "| "
            + str(icon.get("file_id") or "").replace("|", "\\|")
            + " | "
            + str(icon.get("name") or "").replace("|", "\\|")
            + " | "
            + str(icon.get("semantic_guess") or "").replace("|", "\\|")
            + " | "
            + str(icon.get("usage_hint") or "").replace("|", "\\|")
            + " |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _filesystem_icon_candidates(icons: list[dict[str, Any]], *, semantic: str, google_name: str) -> list[dict[str, Any]]:
    wanted = {semantic, google_name}
    return [icon for icon in icons if str(icon.get("semantic_guess") or "") in wanted]






def _resource_diff(existing: dict[str, Any] | None, payload: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    diff = []
    for key in keys:
        before = existing.get(key) if existing else None
        after = payload.get(key)
        diff.append({"field": key, "before": before, "after": after, "changed": before != after})
    return diff






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


VIEW_DEFAULT_RANGES = {"day", "week", "month", "quarter", "year"}
LEAFLET_MARKER_ICON_SOURCES = {"default", "img", "field"}


def _validate_view_format_settings(format_name: str | None, settings: dict[str, Any]) -> list[str]:
    """Return non-blocking warnings and raise for settings known to produce broken views."""
    normalized_format = (format_name or "table").strip().lower()
    warnings: list[str] = []
    if normalized_format == "calendar":
        if not settings.get("title"):
            warnings.append("calendar UI preview requires settings.title to build visible event names.")
        if not settings.get("startDate"):
            warnings.append("calendar UI preview requires settings.startDate.")
        return warnings
    if normalized_format == "gantt":
        default_view = settings.get("defaultView")
        if default_view not in VIEW_DEFAULT_RANGES:
            raise ValueError("gantt view requires settings.defaultView to be one of: day, week, month, quarter, year.")
        for key in ("date1", "date2"):
            value = settings.get(key)
            if not isinstance(value, dict) or not str(value.get("field") or "").strip():
                raise ValueError(f"gantt view requires settings.{key}.field.")
        return warnings
    if normalized_format == "leaflet":
        geo_fields = settings.get("geoFields") or []
        if not isinstance(geo_fields, list):
            raise ValueError("leaflet view requires settings.geoFields to be a list.")
        for index, geo_field in enumerate(geo_fields):
            if not isinstance(geo_field, dict):
                raise ValueError(f"leaflet view geoFields[{index}] must be an object.")
            if not str(geo_field.get("name") or "").strip():
                raise ValueError(f"leaflet view geoFields[{index}].name is required.")
            marker_icons = geo_field.get("markerIcons")
            if marker_icons not in LEAFLET_MARKER_ICON_SOURCES:
                raise ValueError(
                    f"leaflet view geoFields[{index}].markerIcons must be one of: default, img, field."
                )
        return warnings
    return warnings


def _view_format_readback_warnings(
    format_name: str | None,
    requested_settings: dict[str, Any],
    readback_settings: dict[str, Any] | None,
) -> list[str]:
    normalized_format = (format_name or "table").strip().lower()
    readback_settings = readback_settings or {}
    warnings: list[str] = []
    if normalized_format == "calendar":
        for key in ("startDate", "endDate"):
            if requested_settings.get(key) and readback_settings.get(key) != requested_settings.get(key):
                warnings.append(f"calendar settings.{key} was requested but was not present in readback.")
    return warnings


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
        if attribute and (
            field.get("attribute") == attribute
            or field.get("contentAttribute") == attribute
            or field.get("mname") == attribute
        ):
            return field
    return None


def _view_entity_main_content_type_id(entity: dict[str, Any] | None) -> str | None:
    if not isinstance(entity, dict):
        return None
    config = entity.get("config")
    if not isinstance(config, dict):
        return None
    content_type_ids = config.get("contentTypesIds")
    if isinstance(content_type_ids, list):
        for item in content_type_ids:
            normalized = str(item or "").strip()
            if normalized:
                return normalized
    content_type_id = config.get("contentTypeId")
    if content_type_id:
        return str(content_type_id).strip() or None
    return None


def _view_entity_field_add_request(entity: dict[str, Any] | None, *, attribute: str | None, content_type_field_id: str | None) -> dict[str, Any]:
    entity_id = str((entity or {}).get("_id") or "").strip()
    if not entity_id:
        raise ValueError("View entity readback does not contain _id.")
    request: dict[str, Any] = {"entityId": entity_id}
    if content_type_field_id:
        request["contentTypeFieldId"] = content_type_field_id
        return request
    if not attribute:
        return request
    request["attribute"] = attribute
    return request


def _normalize_view_field_payload_for_entity(
    payload: dict[str, Any],
    entity: dict[str, Any] | None,
    *,
    attribute: str | None,
) -> dict[str, Any]:
    normalized = dict(payload)
    if (entity or {}).get("type") != "content" or normalized.get("contentTypeFieldId"):
        return normalized
    effective_attribute = attribute or normalized.get("contentAttribute") or normalized.get("attribute")
    if not effective_attribute:
        return normalized
    content_type_id = _view_entity_main_content_type_id(entity)
    if not content_type_id:
        return normalized
    normalized["contentTypeId"] = content_type_id
    normalized["contentAttribute"] = effective_attribute
    normalized.pop("attribute", None)
    return normalized




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






def _report_has_dashboard_page(report: Any) -> bool:
    template = _report_template_payload(report)
    if not isinstance(template, dict):
        return False
    page = (template.get("Pages") or {}).get("0")
    return isinstance(page, dict) and page.get("Ident") == "StiDashboard"


def _report_has_printable_page(report: Any) -> bool:
    template = _report_template_payload(report)
    if not isinstance(template, dict):
        return False
    pages = template.get("Pages") or {}
    page_values = pages.values() if isinstance(pages, dict) else pages if isinstance(pages, list) else []
    return any(
        isinstance(page, dict) and page.get("Ident") == "StiPage"
        for page in page_values
    )




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


def _has_encrypted_project_database_connection(template: dict[str, Any] | None) -> bool:
    if not isinstance(template, dict):
        return False
    for value in _walk_values(template):
        if (
            isinstance(value, dict)
            and value.get("ServiceName") == "Project Database"
            and bool(value.get("ConnectionStringEncrypted"))
        ):
            return True
    return False


def _dashboard_table_summaries(template: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(template, dict):
        return []
    tables: list[dict[str, Any]] = []
    for value in _walk_values(template):
        if not isinstance(value, dict) or value.get("Ident") != "StiTableElement":
            continue
        columns = value.get("Columns")
        column_items = list(columns.values()) if isinstance(columns, dict) else []
        expressions = [
            str(column.get("Expression") or "")
            for column in column_items
            if isinstance(column, dict) and column.get("Expression")
        ]
        labels = [
            str(column.get("Label") or "")
            for column in column_items
            if isinstance(column, dict) and column.get("Label")
        ]
        tables.append(
            {
                "name": value.get("Name"),
                "column_count": len(column_items),
                "expressions": expressions,
                "labels": labels,
            }
        )
    return tables


def _printable_band_summary(template: dict[str, Any] | None) -> dict[str, Any]:
    idents = [
        str(value.get("Ident") or "")
        for value in _walk_values(template)
        if isinstance(value, dict) and str(value.get("Ident") or "").endswith("Band")
    ] if isinstance(template, dict) else []
    data_expressions: list[str] = []
    if isinstance(template, dict):
        for value in _walk_values(template):
            if not isinstance(value, dict) or value.get("Ident") != "StiText":
                continue
            text_value = value.get("Text")
            if isinstance(text_value, dict):
                text_value = text_value.get("Value")
            if isinstance(text_value, str) and "{data." in text_value:
                data_expressions.append(text_value)
    return {
        "bands": sorted(set(idents)),
        "has_report_title": "StiReportTitleBand" in idents,
        "has_page_header": "StiPageHeaderBand" in idents,
        "has_data_band": "StiDataBand" in idents,
        "has_page_footer": "StiPageFooterBand" in idents,
        "data_expressions": data_expressions,
    }


def _printable_smoke_rows(template: dict[str, Any], count: int = 3) -> list[dict[str, Any]]:
    expressions = _printable_band_summary(template)["data_expressions"]
    fields = []
    for expression in expressions:
        match = re.fullmatch(r"\{data\.([^{}]+)\}", expression)
        if match and match.group(1) not in fields:
            fields.append(match.group(1))
    if not fields:
        raise ValueError("Printable report has no {data.field} expressions for render validation.")
    return [
        {field: f"Smoke {row_index + 1}: {field}" for field in fields}
        for row_index in range(max(1, count))
    ]


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
    table_summaries = _dashboard_table_summaries(template)
    printable = _printable_band_summary(template)
    return {
        "has_template": isinstance(template, dict),
        "has_dashboard_page": _report_has_dashboard_page(report),
        "has_printable_page": _report_has_printable_page(report),
        "has_project_database": _has_project_database(template),
        "has_encrypted_project_database_connection": _has_encrypted_project_database_connection(template),
        "table_component_count": len(table_summaries),
        "table_has_columns": any(item["column_count"] > 0 for item in table_summaries),
        "table_columns": table_summaries,
        "printable": printable,
        "marker": marker,
        "marker_matches": expected_marker is None or marker == expected_marker,
        "view_name_matches": expected_view_name is None or _contains_text(template, expected_view_name),
    }




def _response_body(value: Any) -> Any:
    if isinstance(value, dict) and "body" in value:
        return value.get("body")
    return value


def _managed_description(text: str | None, fallback: str) -> str:
    description = (text or fallback).strip()
    if MANAGED_MARKER in description:
        return description
    return f"{MANAGED_MARKER}: {description}"


def _material_module_operation(
    *,
    module_name: str,
    field_name_prefix: str,
    fields: list[dict[str, Any]],
    content_type_id: str | None,
    view_id: str | None,
    add_form_id: str | None,
    edit_form_id: str | None,
    view_form_id: str | None,
    list_form_id: str | None,
    group_id: str | None,
    parent_group_id: str | None,
    names: dict[str, str],
    content_name_template: str | None,
    content_type_description: str | None,
    icon_id: str | None,
    add_icon_id: str | None,
    edit_icon_id: str | None,
    view_icon_id: str | None,
    delete_icon_id: str | None,
    menu_icon_id: str | None,
    close_icon_id: str | None,
    save_icon_id: str | None,
    delivery_evidence: dict[str, Any] | None,
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
        "viewFormId": view_form_id,
        "listFormId": list_form_id,
        "groupId": group_id,
        "parentGroupId": parent_group_id,
        "names": names,
        "contentNameTemplate": content_name_template,
        "contentTypeDescription": content_type_description,
        "icons": {
            "group": icon_id,
            "add": add_icon_id,
            "edit": edit_icon_id,
            "view": view_icon_id,
            "delete": delete_icon_id,
            "menu": menu_icon_id,
            "close": close_icon_id,
            "save": save_icon_id,
        },
        "allowUnmanagedUpdate": allow_unmanaged_update,
        "deliveryEvidence": delivery_evidence,
    }
    return _resource_operation(
        name="SCENARIO create_material_module",
        kind="scenario_material_module",
        risk_level="write",
        method="POST",
        path="scenario://material-module",
        summary=(
            "Create or update a complete Alterios material module: content type, fields, view, "
            "add/edit/view/list forms, and menu group."
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
        if field_type != "date":
            persistent_help = str(normalized_field.pop("help", "") or "").strip()
            persistent_description = str(normalized_field.pop("description", "") or "").strip()
            if not str(normalized_field.get("tooltip") or "").strip():
                normalized_field["tooltip"] = (
                    persistent_help
                    or persistent_description
                    or f"Укажите значение поля «{name}»."
                )
        else:
            if not str(normalized_field.get("description") or "").strip():
                normalized_field["description"] = f"Дата для поля «{name}»."
            if not str(normalized_field.get("tooltip") or "").strip():
                normalized_field["tooltip"] = f"Укажите дату для поля «{name}»."
        field_settings = dict(normalized_field.get("settings") or {})
        field_settings.setdefault("valueCount", 1)
        if field_type == "text":
            field_settings.setdefault("widget", "text")
            field_settings.setdefault("maxLength", 2000 if field_settings.get("widget") == "textarea" else 255)
        if field_type == "number":
            field_settings.setdefault("widget", "text")
            field_settings.setdefault("maxLength", 255)
            field_settings.setdefault("precision", 2)
            field_settings.setdefault("defaultValue", [None])
        normalized_field["settings"] = field_settings
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
        "edit_form": overrides.get("edit_form") or f"{module_name}. Редактирование",
        "view_form": overrides.get("view_form") or f"{module_name}. Просмотр",
        "list_form": overrides.get("list_form") or module_name,
        "group": overrides.get("group") or module_name,
        "add_page_title": overrides.get("add_page_title") or f"Добавить {module_name}",
        "edit_page_title": overrides.get("edit_page_title") or module_name,
        "view_page_title": overrides.get("view_page_title") or module_name,
        "list_page_title": overrides.get("list_page_title") or overrides.get("list_form") or module_name,
    }


def _material_flex_styles() -> dict[str, Any]:
    return {"flexGrow": 1, "flexBasis": 0, "flexShrink": 1, "flexBasisUnit": "%"}


def _material_row_styles() -> dict[str, Any]:
    return _material_flex_styles()


def _material_content_display_fields(fields: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        field["mname"]: {
            "order": int(field.get("order", index)),
            "title": field["name"],
            "filter": {"mode": "standard", "enabled": True},
        }
        for index, field in enumerate(fields)
    }


def _material_view_display_fields(
    fields: list[dict[str, Any]],
    *,
    read_only: bool = False,
) -> dict[str, Any]:
    display: dict[str, Any] = {"_id": {"order": 0, "hidden": True}, "_id0": {"order": 0, "hidden": True}}
    for index, field in enumerate(fields, start=1):
        field_order = int(field.get("order", index - 1)) + 1
        config: dict[str, Any] = {
            "order": field_order,
            "hidden": False,
            "title": field["name"],
            "filter": {"mode": "standard", "enabled": True},
        }
        if read_only:
            config["inputConfig"] = None
            config["outputConfig"] = {"outputType": "default"}
        display[field["view_mname"]] = config
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
                "displaying": {
                    "list": {"pageSizeOptions": [], "showLineNumbers": False},
                    "fields": _material_view_display_fields(fields, read_only=not editable),
                    "header": {},
                    "editForm": {},
                },
                "cellActionContainers": [],
            }
        ],
        "styles": _material_row_styles(),
        "reverse": False,
    }




def _material_view_form_row(
    *,
    module_name: str,
    view_id: str,
    fields: list[dict[str, Any]],
    edit_form_id: str,
    edit_form_name: str,
    view_entity_id: str,
    edit_icon_id: str | None,
) -> dict[str, Any]:
    row = _material_view_data_row(module_name, view_id, fields, editable=False)
    row["cells"][0]["cellActionContainers"] = [
        _material_edit_from_view_action(
            icon_id=edit_icon_id,
            edit_form_id=edit_form_id,
            edit_form_name=edit_form_name,
            view_entity_id=view_entity_id,
        )
    ]
    return row


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
                "displaying": {"fields": {}, "header": {}},
                "cellActionContainers": [],
            }
        ],
        "styles": _material_row_styles(),
        "reverse": False,
    }




def _material_row_form_menu_item(
    *,
    title: str,
    icon_id: str | None,
    form_id: str,
    form_name: str,
    view_entity_id: str,
    default: bool = False,
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
        "position": "toolbar",
        "default": default,
        "conditions": [],
    }
    if icon_id:
        container["iconId"] = icon_id
    return container


def _material_row_delete_menu_item(icon_id: str | None, view_entity_id: str) -> dict[str, Any]:
    container: dict[str, Any] = {
        "type": "action",
        "title": "Удалить",
        "styles": {},
        "actions": [
            {
                "type": "delete_contents",
                "openInDialog": False,
                "openInNewTab": False,
                "viewEntityId": view_entity_id,
                "argumentsConfig": {},
            }
        ],
        "position": "toolbar",
        "conditions": [],
    }
    if icon_id:
        container["iconId"] = icon_id
    return container


def _material_row_menu_container(
    *,
    menu_icon_id: str | None,
    edit_icon_id: str | None,
    view_icon_id: str | None,
    delete_icon_id: str | None,
    edit_form_id: str,
    edit_form_name: str,
    view_form_id: str,
    view_form_name: str,
    view_entity_id: str,
) -> dict[str, Any]:
    container: dict[str, Any] = {
        "type": "menu",
        "title": "",
        "tooltip": "Действия",
        "styles": {},
        "actions": [],
        "position": "toolbar",
        "conditions": [],
        "containers": [
            _material_row_form_menu_item(
                title="Редактировать",
                icon_id=edit_icon_id,
                form_id=edit_form_id,
                form_name=edit_form_name,
                view_entity_id=view_entity_id,
            ),
            _material_row_form_menu_item(
                title="Просмотр",
                icon_id=view_icon_id,
                form_id=view_form_id,
                form_name=view_form_name,
                view_entity_id=view_entity_id,
                default=True,
            ),
            _material_row_delete_menu_item(delete_icon_id, view_entity_id),
        ],
    }
    if menu_icon_id:
        container["iconId"] = menu_icon_id
    return container






def _material_edit_form_actions(*, close_icon_id: str | None, save_icon_id: str | None) -> list[dict[str, Any]]:
    return [_material_close_action_container(close_icon_id), _material_save_action_container(save_icon_id)]


def _material_view_data_list_row(
    *,
    module_name: str,
    view_id: str,
    view_entity_id: str,
    add_form_id: str,
    add_form_name: str,
    edit_form_id: str,
    edit_form_name: str,
    view_form_id: str,
    view_form_name: str,
    fields: list[dict[str, Any]],
    add_icon_id: str | None,
    edit_icon_id: str | None,
    view_icon_id: str | None,
    delete_icon_id: str | None,
    menu_icon_id: str | None,
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
                    "fields": _material_view_display_fields(fields, read_only=True),
                    "header": {},
                    "editForm": {},
                },
                "cellActionContainers": [
                    _material_open_form_container(
                        tooltip="Добавить",
                        icon_id=add_icon_id,
                        form_id=add_form_id,
                        form_name=add_form_name,
                        view_entity_id=view_entity_id,
                        position="top_left",
                        default=True,
                    )
                ],
                "valueActionContainers": [
                    _material_row_menu_container(
                        menu_icon_id=menu_icon_id,
                        edit_icon_id=edit_icon_id,
                        view_icon_id=view_icon_id,
                        delete_icon_id=delete_icon_id,
                        edit_form_id=edit_form_id,
                        edit_form_name=edit_form_name,
                        view_form_id=view_form_id,
                        view_form_name=view_form_name,
                        view_entity_id=view_entity_id,
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
    view_form_id: str | None,
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
        "view": _find_form(client, form_id=view_form_id, name=names["view_form"]),
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
    view_form_id: str | None,
    list_form_id: str | None,
    group_id: str | None,
    parent_group_id: str | None,
    icon_id: str | None,
    add_icon_id: str | None,
    edit_icon_id: str | None,
    view_icon_id: str | None,
    delete_icon_id: str | None,
    menu_icon_id: str | None,
    close_icon_id: str | None,
    save_icon_id: str | None,
) -> dict[str, Any]:
    planned_content_type_id = content_type_id or "$content_type_id"
    planned_view_id = view_id or "$view_id"
    planned_view_entity_id = "$view_entity_id"
    planned_add_form_id = add_form_id or "$add_form_id"
    planned_edit_form_id = edit_form_id or "$edit_form_id"
    planned_view_form_id = view_form_id or "$view_form_id"
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
            "upsert_view_form",
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
            "format": "table",
            "settings": {
                "engineVersion": "v2",
                "title": fields[0]["view_mname"],
            },
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
                "page_title": names["add_page_title"],
                "form_id": add_form_id,
                "tabs": [{"name": None, "rows": [_material_content_form_row(module_name, planned_content_type_id, fields)]}],
                "formActionContainers": _material_edit_form_actions(
                    close_icon_id=close_icon_id,
                    save_icon_id=save_icon_id,
                ),
            },
            "edit": {
                "name": names["edit_form"],
                "page_title": names["edit_page_title"],
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
                "formActionContainers": _material_edit_form_actions(
                    close_icon_id=close_icon_id,
                    save_icon_id=save_icon_id,
                ),
            },
            "view": {
                "name": names["view_form"],
                "page_title": names["view_page_title"],
                "form_id": view_form_id,
                "tabs": [
                    {
                        "name": None,
                        "rows": [
                            _material_view_form_row(
                                module_name=module_name,
                                view_id=planned_view_id,
                                fields=fields,
                                edit_form_id=planned_edit_form_id,
                                edit_form_name=names["edit_form"],
                                view_entity_id=planned_view_entity_id,
                                edit_icon_id=edit_icon_id,
                            )
                        ],
                    }
                ],
                "formActionContainers": [_material_close_action_container(close_icon_id)],
            },
            "list": {
                "name": names["list_form"],
                "page_title": names["list_page_title"],
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
                                view_form_id=planned_view_form_id,
                                view_form_name=names["view_form"],
                                fields=fields,
                                add_icon_id=add_icon_id,
                                edit_icon_id=edit_icon_id,
                                view_icon_id=view_icon_id,
                                delete_icon_id=delete_icon_id,
                                menu_icon_id=menu_icon_id,
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
    delivery_evidence: dict[str, Any] | None,
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
        "deliveryEvidence": delivery_evidence,
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
        str(index): {
            "Name": column["name"],
            "NameInSource": column["name"],
            "Alias": column["alias"],
            "Type": column["type"],
        }
        for index, column in enumerate(columns)
    }
    table_columns = _dashboard_table_columns(columns)
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
                    "Ident": "StiCustomDatabase",
                    "Name": source_view_name,
                    "Alias": "Project Database",
                    "CastToColumnType": "CastToColumnType",
                    "ServiceName": "Project Database",
                    "ConnectionString": connection,
                }
            },
            "DataSources": {
                "0": {
                    "Ident": "StiCustomSource",
                    "Name": "data",
                    "Alias": source_view_name,
                    "NameInSource": source_view_name,
                    "ServiceName": "Project Database",
                    "SqlCommand": "data",
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
                        "Columns": table_columns,
                        "HeaderFont": ";10;Bold;",
                        "FooterFont": ";10;;",
                        "Title": {"Text": "", "Visible": False},
                        "DashboardInteraction": {
                            "Ident": "Table",
                            "OnHover": "ShowToolTip",
                            "OnClick": "ApplyFilter",
                            "HyperlinkDestination": "NewTab",
                        },
                        "SizeMode": "Fit",
                        "CornerRadius": "0, 0, 0, 0",
                        "Shadow": ";;;",
                    },
                },
            }
        },
    }


def _project_database_printable_template(
    *,
    report_name: str,
    marker: str,
    source_view_id: str,
    source_view_name: str,
    columns: list[dict[str, str]],
) -> dict[str, Any]:
    visible_columns = _visible_report_columns(columns)
    widths = _printable_column_widths(visible_columns)
    connection = json.dumps(
        {"type": "view-data-v2", "filter": {"viewId": source_view_id}},
        ensure_ascii=False,
        sort_keys=True,
    )
    column_items = {
        str(index): {
            "Name": column["name"],
            "NameInSource": column["name"],
            "Alias": column["alias"],
            "Type": column["type"],
        }
        for index, column in enumerate(visible_columns)
    }
    header_components: dict[str, dict[str, Any]] = {}
    data_components: dict[str, dict[str, Any]] = {}
    left = 0.0
    for index, (column, width) in enumerate(zip(visible_columns, widths, strict=True)):
        rectangle = f"{left:.3f},0,{width:.3f},0.8"
        common = {
            "ClientRectangle": rectangle,
            "Border": "All;;;;;;;solid:Black",
            "VertAlignment": "Center",
            "CanGrow": True,
            "WordWrap": True,
        }
        header_components[str(index)] = {
            "Ident": "StiText",
            "Name": f"Header_{index + 1}",
            **common,
            "Text": {"Value": column["alias"]},
            "HorAlignment": "Center",
            "Font": ";9;Bold;",
            "Brush": "solid:245,247,250",
            "TextBrush": "solid:Black",
        }
        data_components[str(index)] = {
            "Ident": "StiText",
            "Name": f"Data_{index + 1}",
            **common,
            "Text": {"Value": f"{{data.{column['name']}}}"},
            "Font": ";9;;",
            "GrowToHeight": True,
            "TextBrush": "solid:Black",
        }
        left += width
    return {
        "CodexMarker": marker,
        "ReportName": report_name,
        "ReportAlias": report_name,
        "ReportUnit": "Centimeters",
        "Alterios": {
            "sourceViewId": source_view_id,
            "sourceViewName": source_view_name,
            "templateKind": "printable_project_database",
        },
        "Dictionary": {
            "Databases": {
                "0": {
                    "Ident": "StiCustomDatabase",
                    "Name": source_view_name,
                    "Alias": "Project Database",
                    "CastToColumnType": "CastToColumnType",
                    "ServiceName": "Project Database",
                    "ConnectionString": connection,
                }
            },
            "DataSources": {
                "0": {
                    "Ident": "StiCustomSource",
                    "Name": "data",
                    "Alias": source_view_name,
                    "NameInSource": source_view_name,
                    "ServiceName": "Project Database",
                    "SqlCommand": "data",
                    "Columns": column_items,
                }
            },
        },
        "Pages": {
            "0": {
                "Ident": "StiPage",
                "Name": "PrintableRegistry",
                "Width": 19,
                "Height": 27.7,
                "Components": {
                    "0": {
                        "Ident": "StiReportTitleBand",
                        "Name": "ReportTitle",
                        "ClientRectangle": "0,0,19,1.4",
                        "CanGrow": True,
                        "Components": {
                            "0": {
                                "Ident": "StiText",
                                "Name": "ReportTitleText",
                                "ClientRectangle": "0,0,19,1.2",
                                "Text": {"Value": report_name},
                                "HorAlignment": "Center",
                                "VertAlignment": "Center",
                                "Font": ";16;Bold;",
                                "TextBrush": "solid:Black",
                            }
                        },
                    },
                    "1": {
                        "Ident": "StiPageHeaderBand",
                        "Name": "PageHeader",
                        "ClientRectangle": "0,0,19,0.8",
                        "CanGrow": True,
                        "Components": header_components,
                    },
                    "2": {
                        "Ident": "StiDataBand",
                        "Name": "DataBand",
                        "ClientRectangle": "0,0,19,0.8",
                        "CanGrow": True,
                        "CanBreak": True,
                        "DataSourceName": "data",
                        "Components": data_components,
                    },
                    "3": {
                        "Ident": "StiPageFooterBand",
                        "Name": "PageFooter",
                        "ClientRectangle": "0,0,19,0.6",
                        "Components": {
                            "0": {
                                "Ident": "StiText",
                                "Name": "PageNumber",
                                "ClientRectangle": "0,0,19,0.6",
                                "Text": {"Value": "Страница {PageNumber} из {TotalPageCount}"},
                                "HorAlignment": "Right",
                                "VertAlignment": "Center",
                                "Font": ";8;;",
                                "TextBrush": "solid:Black",
                            }
                        },
                    },
                },
            }
        },
    }


def _printable_column_widths(columns: list[dict[str, str]], total_width: float = 19.0) -> list[float]:
    if not columns:
        return []
    weights = []
    for column in columns:
        text = f"{column.get('name', '')} {column.get('alias', '')}".lower()
        weight = 2.0 if any(token in text for token in ("description", "comment", "описан", "комментар")) else 1.0
        if column.get("type") in {"System.Decimal", "System.Boolean", "System.DateTime"}:
            weight = min(weight, 0.85)
        weights.append(weight)
    unit = total_width / sum(weights)
    widths = [round(weight * unit, 3) for weight in weights]
    widths[-1] = round(total_width - sum(widths[:-1]), 3)
    return widths


def _project_database_native_dashboard_template(
    *,
    report_name: str,
    marker: str,
    source_view_id: str,
    source_view_name: str,
    columns: list[dict[str, str]],
    base_url: str,
) -> dict[str, Any]:
    visible_columns = _visible_report_columns(columns)
    template = _project_database_dashboard_template(
        report_name=report_name,
        marker=marker,
        source_view_id=source_view_id,
        source_view_name=source_view_name,
        columns=visible_columns,
    )
    try:
        return _stimulsoft_native_project_database_template(
            template=template,
            report_name=report_name,
            marker=marker,
            source_view_id=source_view_id,
            source_view_name=source_view_name,
            columns=visible_columns,
            base_url=base_url,
        )
    except Exception as exc:
        alterios = template.setdefault("Alterios", {})
        if isinstance(alterios, dict):
            alterios["nativeTemplateBuildError"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        return template


def _project_database_native_printable_template(
    *,
    report_name: str,
    marker: str,
    source_view_id: str,
    source_view_name: str,
    columns: list[dict[str, str]],
    base_url: str,
) -> dict[str, Any]:
    visible_columns = _visible_report_columns(columns)
    template = _project_database_printable_template(
        report_name=report_name,
        marker=marker,
        source_view_id=source_view_id,
        source_view_name=source_view_name,
        columns=visible_columns,
    )
    try:
        return _stimulsoft_native_project_database_template(
            template=template,
            report_name=report_name,
            marker=marker,
            source_view_id=source_view_id,
            source_view_name=source_view_name,
            columns=visible_columns,
            base_url=base_url,
        )
    except Exception as exc:
        alterios = template.setdefault("Alterios", {})
        if isinstance(alterios, dict):
            alterios["nativeTemplateBuildError"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        return template


def _stimulsoft_native_project_database_template(
    *,
    template: dict[str, Any],
    report_name: str,
    marker: str,
    source_view_id: str,
    source_view_name: str,
    columns: list[dict[str, str]],
    base_url: str,
) -> dict[str, Any]:
    node_path = _find_node()
    scripts_dir = _ensure_stimulsoft_assets(base_url)
    helper_path = Path(tempfile.gettempdir()) / "alterios-mcp-stimulsoft" / "build_project_database_template.js"
    helper_path.parent.mkdir(parents=True, exist_ok=True)
    helper_path.write_text(_STIMULSOFT_PROJECT_DATABASE_DASHBOARD_HELPER, encoding="utf-8")
    completed = subprocess.run(
        [str(node_path), str(helper_path)],
        input=json.dumps(
            {
                "scriptsDir": str(scripts_dir),
                "template": template,
                "reportName": report_name,
                "marker": marker,
                "viewId": source_view_id,
                "viewName": source_view_name,
                "columns": columns,
            },
            ensure_ascii=False,
        ),
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip()[:1000] or "Stimulsoft helper failed.")
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("Stimulsoft helper returned unexpected payload.")
    return payload


def _find_node() -> Path:
    node = shutil.which("node")
    if node:
        return Path(node)
    runtime_node = (
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "node"
        / "bin"
        / "node.exe"
    )
    if runtime_node.exists():
        return runtime_node
    raise RuntimeError("Node.js was not found for native Stimulsoft template generation.")


def _ensure_stimulsoft_assets(base_url: str) -> Path:
    if not base_url:
        raise RuntimeError("base_url is required for native Stimulsoft template generation.")
    target = Path(tempfile.gettempdir()) / "alterios-mcp-stimulsoft"
    target.mkdir(parents=True, exist_ok=True)
    for filename in ("stimulsoft.reports.pack.js", "stimulsoft.dashboards.pack.js"):
        path = target / filename
        if path.exists() and path.stat().st_size > 1000:
            continue
        request = Request(
            base_url.rstrip("/") + f"/assets/stimulsoft/{filename}",
            headers={"User-Agent": "alterios-mcp/1.0"},
        )
        with urlopen(request, timeout=45) as response:
            path.write_bytes(response.read())
    return target


_STIMULSOFT_PROJECT_DATABASE_DASHBOARD_HELPER = r"""
const fs = require("fs");
const path = require("path");

const input = JSON.parse(fs.readFileSync(0, "utf8"));
const reports = require(path.join(input.scriptsDir, "stimulsoft.reports.pack.js"));
const dashboards = require(path.join(input.scriptsDir, "stimulsoft.dashboards.pack.js"));
const Stimulsoft = dashboards.Stimulsoft || reports.Stimulsoft;
const S = Stimulsoft;

const report = new S.Report.StiReport();
const base = JSON.parse(JSON.stringify(input.template));
delete base.Dictionary;
report.load(JSON.stringify(base));
report.reportName = input.reportName;
report.reportAlias = input.reportName;

const connection = JSON.stringify({ type: "view-data-v2", filter: { viewId: input.viewId } });
const database = new S.Report.Dictionary.StiCustomDatabase(input.viewName, "Project Database", connection);
database.serviceName = "Project Database";
database.castToColumnType = "CastToColumnType";
report.dictionary.databases.add(database);

const dataSource = new S.Report.Dictionary.StiCustomSource(input.viewName, "data", input.viewName);
dataSource.serviceName = "Project Database";
dataSource.sqlCommand = "data";
for (const column of input.columns) {
  let type = S.System.String;
  if (column.type === "System.DateTime") type = S.System.DateTime;
  if (column.type === "System.Decimal") type = S.System.Decimal;
  if (column.type === "System.Boolean") type = S.System.Boolean;
  dataSource.columns.add(new S.Report.Dictionary.StiDataColumn(column.name, column.name, column.alias, type));
}
report.dictionary.dataSources.add(dataSource);

const saved = JSON.parse(report.saveToJsonString());
saved.CodexMarker = input.marker;
saved.Alterios = {
  ...(input.template.Alterios || {}),
  sourceViewId: input.viewId,
  sourceViewName: input.viewName,
  templateKind: input.template.Alterios?.templateKind === "printable_project_database"
    ? "native_printable_project_database"
    : "report_tab_project_database_native_dashboard",
};
process.stdout.write(JSON.stringify(saved));
"""


def _dashboard_table_columns(columns: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    visible_columns = _visible_report_columns(columns)
    return {
        str(index): {
            "Ident": "DimensionColumn",
            "Key": _stable_dashboard_key("table", column["name"]),
            "Expression": f"data.{column['name']}",
            "Label": column["alias"],
            "DashboardInteraction": {
                "Ident": "TableColumn",
                "OnHover": "None",
                "OnClick": "None",
                "HyperlinkDestination": "NewTab",
            },
            "Size": {"MinWidth": 30, "MaxWidth": 300},
        }
        for index, column in enumerate(visible_columns)
    }


def _visible_report_columns(columns: list[dict[str, str]]) -> list[dict[str, str]]:
    visible = [
        column
        for column in columns
        if not _is_technical_report_column(column.get("name") or "", column.get("alias") or "")
    ]
    return visible or [
        column for column in columns if not re.fullmatch(r"_id\d*", column.get("name") or "")
    ] or columns


def _is_technical_report_column(name: str, alias: str) -> bool:
    lowered = f"{name} {alias}".lower()
    if re.fullmatch(r"_id\d*", name):
        return True
    return name.startswith("test__field_") or "bulk_select" in lowered


def _stable_dashboard_key(prefix: str, value: str) -> str:
    return hashlib.md5(f"{prefix}:{value}".encode("utf-8")).hexdigest()


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
    delivery_evidence: dict[str, Any] | None,
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
        "deliveryEvidence": delivery_evidence,
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
                            "displaying": {"fields": {}, "header": {}},
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




__all__ = [name for name in globals() if not name.startswith("__")]
