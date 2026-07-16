from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .client import AlteriosClient, AlteriosConfig, listandcount_items
from .form_surface import analyze_form_surface
from .services import SERVICES

CAMUNDA_NS = "http://camunda.org/schema/1.0/bpmn"
ID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
SCRIPT_REF_KEYS = {
    "_id",
    "id",
    "scriptId",
    "manualScriptId",
    "diagramScriptId",
    "eventScriptId",
    "function",
    "service",
    "script",
    "scriptName",
}
ICON_KEYS = {"icon", "iconId", "iconName", "materialIcon"}
STANDARD_ICON_NAMES = {
    "save": "save",
    "back": "arrow_back",
    "edit": "edit",
    "view": "visibility",
    "delete": "delete",
    "menu": "more_vert",
    "info": "info",
    "add": "add",
    "sync": "sync",
    "files": "attach_file",
}
TASK_NODE_TYPES = {
    "task",
    "userTask",
    "scriptTask",
    "serviceTask",
    "manualTask",
    "businessRuleTask",
    "sendTask",
    "receiveTask",
    "callActivity",
}
EVENT_NODE_TYPES = {
    "startEvent",
    "endEvent",
    "intermediateCatchEvent",
    "intermediateThrowEvent",
    "boundaryEvent",
}


def collect_live_project_inventory(
    *,
    profile: str | None,
    project_id: str | None,
    dotenv_path: str | None = ".env",
    include_processes: bool = True,
) -> dict[str, Any]:
    client = AlteriosClient(AlteriosConfig.from_env(dotenv_path=dotenv_path, profile=profile).with_project_id(project_id))
    forms = _items(client.list_forms(limit=5000).body)
    scripts = _items(client.list_scripts(limit=5000).body)
    diagrams = _items(client.list_diagrams(limit=5000).body)
    groups = _items(client.list_groups().body)
    processes_by_diagram: dict[str, list[dict[str, Any]]] = {}
    tasks_by_diagram: dict[str, list[dict[str, Any]]] = {}
    read_errors: list[dict[str, str]] = []

    if include_processes:
        for diagram in diagrams:
            diagram_id = str(diagram.get("_id") or "")
            if not diagram_id:
                continue
            try:
                processes_by_diagram[diagram_id] = _items(client.list_processes(diagram_id=diagram_id, limit=5000).body)
            except Exception as exc:  # pragma: no cover - network/instance dependent.
                read_errors.append({"scope": "processes", "diagram_id": diagram_id, "error": str(exc)})
            try:
                tasks_by_diagram[diagram_id] = _items(client.list_tasks(diagram_id=diagram_id).body)
            except Exception as exc:  # pragma: no cover - network/instance dependent.
                read_errors.append({"scope": "tasks", "diagram_id": diagram_id, "error": str(exc)})

    return build_deep_inventory(
        forms=forms,
        scripts=scripts,
        diagrams=diagrams,
        groups=groups,
        processes_by_diagram=processes_by_diagram,
        tasks_by_diagram=tasks_by_diagram,
        profile=profile,
        project_id=project_id,
        read_errors=read_errors,
    )


