from __future__ import annotations

import copy
import re
from typing import Any


FORM_SCRIPT_ACTION_SCOPES = {"page", "element", "value"}
SPECIAL_DATA_PROVIDER_KEYS = {"__entity_id", "openId"}
ID_FIELD_MNAME_RE = re.compile(r"^_id\d*$", re.IGNORECASE)


def form_cell(
    form: dict[str, Any],
    *,
    tab_index: int | None,
    row_index: int | None,
    cell_index: int | None,
) -> dict[str, Any]:
    if tab_index is None or row_index is None or cell_index is None:
        raise ValueError("tab_index, row_index, and cell_index are required for element and value actions.")
    if min(tab_index, row_index, cell_index) < 0:
        raise ValueError("tab_index, row_index, and cell_index must be non-negative.")
    try:
        cell = form["tabs"][tab_index]["rows"][row_index]["cells"][cell_index]
    except (IndexError, KeyError, TypeError) as exc:
        raise ValueError(
            f"Cell path tabs[{tab_index}].rows[{row_index}].cells[{cell_index}] was not found."
        ) from exc
    if not isinstance(cell, dict):
        raise ValueError("Target form cell is not a JSON object.")
    return cell


def cell_view_id(cell: dict[str, Any] | None) -> str | None:
    if not isinstance(cell, dict):
        return None
    params = cell.get("params")
    value = params.get("viewId") if isinstance(params, dict) else None
    value = value or cell.get("viewId")
    return str(value).strip() if value else None


def resolve_entity_id_provider_key(
    view_fields: list[dict[str, Any]],
    entity_id: str,
) -> dict[str, Any]:
    normalized_entity_id = str(entity_id or "").strip()
    if not normalized_entity_id:
        raise ValueError("View entity id must not be empty.")
    candidates = []
    for field in view_fields:
        if not isinstance(field, dict) or str(field.get("entityId") or "") != normalized_entity_id:
            continue
        mname = str(field.get("mname") or "").strip()
        if not mname or not ID_FIELD_MNAME_RE.fullmatch(mname):
            continue
        field_type = str(field.get("type") or "").lower()
        attribute = str(field.get("attribute") or field.get("contentAttribute") or "").lower()
        if field_type and field_type != "attribute" and attribute not in {"_id", "id"}:
            continue
        candidates.append(field)
    if not candidates:
        raise ValueError(f"View entity {normalized_entity_id!r} has no _id/_idN provider field in the view.")
    candidates.sort(key=lambda item: (str(item.get("mname")) != "_id", str(item.get("mname"))))
    selected = candidates[0]
    return {
        "entity_id": normalized_entity_id,
        "provider_key": str(selected.get("mname")),
        "view_field_id": selected.get("_id"),
        "alias": selected.get("alias"),
        "candidate_count": len(candidates),
    }


def script_argument_keys(script: dict[str, Any]) -> set[str]:
    config = script.get("config")
    arguments = config.get("arguments") if isinstance(config, dict) else None
    if isinstance(arguments, dict):
        return {str(key) for key in arguments if str(key).strip()}
    if isinstance(arguments, list):
        return {
            str(item.get("key"))
            for item in arguments
            if isinstance(item, dict) and str(item.get("key") or "").strip()
        }
    return set()