def build_deep_inventory(
    *,
    forms: list[dict[str, Any]],
    scripts: list[dict[str, Any]],
    diagrams: list[dict[str, Any]],
    groups: list[dict[str, Any]] | None = None,
    processes_by_diagram: dict[str, list[dict[str, Any]]] | None = None,
    tasks_by_diagram: dict[str, list[dict[str, Any]]] | None = None,
    profile: str | None = None,
    project_id: str | None = None,
    read_errors: list[dict[str, str]] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    groups = groups or []
    processes_by_diagram = processes_by_diagram or {}
    tasks_by_diagram = tasks_by_diagram or {}
    context = {"generated_at": timestamp, "profile": profile, "project_id": project_id}
    form_inventory = build_form_surface_inventory(forms=forms, diagrams=diagrams, context=context)
    script_linkage = build_script_bpmn_linkage(
        forms=forms,
        scripts=scripts,
        diagrams=diagrams,
        form_actions=form_inventory["action_matrix"],
        processes_by_diagram=processes_by_diagram,
        tasks_by_diagram=tasks_by_diagram,
        context=context,
    )
    icon_usage = build_icon_usage_matrix(forms=forms, groups=groups, form_actions=form_inventory["action_matrix"], context=context)
    return {
        "context": context,
        "read_errors": read_errors or [],
        "form_surface_inventory": form_inventory,
        "script_bpmn_linkage": script_linkage,
        "icon_usage_matrix": icon_usage,
    }


def build_form_surface_inventory(
    *,
    forms: list[dict[str, Any]],
    diagrams: list[dict[str, Any]],
    context: dict[str, Any],
) -> dict[str, Any]:
    task_form_keys = _task_form_keys(diagrams)
    cell_type_counter: Counter[str] = Counter()
    action_type_counter: Counter[str] = Counter()
    form_kind_counter: Counter[str] = Counter()
    action_matrix: list[dict[str, Any]] = []
    form_rows: list[dict[str, Any]] = []

    for form in forms:
        form_id = str(form.get("_id") or "")
        analyzer = analyze_form_surface(form)
        tabs, rows, cells = _summarize_tabs(form)
        actions = _collect_form_actions(form)
        for action in actions:
            action_matrix.append(action)
            action_type_counter[action["category"]] += 1
        for cell in cells:
            cell_type_counter[cell["type"]] += 1
        kinds = _classify_form(form, cells, actions, task_form_keys)
        for kind in kinds:
            form_kind_counter[kind] += 1
        form_rows.append(
            {
                "form_id": form_id,
                "name": form.get("name"),
                "page_title": form.get("pageTitle"),
                "version": form.get("version"),
                "kinds": kinds,
                "task_links": [item for item in task_form_keys if item.get("form_key") in {form_id, form.get("name"), form.get("pageTitle")}],
                "tab_count": len(tabs),
                "row_count": len(rows),
                "cell_count": len(cells),
                "cell_types": dict(Counter(cell["type"] for cell in cells)),
                "form_action_container_count": len(_as_list(form.get("formActionContainers"))),
                "action_count": len(actions),
                "action_types": dict(Counter(action["category"] for action in actions)),
                "icon_ids": sorted({icon for cell in cells for icon in cell["icon_ids"]} | {action["icon_id"] for action in actions if action.get("icon_id")}),
                "tabs": tabs,
                "rows": rows,
                "cells": cells,
                "formActionContainers": [
                    _summarize_action_container(container, f"forms[{form_id}].formActionContainers[{index}]", "form", form_id=form_id)
                    for index, container in enumerate(_as_list(form.get("formActionContainers")))
                    if isinstance(container, dict)
                ],
                "actions": actions,
                "surface_check": {
                    "ok": analyzer["ok"],
                    "issue_count": analyzer["issue_count"],
                    "issues_by_code": analyzer["issues_by_code"],
                    "issues_by_severity": analyzer["issues_by_severity"],
                },
            }
        )

    return {
        "context": context,
        "totals": {
            "forms": len(forms),
            "tabs": sum(item["tab_count"] for item in form_rows),
            "rows": sum(item["row_count"] for item in form_rows),
            "cells": sum(item["cell_count"] for item in form_rows),
            "actions": len(action_matrix),
            "cell_types": dict(sorted(cell_type_counter.items())),
            "action_types": dict(sorted(action_type_counter.items())),
            "form_kinds": dict(sorted(form_kind_counter.items())),
        },
        "forms": form_rows,
        "action_matrix": action_matrix,
    }


def build_script_bpmn_linkage(
    *,
    forms: list[dict[str, Any]],
    scripts: list[dict[str, Any]],
    diagrams: list[dict[str, Any]],
    form_actions: list[dict[str, Any]],
    processes_by_diagram: dict[str, list[dict[str, Any]]],
    tasks_by_diagram: dict[str, list[dict[str, Any]]],
    context: dict[str, Any],
) -> dict[str, Any]:
    script_rows = [_summarize_script(script) for script in scripts]
    script_index = _script_index(scripts)
    form_index = _form_index(forms)
    form_script_links = [
        {
            **action,
            "script_match": _match_script_ref(action.get("target_script_id") or action.get("target_script_name"), script_index),
        }
        for action in form_actions
        if action.get("category") in {"manual_script", "script"} or action.get("target_script_id") or action.get("target_script_name")
    ]

    diagram_rows: list[dict[str, Any]] = []
    all_bpmn_nodes: list[dict[str, Any]] = []
    all_form_task_links: list[dict[str, Any]] = []
    all_diagram_script_refs: list[dict[str, Any]] = []
    all_listener_refs: list[dict[str, Any]] = []

    for diagram in diagrams:
        diagram_summary = _summarize_diagram(
            diagram,
            script_index=script_index,
            form_index=form_index,
            processes=processes_by_diagram.get(str(diagram.get("_id") or ""), []),
            tasks=tasks_by_diagram.get(str(diagram.get("_id") or ""), []),
        )
        diagram_rows.append(diagram_summary)
        all_bpmn_nodes.extend(diagram_summary["bpmn_nodes"])
        all_form_task_links.extend(diagram_summary["user_task_form_links"])
        all_diagram_script_refs.extend(diagram_summary["script_refs"])
        all_listener_refs.extend(diagram_summary["listener_refs"])

    service_call_counter: Counter[str] = Counter()
    risk_counter: Counter[str] = Counter()
    for script in script_rows:
        for call in script["service_calls"]:
            service_call_counter[call["name"]] += 1
            risk_counter[call["risk_level"]] += 1

    return {
        "context": context,
        "totals": {
            "scripts": len(scripts),
            "script_types": dict(Counter(str(script.get("type") or "unknown") for script in scripts)),
            "diagrams": len(diagrams),
            "bpmn_nodes": len(all_bpmn_nodes),
            "user_task_form_links": len(all_form_task_links),
            "form_script_links": len(form_script_links),
            "diagram_script_refs": len(all_diagram_script_refs),
            "listener_refs": len(all_listener_refs),
            "service_calls": dict(sorted(service_call_counter.items())),
            "service_risks": dict(sorted(risk_counter.items())),
        },
        "scripts": script_rows,
        "form_script_links": form_script_links,
        "diagrams": diagram_rows,
        "bpmn_nodes": all_bpmn_nodes,
        "user_task_form_links": all_form_task_links,
        "diagram_script_refs": all_diagram_script_refs,
        "listener_refs": all_listener_refs,
    }


def build_icon_usage_matrix(
    *,
    forms: list[dict[str, Any]],
    groups: list[dict[str, Any]],
    form_actions: list[dict[str, Any]],
    context: dict[str, Any],
) -> dict[str, Any]:
    usage: list[dict[str, Any]] = []
    for form in forms:
        form_id = str(form.get("_id") or "")
        for path, key, value, owner in _walk_icon_values(form, f"forms[{form_id}]", owner={"owner_type": "form", "owner_id": form_id, "owner_name": form.get("name")}):
            usage.append(_icon_usage_row(path=path, key=key, value=value, owner=owner, source="form"))
    for group in groups:
        group_id = str(group.get("_id") or "")
        for path, key, value, owner in _walk_icon_values(group, f"groups[{group_id}]", owner={"owner_type": "group", "owner_id": group_id, "owner_name": group.get("name")}):
            usage.append(_icon_usage_row(path=path, key=key, value=value, owner=owner, source="group"))
    for action in form_actions:
        icon_id = action.get("icon_id")
        if icon_id:
            usage.append(
                _icon_usage_row(
                    path=action["path"],
                    key="iconId",
                    value=icon_id,
                    owner={
                        "owner_type": "action",
                        "owner_id": action.get("form_id"),
                        "owner_name": action.get("form_name"),
                        "action_category": action.get("category"),
                        "action_title": action.get("title"),
                    },
                    source="action_matrix",
                )
            )

    deduped = _dedupe_dicts(usage)
    icon_counter = Counter(str(item["icon_value"]) for item in deduped)
    semantic_counter = Counter(str(item["semantic_guess"] or "unknown") for item in deduped)
    return {
        "context": context,
        "standard": {
            "library": "Google Fonts Icons",
            "size": 16,
            "color": "#4B77D1",
            "semantic_icons": STANDARD_ICON_NAMES,
        },
        "totals": {
            "icon_usages": len(deduped),
            "unique_icon_values": len(icon_counter),
            "icon_values": dict(sorted(icon_counter.items())),
            "semantic_guesses": dict(sorted(semantic_counter.items())),
        },
        "usage": deduped,
    }


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        direct = [item for item in payload if isinstance(item, dict)]
        if direct:
            return direct
    if isinstance(payload, dict):
        for key in ("items", "data", "rows", "values", "results", "groups"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return [item for item in listandcount_items(payload) if isinstance(item, dict)]


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _summarize_tabs(form: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    form_id = str(form.get("_id") or "")
    tabs: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    cells: list[dict[str, Any]] = []
    for tab_index, tab in enumerate(_as_list(form.get("tabs"))):
        if not isinstance(tab, dict):
            continue
        tab_path = f"forms[{form_id}].tabs[{tab_index}]"
        tab_rows = _rows_from_tab(tab)
        tab_cell_count = sum(len(_cells_from_row(row)) for row in tab_rows)
        tabs.append(
            {
                "path": tab_path,
                "index": tab_index,
                "name": tab.get("name"),
                "title": tab.get("title"),
                "row_count": len(tab_rows),
                "cell_count": tab_cell_count,
                "style_keys": sorted(_dict(tab.get("styles")).keys()),
            }
        )
        for row_index, row in enumerate(tab_rows):
            row_path = f"{tab_path}.rows[{row_index}]"
            row_cells = _cells_from_row(row)
            rows.append(
                {
                    "path": row_path,
                    "tab_index": tab_index,
                    "row_index": row_index,
                    "cell_count": len(row_cells),
                    "style_keys": sorted(_dict(row.get("styles") if isinstance(row, dict) else {}).keys()),
                    "reverse": row.get("reverse") if isinstance(row, dict) else None,
                }
            )
            for cell_index, cell in enumerate(row_cells):
                if isinstance(cell, dict):
                    cells.append(_summarize_cell(cell, f"{row_path}.cells[{cell_index}]", tab_index, row_index, cell_index))
    return tabs, rows, cells


def _rows_from_tab(tab: dict[str, Any]) -> list[Any]:
    for key in ("rows", "items", "children"):
        value = tab.get(key)
        if isinstance(value, list):
            return value
    return []


def _cells_from_row(row: Any) -> list[Any]:
    if isinstance(row, list):
        return row
    if not isinstance(row, dict):
        return []
    for key in ("cells", "items", "children"):
        value = row.get(key)
        if isinstance(value, list):
            return value
    return [row] if row.get("type") else []


def _summarize_cell(cell: dict[str, Any], path: str, tab_index: int, row_index: int, cell_index: int) -> dict[str, Any]:
    params = _dict(cell.get("params"))
    displaying = _dict(cell.get("displaying"))
    return {
        "path": path,
        "tab_index": tab_index,
        "row_index": row_index,
        "cell_index": cell_index,
        "name": cell.get("name"),
        "type": str(cell.get("type") or "unknown"),
        "params": _summarize_params(params),
        "openId": params.get("openId"),
        "viewId": params.get("viewId"),
        "contentTypeId": params.get("contentTypeId"),
        "reportId": params.get("reportId"),
        "entity": params.get("entity"),
        "viewEntityId": cell.get("viewEntityId") or params.get("viewEntityId"),
        "style_keys": sorted(_dict(cell.get("styles")).keys()),
        "displaying_keys": sorted(displaying.keys()),
        "displaying_field_count": len(_dict(displaying.get("fields"))),
        "displaying_header_keys": sorted(_dict(displaying.get("header")).keys()),
        "condition_count": _count_conditions(cell),
        "cell_action_container_count": len(_as_list(cell.get("cellActionContainers"))),
        "value_action_container_count": len(_as_list(cell.get("valueActionContainers"))),
        "icon_ids": sorted({str(value) for _, _, value, _ in _walk_icon_values(cell, path, owner={})}),
    }


def _summarize_params(params: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {"keys": sorted(params.keys())}
    for key in (
        "openId",
        "viewId",
        "contentTypeId",
        "reportId",
        "entity",
        "engineVersion",
        "fullscreenMode",
        "createNew",
        "viewEntityId",
    ):
        if key in params:
            summary[key] = params[key]
    return summary


def _count_conditions(value: Any) -> int:
    count = 0
    if isinstance(value, dict):
        conditions = value.get("conditions")
        if isinstance(conditions, list):
            count += len(conditions)
        for child in value.values():
            count += _count_conditions(child)
    elif isinstance(value, list):
        for child in value:
            count += _count_conditions(child)
    return count


def _collect_form_actions(form: dict[str, Any]) -> list[dict[str, Any]]:
    form_id = str(form.get("_id") or "")
    form_name = str(form.get("name") or "")
    actions: list[dict[str, Any]] = []
    for index, container in enumerate(_as_list(form.get("formActionContainers"))):
        if isinstance(container, dict):
            actions.extend(_action_rows(container, f"forms[{form_id}].formActionContainers[{index}]", "form", form_id, form_name, None))
    for tab_index, tab in enumerate(_as_list(form.get("tabs"))):
        if not isinstance(tab, dict):
            continue
        for row_index, row in enumerate(_rows_from_tab(tab)):
            for cell_index, cell in enumerate(_cells_from_row(row)):
                if not isinstance(cell, dict):
                    continue
                cell_path = f"forms[{form_id}].tabs[{tab_index}].rows[{row_index}].cells[{cell_index}]"
                for container_index, container in enumerate(_as_list(cell.get("cellActionContainers"))):
                    if isinstance(container, dict):
                        actions.extend(_action_rows(container, f"{cell_path}.cellActionContainers[{container_index}]", "cell", form_id, form_name, cell.get("type")))
                for container_index, container in enumerate(_as_list(cell.get("valueActionContainers"))):
                    if isinstance(container, dict):
                        actions.extend(_action_rows(container, f"{cell_path}.valueActionContainers[{container_index}]", "value", form_id, form_name, cell.get("type")))
    return actions


def _action_rows(
    container: dict[str, Any],
    path: str,
    scope: str,
    form_id: str,
    form_name: str,
    cell_type: Any,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    nested_containers = container.get("containers")
    if str(container.get("type") or "").lower() == "menu" and isinstance(nested_containers, list):
        for nested_index, nested_container in enumerate(nested_containers):
            if isinstance(nested_container, dict):
                rows.extend(
                    _action_rows(
                        nested_container,
                        f"{path}.containers[{nested_index}]",
                        scope,
                        form_id,
                        form_name,
                        cell_type,
                    )
                )
        return rows
    actions = container.get("actions")
    if not isinstance(actions, list):
        actions = [container]
    for action_index, action in enumerate(actions):
        if not isinstance(action, dict):
            continue
        action_path = f"{path}.actions[{action_index}]" if action is not container else path
        category = _classify_action(container, action)
        args = action.get("argumentsConfig")
        if args is None:
            args = action.get("args")
        if args is None:
            args = action.get("params")
        rows.append(
            {
                "form_id": form_id,
                "form_name": form_name,
                "path": action_path,
                "scope": scope,
                "cell_type": cell_type,
                "container_title": container.get("title"),
                "title": action.get("title") or container.get("title") or action.get("name"),
                "container_type": container.get("type"),
                "action_type": action.get("type"),
                "category": category,
                "position": container.get("position"),
                "default": container.get("default"),
                "icon_id": _icon_value(action) or _icon_value(container),
                "style_keys": sorted(_dict(container.get("styles")).keys()),
                "condition_count": _count_conditions(container) + _count_conditions(action),
                "dataManagingType": action.get("dataManagingType"),
                "openInDialog": action.get("openInDialog"),
                "openInNewTab": action.get("openInNewTab"),
                "viewEntityId": action.get("viewEntityId") or container.get("viewEntityId"),
                "target_form_id": _target_form_id(action),
                "target_script_id": _target_script_id(action),
                "target_script_name": _target_script_name(action),
                "target_report_id": _target_report_id(action),
                "target_diagram_id": action.get("diagramId") or action.get("diagram_id"),
                "argument_shape": _shape(args),
                "argument_keys": sorted(args.keys()) if isinstance(args, dict) else [],
            }
        )
    return rows


def _summarize_action_container(container: dict[str, Any], path: str, scope: str, *, form_id: str) -> dict[str, Any]:
    return {
        "path": path,
        "scope": scope,
        "form_id": form_id,
        "title": container.get("title"),
        "type": container.get("type"),
        "position": container.get("position"),
        "default": container.get("default"),
        "icon_id": _icon_value(container),
        "condition_count": _count_conditions(container),
        "style_keys": sorted(_dict(container.get("styles")).keys()),
        "action_count": len(_as_list(container.get("actions"))),
    }


def _classify_action(container: dict[str, Any], action: dict[str, Any]) -> str:
    data_type = str(action.get("dataManagingType") or "").lower()
    action_type = str(action.get("type") or container.get("type") or "").lower()
    title = " ".join(str(value or "").lower() for value in (container.get("title"), action.get("title"), action.get("name")))
    if data_type in {"submit_all", "submit", "save"}:
        return "save_submit"
    if action_type in {"forms", "form"}:
        return "open_form"
    if action_type in {"manual_script", "script", "scripts"} or any(key in action for key in ("scriptId", "manualScriptId", "scriptName")):
        return "manual_script"
    if action_type in {"process", "processes", "start_process"} or action.get("diagramId"):
        return "start_process"
    if action_type in {"edit_task", "task_edit"} or "edit_task" in title:
        return "task_edit"
    if action_type in {"report", "reports"} or action.get("reportId"):
        return "report"
    if action_type in {"routing", "redirect", "route", "link"} or any(token in title for token in ("routing", "redirect", "route", "перей", "назад")):
        return "routing"
    if data_type in {"delete", "delete_all", "delete_many"} or any(token in title for token in ("delete", "remove", "удал")):
        return "delete"
    return action_type or "unknown"


def _target_form_id(action: dict[str, Any]) -> Any:
    if str(action.get("type") or "").lower() in {"forms", "form"}:
        return action.get("_id") or action.get("formId") or action.get("id")
    return action.get("formId")


def _target_script_id(action: dict[str, Any]) -> Any:
    for key in ("scriptId", "manualScriptId", "diagramScriptId", "eventScriptId"):
        if action.get(key):
            return action.get(key)
    if str(action.get("type") or "").lower() in {"manual_script", "script", "scripts"}:
        return action.get("_id") or action.get("id")
    return None


def _target_script_name(action: dict[str, Any]) -> Any:
    if str(action.get("type") or "").lower() in {"manual_script", "script", "scripts"}:
        return action.get("name") or action.get("scriptName")
    return action.get("scriptName")


def _target_report_id(action: dict[str, Any]) -> Any:
    if str(action.get("type") or "").lower() in {"report", "reports"}:
        return action.get("_id") or action.get("reportId") or action.get("id")
    return action.get("reportId")


def _classify_form(
    form: dict[str, Any],
    cells: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    task_form_keys: list[dict[str, Any]],
) -> list[str]:
    text = f"{form.get('name') or ''} {form.get('pageTitle') or ''}".lower()
    cell_types = {cell["type"] for cell in cells}
    kinds: set[str] = set()
    if "view_data_list" in cell_types:
        kinds.add("list")
    if "view_data" in cell_types or "content" in cell_types:
        kinds.add("detail")
    if any(token in text for token in ("добав", "add", "create", "new")) or any(action["category"] == "save_submit" for action in actions) and "content" in cell_types:
        kinds.add("add")
    if any(token in text for token in ("редакт", "edit", "карточ")) or any(action["category"] == "save_submit" for action in actions) and "view_data" in cell_types:
        kinds.add("edit")
    if "edit_task" in cell_types or any(item.get("form_key") in {form.get("_id"), form.get("name"), form.get("pageTitle")} for item in task_form_keys):
        kinds.add("task")
    if "list" in kinds and not ({"add", "edit", "task"} & kinds):
        kinds.add("main")
    if not kinds:
        kinds.add("other")
    return sorted(kinds)


def _task_form_keys(diagrams: list[dict[str, Any]]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for diagram in diagrams:
        parsed = _parse_bpmn(diagram)
        for node in parsed["nodes"]:
            form_key = node.get("camunda", {}).get("formKey")
            if form_key:
                links.append(
                    {
                        "diagram_id": diagram.get("_id"),
                        "diagram_name": diagram.get("name"),
                        "node_id": node.get("id"),
                        "node_name": node.get("name"),
                        "node_type": node.get("type"),
                        "form_key": form_key,
                    }
                )
    return links


def _summarize_script(script: dict[str, Any]) -> dict[str, Any]:
    body = str(script.get("body") or "")
    service_calls = _service_calls(body)
    return {
        "script_id": script.get("_id"),
        "name": script.get("name"),
        "type": script.get("type"),
        "active": script.get("active"),
        "version": script.get("version"),
        "share": script.get("share"),
        "libraries_count": len(_as_list(script.get("librariesIds"))),
        "config_keys": sorted(_dict(script.get("config")).keys()),
        "config_shape": _shape(script.get("config")),
        "body_length": len(body),
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest() if body else None,
        "uuid_refs": sorted(set(ID_RE.findall(body))),
        "service_calls": service_calls,
        "side_effect_risks": sorted({call["risk_level"] for call in service_calls if call["mutates"]}),
    }


def _service_calls(body: str) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for name, service in SERVICES.items():
        if re.search(rf"\b{re.escape(name)}\s*\(", body) or re.search(rf"['\"]{re.escape(name)}['\"]", body):
            calls.append(
                {
                    "name": name,
                    "category": service.category,
                    "mutates": service.mutates,
                    "risk_level": service.risk_level,
                    "args": list(service.args),
                }
            )
    return calls


def _script_index(scripts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for script in scripts:
        for key in (script.get("_id"), script.get("name")):
            if key:
                index[str(key)] = {"script_id": script.get("_id"), "script_name": script.get("name"), "script_type": script.get("type")}
    return index


def _form_index(forms: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for form in forms:
        for key in (form.get("_id"), form.get("name"), form.get("pageTitle")):
            if key:
                index[str(key)] = {"form_id": form.get("_id"), "form_name": form.get("name"), "page_title": form.get("pageTitle")}
    return index


def _match_script_ref(value: Any, script_index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if value is None:
        return None
    return script_index.get(str(value))


def _summarize_diagram(
    diagram: dict[str, Any],
    *,
    script_index: dict[str, dict[str, Any]],
    form_index: dict[str, dict[str, Any]],
    processes: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    parsed = _parse_bpmn(diagram)
    diagram_id = str(diagram.get("_id") or "")
    xml_text = str(diagram.get("value") or "")
    script_refs = []
    for ref, match in _scan_known_refs(xml_text, script_index).items():
        script_refs.append({"diagram_id": diagram_id, "diagram_name": diagram.get("name"), "ref": ref, "script_match": match})
    form_links = []
    for node in parsed["nodes"]:
        form_key = node.get("camunda", {}).get("formKey")
        if form_key:
            form_links.append(
                {
                    "diagram_id": diagram_id,
                    "diagram_name": diagram.get("name"),
                    "node_id": node.get("id"),
                    "node_name": node.get("name"),
                    "node_type": node.get("type"),
                    "form_key": form_key,
                    "form_match": form_index.get(str(form_key)),
                }
            )
    listener_refs = [
        {
            "diagram_id": diagram_id,
            "diagram_name": diagram.get("name"),
            **listener,
            "script_matches": _refs_in_values(listener, script_index),
        }
        for listener in parsed["listeners"]
    ]
    nodes = [
        {
            "diagram_id": diagram_id,
            "diagram_name": diagram.get("name"),
            **node,
        }
        for node in parsed["nodes"]
    ]
    return {
        "diagram_id": diagram.get("_id"),
        "name": diagram.get("name"),
        "version": diagram.get("version"),
        "contentTypeId": diagram.get("contentTypeId"),
        "createOnStart": diagram.get("createOnStart"),
        "delayedStart": diagram.get("delayedStart"),
        "xml_length": len(xml_text),
        "xml_sha256": hashlib.sha256(xml_text.encode("utf-8")).hexdigest() if xml_text else None,
        "parse_error": parsed["parse_error"],
        "node_counts": dict(Counter(node["type"] for node in nodes)),
        "bpmn_nodes": nodes,
        "user_task_form_links": form_links,
        "script_refs": script_refs,
        "listener_refs": listener_refs,
        "process_summary": {
            "process_count": len(processes),
            "task_count": len(tasks),
            "process_statuses": dict(Counter(str(process.get("status") or process.get("state") or "unknown") for process in processes)),
            "task_statuses": dict(Counter(str(task.get("status") or task.get("state") or "unknown") for task in tasks)),
            "task_names": sorted({str(task.get("name")) for task in tasks if task.get("name")}),
        },
    }


def _parse_bpmn(diagram: dict[str, Any]) -> dict[str, Any]:
    xml_text = str(diagram.get("value") or "")
    if not xml_text.strip():
        return {"nodes": [], "listeners": [], "parse_error": "empty BPMN value"}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        return {"nodes": [], "listeners": [], "parse_error": str(exc)}

    nodes: list[dict[str, Any]] = []
    listeners: list[dict[str, Any]] = []
    for elem in root.iter():
        tag = _local_name(elem.tag)
        if tag in TASK_NODE_TYPES or tag in EVENT_NODE_TYPES:
            attrs = _attrs(elem)
            nodes.append(
                {
                    "id": attrs.get("id"),
                    "name": attrs.get("name"),
                    "type": tag,
                    "camunda": {key.removeprefix("camunda:"): value for key, value in attrs.items() if key.startswith("camunda:")},
                    "incoming": [_child_text(child) for child in elem if _local_name(child.tag) == "incoming"],
                    "outgoing": [_child_text(child) for child in elem if _local_name(child.tag) == "outgoing"],
                }
            )
        if tag in {"executionListener", "taskListener"}:
            attrs = _attrs(elem)
            listeners.append(
                {
                    "listener_type": tag,
                    "event": attrs.get("event") or attrs.get("camunda:event"),
                    "class": attrs.get("class") or attrs.get("camunda:class"),
                    "expression": attrs.get("expression") or attrs.get("camunda:expression"),
                    "delegateExpression": attrs.get("delegateExpression") or attrs.get("camunda:delegateExpression"),
                    "script": _child_script_summary(elem),
                }
            )
    return {"nodes": nodes, "listeners": listeners, "parse_error": None}


def _attrs(elem: ET.Element) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    for raw_key, value in elem.attrib.items():
        key = _attr_name(raw_key)
        attrs[key] = value
    return attrs


def _attr_name(raw_key: str) -> str:
    if raw_key.startswith("{"):
        namespace, local = raw_key[1:].split("}", 1)
        if namespace == CAMUNDA_NS:
            return f"camunda:{local}"
        return local
    return raw_key


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _child_text(elem: ET.Element) -> str:
    return (elem.text or "").strip()


def _child_script_summary(elem: ET.Element) -> dict[str, Any] | None:
    for child in elem.iter():
        if _local_name(child.tag) == "script":
            attrs = _attrs(child)
            text = _child_text(child)
            return {"format": attrs.get("scriptFormat") or attrs.get("camunda:scriptFormat"), "resource": attrs.get("resource"), "length": len(text)}
    return None


def _scan_known_refs(text: str, index: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for ref, match in index.items():
        if ref and ref in text:
            result[ref] = match
    return result


def _refs_in_values(value: Any, index: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return [{"ref": ref, **match} for ref, match in _scan_known_refs(text, index).items()]


def _walk_icon_values(value: Any, path: str, *, owner: dict[str, Any]) -> list[tuple[str, str, Any, dict[str, Any]]]:
    found: list[tuple[str, str, Any, dict[str, Any]]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in ICON_KEYS and child:
                found.append((child_path, key, child, owner))
            found.extend(_walk_icon_values(child, child_path, owner=owner))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_walk_icon_values(child, f"{path}[{index}]", owner=owner))
    return found


def _icon_value(value: dict[str, Any]) -> str | None:
    for key in ("iconId", "icon", "iconName", "materialIcon"):
        if value.get(key):
            return str(value.get(key))
    return None


def _icon_usage_row(path: str, key: str, value: Any, owner: dict[str, Any], source: str) -> dict[str, Any]:
    icon_value = str(value)
    semantic = _semantic_icon_guess(icon_value, path, owner)
    return {
        "source": source,
        "path": path,
        "key": key,
        "icon_value": icon_value,
        "value_kind": "uuid" if ID_RE.fullmatch(icon_value) else "material_name_or_text",
        "semantic_guess": semantic,
        "standard_expected_icon": STANDARD_ICON_NAMES.get(semantic or ""),
        "validation": _icon_validation(icon_value, semantic),
        "owner": owner,
    }


def _semantic_icon_guess(icon_value: str, path: str, owner: dict[str, Any]) -> str | None:
    text = " ".join(str(part or "").lower() for part in (icon_value, path, owner.get("action_category"), owner.get("action_title"), owner.get("owner_name")))
    checks = {
        "save": ("save", "submit", "сохран"),
        "back": ("back", "arrow_back", "назад", "close", "закры"),
        "edit": ("edit", "редакт", "измен"),
        "view": ("view", "visibility", "просмотр", "откры"),
        "delete": ("delete", "удал", "remove"),
        "menu": ("more_vert", "menu", "ellipsis"),
        "info": ("info", "help", "справ", "подсказ"),
        "add": ("add", "plus", "добав"),
        "sync": ("sync", "refresh", "обнов", "синх"),
        "files": ("file", "attach", "upload", "файл"),
    }
    for semantic, tokens in checks.items():
        if any(token in text for token in tokens):
            return semantic
    return None


def _icon_validation(icon_value: str, semantic: str | None) -> dict[str, Any]:
    if ID_RE.fullmatch(icon_value):
        return {
            "status": "icon_id_present",
            "note": "UUID iconId can be validated only against an icon registry/readback; semantic is inferred from usage context.",
        }
    expected = STANDARD_ICON_NAMES.get(semantic or "")
    if expected and icon_value == expected:
        return {"status": "matches_standard_name"}
    if expected:
        return {"status": "name_differs_from_standard", "expected": expected}
    return {"status": "present_unmapped"}


def _shape(value: Any, *, depth: int = 0) -> Any:
    if depth >= 3:
        return type(value).__name__
    if isinstance(value, dict):
        return {str(key): _shape(child, depth=depth + 1) for key, child in value.items() if str(key).lower() != "apikey"}
    if isinstance(value, list):
        if not value:
            return []
        return [_shape(value[0], depth=depth + 1), f"... {len(value)} item(s)"]
    if value is None:
        return None
    return type(value).__name__


def _dedupe_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def write_inventory_outputs(inventory: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "form_json": out_dir / "form-surface-inventory.json",
        "linkage_json": out_dir / "script-bpmn-linkage.json",
        "icons_json": out_dir / "icon-usage-matrix.json",
        "form_doc": out_dir / "form-surface-inventory.md",
        "linkage_doc": out_dir / "script-bpmn-linkage.md",
    }
    paths["form_json"].write_text(json.dumps(inventory["form_surface_inventory"], ensure_ascii=False, indent=2), encoding="utf-8")
    paths["linkage_json"].write_text(json.dumps(inventory["script_bpmn_linkage"], ensure_ascii=False, indent=2), encoding="utf-8")
    paths["icons_json"].write_text(json.dumps(inventory["icon_usage_matrix"], ensure_ascii=False, indent=2), encoding="utf-8")
    paths["form_doc"].write_text(render_form_inventory_markdown(inventory), encoding="utf-8")
    paths["linkage_doc"].write_text(render_script_bpmn_markdown(inventory), encoding="utf-8")
    return {key: str(path) for key, path in paths.items()}


def render_form_inventory_markdown(inventory: dict[str, Any]) -> str:
    forms = inventory["form_surface_inventory"]
    icons = inventory["icon_usage_matrix"]
    totals = forms["totals"]
    lines = [
        "# Инвентаризация поверхности форм",
        "",
        f"Дата: {forms['context'].get('generated_at')}",
        f"Профиль: `{forms['context'].get('profile')}`",
        f"Проект: `{forms['context'].get('project_id')}`",
        "",
        "## Сводка",
        "",
        "| Метрика | Значение |",
        "|---|---:|",
        f"| Формы | {totals['forms']} |",
        f"| Tabs | {totals['tabs']} |",
        f"| Rows | {totals['rows']} |",
        f"| Cells | {totals['cells']} |",
        f"| Actions | {totals['actions']} |",
        f"| Icon usages | {icons['totals']['icon_usages']} |",
        "",
        "## Типы ячеек",
        "",
        "| Cell type | Количество |",
        "|---|---:|",
    ]
    lines.extend(f"| `{key}` | {value} |" for key, value in totals["cell_types"].items())
    lines.extend(["", "## Типы действий", "", "| Action category | Количество |", "|---|---:|"])
    lines.extend(f"| `{key}` | {value} |" for key, value in totals["action_types"].items())
    lines.extend(["", "## Классификация форм", "", "| Kind | Количество |", "|---|---:|"])
    lines.extend(f"| `{key}` | {value} |" for key, value in totals["form_kinds"].items())
    lines.extend(
        [
            "",
            "## Формы",
            "",
            "| Форма | Kind | Tabs | Rows | Cells | Cell types | Actions | Surface issues |",
            "|---|---|---:|---:|---:|---|---:|---|",
        ]
    )
    for form in forms["forms"]:
        issue_text = ", ".join(f"{key}={value}" for key, value in form["surface_check"]["issues_by_code"].items()) or "0"
        cell_types = ", ".join(f"{key}:{value}" for key, value in form["cell_types"].items())
        lines.append(
            f"| `{form['name']}` | {', '.join(form['kinds'])} | {form['tab_count']} | {form['row_count']} | {form['cell_count']} | {cell_types} | {form['action_count']} | {issue_text} |"
        )
    lines.extend(
        [
            "",
            "## JSON-матрицы",
            "",
            "- `form-surface-inventory.json` - tabs/rows/cells/actions/params/styles/displaying/conditions.",
            "- `icon-usage-matrix.json` - iconId/icon/materialIcon usage по формам, группам и actions.",
            "",
            "## Правила чтения",
            "",
            "- `surface_check` показывает статический preflight, а не визуальную UI-проверку.",
            "- UUID в `iconId` означает наличие ссылки на иконку; соответствие Google Fonts Icons требует отдельной сверки с registry/readback.",
            "- Form kind выводится эвристически по ячейкам, actions и BPMN `formKey`; неоднозначные формы могут иметь несколько kind.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_script_bpmn_markdown(inventory: dict[str, Any]) -> str:
    linkage = inventory["script_bpmn_linkage"]
    totals = linkage["totals"]
    lines = [
        "# Связи scripts, forms и BPMN",
        "",
        f"Дата: {linkage['context'].get('generated_at')}",
        f"Профиль: `{linkage['context'].get('profile')}`",
        f"Проект: `{linkage['context'].get('project_id')}`",
        "",
        "## Сводка",
        "",
        "| Метрика | Значение |",
        "|---|---:|",
        f"| Scripts | {totals['scripts']} |",
        f"| Diagrams | {totals['diagrams']} |",
        f"| BPMN nodes | {totals['bpmn_nodes']} |",
        f"| UserTask form links | {totals['user_task_form_links']} |",
        f"| Form script links | {totals['form_script_links']} |",
        f"| Diagram script refs | {totals['diagram_script_refs']} |",
        f"| Listener refs | {totals['listener_refs']} |",
        "",
        "## Типы scripts",
        "",
        "| Type | Количество |",
        "|---|---:|",
    ]
    lines.extend(f"| `{key}` | {value} |" for key, value in totals["script_types"].items())
    lines.extend(["", "## Service calls в script body", "", "| Service | Количество |", "|---|---:|"])
    if totals["service_calls"]:
        lines.extend(f"| `{key}` | {value} |" for key, value in totals["service_calls"].items())
    else:
        lines.append("| - | 0 |")
    lines.extend(["", "## Forms -> scripts", "", "| Форма | Action | Script ref | Match | Args |", "|---|---|---|---|---|"])
    if linkage["form_script_links"]:
        for link in linkage["form_script_links"]:
            match = link.get("script_match") or {}
            ref = link.get("target_script_id") or link.get("target_script_name") or ""
            args = ", ".join(link.get("argument_keys") or [])
            lines.append(f"| `{link.get('form_name')}` | `{link.get('title')}` | `{ref}` | `{match.get('script_name') or ''}` | {args} |")
    else:
        lines.append("| - | - | - | - | - |")
    lines.extend(["", "## BPMN userTask -> forms", "", "| Diagram | Node | formKey | Form match |", "|---|---|---|---|"])
    if linkage["user_task_form_links"]:
        for link in linkage["user_task_form_links"]:
            match = link.get("form_match") or {}
            lines.append(f"| `{link.get('diagram_name')}` | `{link.get('node_name') or link.get('node_id')}` | `{link.get('form_key')}` | `{match.get('form_name') or ''}` |")
    else:
        lines.append("| - | - | - | - |")
    lines.extend(["", "## Диаграммы", "", "| Diagram | Nodes | Processes | Tasks | Parse |", "|---|---:|---:|---:|---|"])
    for diagram in linkage["diagrams"]:
        process_summary = diagram["process_summary"]
        lines.append(
            f"| `{diagram.get('name')}` | {sum(diagram['node_counts'].values())} | {process_summary['process_count']} | {process_summary['task_count']} | {diagram.get('parse_error') or 'ok'} |"
        )
    lines.extend(
        [
            "",
            "## JSON-матрица",
            "",
            "- `script-bpmn-linkage.json` - scripts, form actions, BPMN nodes/listeners/formKey/script refs, process/task readback counts.",
            "",
            "## Границы проверки",
            "",
            "- Scanner не запускает scripts и processes; side effects выводятся по статическим service-call маркерам и live process/task readback.",
            "- Script body в JSON не сохраняется: только `body_length`, `body_sha256`, UUID refs и найденные service calls.",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build deep Alterios form/script/BPMN/icon inventory.")
    parser.add_argument("--profile", default=None)
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--dotenv", default=".env")
    parser.add_argument("--out-dir", default=None, help="Write docs and JSON matrices to this directory.")
    parser.add_argument("--no-processes", action="store_true", help="Skip live process/task readback.")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)

    inventory = collect_live_project_inventory(
        profile=args.profile,
        project_id=args.project_id,
        dotenv_path=args.dotenv,
        include_processes=not args.no_processes,
    )
    if args.out_dir:
        paths = write_inventory_outputs(inventory, Path(args.out_dir))
        print(json.dumps({"written": paths, "context": inventory["context"], "read_errors": inventory["read_errors"]}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(inventory, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