def normalize_argument_bindings(
    argument_bindings: dict[str, str] | None,
    argument_entity_ids: dict[str, str] | None,
    *,
    view_fields: list[dict[str, Any]],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    bindings: dict[str, str] = {}
    resolved_entities: list[dict[str, Any]] = []
    for argument, provider_key in (argument_bindings or {}).items():
        normalized_argument = str(argument or "").strip()
        normalized_provider = str(provider_key or "").strip()
        if not normalized_argument:
            raise ValueError("Manual script argument names must not be empty.")
        if not normalized_provider:
            raise ValueError(f"Manual script argument {normalized_argument!r} has an empty data provider key.")
        bindings[normalized_argument] = normalized_provider
    for argument, entity_id in (argument_entity_ids or {}).items():
        normalized_argument = str(argument or "").strip()
        if not normalized_argument:
            raise ValueError("Manual script argument names must not be empty.")
        resolved = resolve_entity_id_provider_key(view_fields, str(entity_id or ""))
        existing = bindings.get(normalized_argument)
        if existing and existing != resolved["provider_key"]:
            raise ValueError(
                f"Argument {normalized_argument!r} resolves to {resolved['provider_key']!r} but also has explicit binding {existing!r}."
            )
        bindings[normalized_argument] = str(resolved["provider_key"])
        resolved_entities.append({"argument": normalized_argument, **resolved})
    return bindings, resolved_entities


def available_cell_provider_keys(cell: dict[str, Any] | None, view_fields: list[dict[str, Any]]) -> set[str]:
    keys = set(SPECIAL_DATA_PROVIDER_KEYS)
    if isinstance(cell, dict):
        displaying = cell.get("displaying")
        fields = displaying.get("fields") if isinstance(displaying, dict) else None
        if isinstance(fields, dict):
            keys.update(str(key) for key in fields)
    for field in view_fields:
        if isinstance(field, dict) and str(field.get("mname") or "").strip():
            keys.add(str(field["mname"]))
    return keys


def validate_manual_script_bindings(
    *,
    script: dict[str, Any],
    scope: str,
    bindings: dict[str, str],
    available_provider_keys: set[str],
    action_view_entity_id: str | None,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    declared = script_argument_keys(script)
    bound = set(bindings)
    for argument in sorted(declared - bound):
        issues.append(
            {
                "severity": "warning",
                "code": "manual_script_declared_argument_not_bound",
                "argument": argument,
                "message": "The script declares this argument but the form action does not bind it.",
            }
        )
    for argument in sorted(bound - declared):
        if declared:
            issues.append(
                {
                    "severity": "warning",
                    "code": "manual_script_bound_argument_not_declared",
                    "argument": argument,
                    "message": "The form action binds an argument not listed in script.config.arguments.",
                }
            )
    if scope in {"element", "value"}:
        for argument, provider_key in sorted(bindings.items()):
            if provider_key not in available_provider_keys:
                issues.append(
                    {
                        "severity": "error",
                        "code": "manual_script_provider_not_in_view",
                        "argument": argument,
                        "provider_key": provider_key,
                        "message": "The data provider key is not present in the target form cell view.",
                    }
                )
    if scope == "value" and "__entity_id" in bindings.values() and not action_view_entity_id:
        issues.append(
            {
                "severity": "error",
                "code": "manual_script_value_entity_ambiguous",
                "message": "A value action using __entity_id must declare action_view_entity_id.",
            }
        )
    return {
        "ok": not any(issue["severity"] == "error" for issue in issues),
        "declared_arguments": sorted(declared),
        "bound_arguments": sorted(bound),
        "issues": issues,
    }


def build_manual_script_action_container(
    *,
    script: dict[str, Any],
    scope: str,
    title: str,
    tooltip: str | None,
    icon_id: str,
    bindings: dict[str, str],
    action_view_entity_id: str | None,
    position: str | None,
    default: bool,
    save_before_execute: bool,
) -> dict[str, Any]:
    if scope not in FORM_SCRIPT_ACTION_SCOPES:
        raise ValueError(f"scope must be one of: {', '.join(sorted(FORM_SCRIPT_ACTION_SCOPES))}.")
    normalized_title = str(title or "").strip()
    if not normalized_title:
        raise ValueError("title must not be empty.")
    normalized_icon_id = str(icon_id or "").strip()
    if not normalized_icon_id:
        raise ValueError("icon_id must contain a project-local icon UUID.")
    script_id = str(script.get("_id") or "").strip()
    script_name = str(script.get("name") or "").strip()
    if not script_id or not script_name:
        raise ValueError("Manual script readback must contain _id and name.")
    action: dict[str, Any] = {
        "_id": script_id,
        "name": script_name,
        "type": "manual_script",
        "argumentsConfig": {
            "args": {
                argument: {"dataProviderKey": provider_key}
                for argument, provider_key in sorted(bindings.items())
            },
            "type": "context",
        },
    }
    if action_view_entity_id:
        action["viewEntityId"] = action_view_entity_id
    actions: list[dict[str, Any]] = []
    if save_before_execute:
        actions.append(
            {
                "_id": None,
                "type": "data_managing",
                "argumentsConfig": {},
                "dataManagingType": "submit_all",
            }
        )
    actions.append(action)
    return {
        "type": "action",
        "title": "" if scope == "element" else normalized_title,
        "tooltip": str(tooltip or normalized_title).strip(),
        "iconId": normalized_icon_id,
        "styles": {},
        "actions": actions,
        "position": position or ("bottom_left" if scope == "page" else "toolbar" if scope == "value" else "top_left"),
        "default": bool(default),
        "conditions": [],
    }


def upsert_manual_script_action(
    form: dict[str, Any],
    *,
    scope: str,
    action_container: dict[str, Any],
    script_id: str,
    tab_index: int | None,
    row_index: int | None,
    cell_index: int | None,
    menu_icon_id: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    updated = copy.deepcopy(form)
    cell = None
    if scope == "page":
        containers = updated.setdefault("formActionContainers", [])
        base_path = "formActionContainers"
    else:
        cell = form_cell(updated, tab_index=tab_index, row_index=row_index, cell_index=cell_index)
        key = "cellActionContainers" if scope == "element" else "valueActionContainers"
        containers = cell.setdefault(key, [])
        base_path = f"tabs[{tab_index}].rows[{row_index}].cells[{cell_index}].{key}"
    if not isinstance(containers, list):
        raise ValueError(f"{base_path} is not a list.")

    matches = _find_script_actions(containers, script_id=script_id, path=base_path)
    if len(matches) > 1:
        expected_labels = {
            str(action_container.get("title") or "").strip(),
            str(action_container.get("tooltip") or "").strip(),
        }
        expected_labels.discard("")
        labelled = [
            match
            for match in matches
            if {
                str(match["container"].get("title") or "").strip(),
                str(match["container"].get("tooltip") or "").strip(),
            }
            & expected_labels
        ]
        if len(labelled) != 1:
            raise ValueError(
                "The form contains multiple actions for this script UUID; use a unique title/tooltip before updating."
            )
        matches = labelled
    match = matches[0] if matches else None
    if match:
        parent = match["parent"]
        index = int(match["index"])
        existing_action = parent[index]
        replacement_action = action_container["actions"][-1]
        parent[index] = {**existing_action, **replacement_action}
        owner = match["container"]
        owner["title"] = action_container["title"]
        owner["tooltip"] = action_container["tooltip"]
        owner["iconId"] = action_container["iconId"]
        owner["position"] = action_container["position"]
        owner["default"] = action_container["default"]
        if len(action_container["actions"]) > 1 and not _has_submit_before(parent, index):
            parent.insert(index, action_container["actions"][0])
        return updated, {"operation": "updated", "path": match["path"], "scope": scope}

    if scope != "value":
        containers.append(action_container)
        return updated, {
            "operation": "created",
            "path": f"{base_path}[{len(containers) - 1}]",
            "scope": scope,
        }

    menu = next((item for item in containers if isinstance(item, dict) and item.get("type") == "menu"), None)
    if menu is None:
        normalized_menu_icon = str(menu_icon_id or "").strip()
        if not normalized_menu_icon:
            raise ValueError("menu_icon_id is required when a value action menu must be created.")
        menu = {
            "type": "menu",
            "title": "",
            "tooltip": "Действия",
            "iconId": normalized_menu_icon,
            "styles": {},
            "actions": [],
            "containers": [],
            "position": "toolbar",
            "conditions": [],
        }
        containers.append(menu)
    nested = menu.setdefault("containers", [])
    if not isinstance(nested, list):
        raise ValueError("The value action menu containers property is not a list.")
    nested.append(action_container)
    menu_index = containers.index(menu)
    return updated, {
        "operation": "created",
        "path": f"{base_path}[{menu_index}].containers[{len(nested) - 1}]",
        "scope": scope,
    }


def find_manual_script_action(form: dict[str, Any], script_id: str) -> dict[str, Any] | None:
    for key, scope in (("formActionContainers", "page"),):
        containers = form.get(key)
        if isinstance(containers, list):
            match = _find_script_action(containers, script_id=script_id, path=key)
            if match:
                return _public_match(match, scope)
    for tab_index, tab in enumerate(form.get("tabs") or []):
        if not isinstance(tab, dict):
            continue
        for row_index, row in enumerate(tab.get("rows") or []):
            if not isinstance(row, dict):
                continue
            for cell_index, cell in enumerate(row.get("cells") or []):
                if not isinstance(cell, dict):
                    continue
                for key, scope in (("cellActionContainers", "element"), ("valueActionContainers", "value")):
                    containers = cell.get(key)
                    if not isinstance(containers, list):
                        continue
                    path = f"tabs[{tab_index}].rows[{row_index}].cells[{cell_index}].{key}"
                    match = _find_script_action(containers, script_id=script_id, path=path)
                    if match:
                        return _public_match(match, scope)
    return None


def _find_script_action(
    containers: list[Any],
    *,
    script_id: str,
    path: str,
) -> dict[str, Any] | None:
    matches = _find_script_actions(containers, script_id=script_id, path=path)
    return matches[0] if matches else None


def _find_script_actions(
    containers: list[Any],
    *,
    script_id: str,
    path: str,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for container_index, container in enumerate(containers):
        if not isinstance(container, dict):
            continue
        container_path = f"{path}[{container_index}]"
        actions = container.get("actions")
        if isinstance(actions, list):
            for action_index, action in enumerate(actions):
                if (
                    isinstance(action, dict)
                    and str(action.get("type") or "").lower() == "manual_script"
                    and str(action.get("_id") or action.get("scriptId") or "") == script_id
                ):
                    matches.append(
                        {
                            "container": container,
                            "parent": actions,
                            "index": action_index,
                            "action": action,
                            "path": f"{container_path}.actions[{action_index}]",
                        }
                    )
        nested = container.get("containers")
        if isinstance(nested, list):
            matches.extend(
                _find_script_actions(
                    nested,
                    script_id=script_id,
                    path=f"{container_path}.containers",
                )
            )
    return matches


def _has_submit_before(actions: list[Any], action_index: int) -> bool:
    return any(
        isinstance(action, dict)
        and action.get("type") == "data_managing"
        and action.get("dataManagingType") == "submit_all"
        for action in actions[:action_index]
    )


def _public_match(match: dict[str, Any], scope: str) -> dict[str, Any]:
    action = match.get("action") if isinstance(match.get("action"), dict) else {}
    arguments_config = action.get("argumentsConfig")
    return {
        "scope": scope,
        "path": match.get("path"),
        "script_id": action.get("_id") or action.get("scriptId"),
        "script_name": action.get("name") or action.get("scriptName"),
        "arguments_config": arguments_config,
        "view_entity_id": action.get("viewEntityId"),
    }
