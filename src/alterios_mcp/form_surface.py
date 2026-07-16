from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from typing import Any

from .ux_contract import UX_CONTRACT_VERSION, apply_form_contract

VIEW_CELL_TYPES = {"view_data", "view_data_list"}
DATA_CELL_TYPES = VIEW_CELL_TYPES | {"content", "report", "comments_list", "edit_task"}
EXPECTED_ROW_ACTION_ORDER = {"edit": 0, "view": 1, "delete": 2}
TABLE_CELL_TYPES = {"view_data_list"}
REPORT_OR_ANALYTICS_TOKENS = (
    "отчет",
    "отчёт",
    "печать",
    "печатн",
    "аналит",
    "report",
    "print",
    "dashboard",
)
ADD_FORM_STEMS = ("добав",)
ADD_FORM_WORDS = {"add", "create", "new"}
EDIT_FORM_STEMS = ("редакт", "измен")
EDIT_FORM_WORDS = {"edit", "update"}
VIEW_DETAIL_FORM_STEMS = ("просмотр", "карточк")
VIEW_DETAIL_FORM_WORDS = {"detail", "view"}
TECHNICAL_LIST_FIELD_PATTERN = re.compile(r"^_id\d*$", re.IGNORECASE)
UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
SERVICE_ID_FIELD_NAMES = frozenset(
    {
        "id",
        "contentid",
        "contenttypeid",
        "entityid",
        "formid",
        "projectid",
        "reportid",
        "scriptid",
        "viewentityid",
        "viewid",
    }
)
FOOTNOTE_KEYS = {
    "bottomText",
    "bottom_text",
    "footerText",
    "footer_text",
    "footnote",
    "footNote",
    "helperText",
    "helper_text",
    "helpText",
    "help_text",
    "note",
    "noteText",
    "note_text",
    "description",
    "hint",
}
FIELD_TYPE_KEYS = {
    "type",
    "fieldType",
    "field_type",
    "dataType",
    "data_type",
    "valueType",
    "value_type",
    "contentTypeFieldType",
    "content_type_field_type",
    "inputType",
    "input_type",
}


def analyze_form_surface(
    form: dict[str, Any],
    field_type_map: dict[str, str] | None = None,
    *,
    strict: bool = False,
) -> dict[str, Any]:
    """Analyze Alterios form JSON for view/form UX and action guardrails."""
    issues: list[dict[str, Any]] = []
    inventory: dict[str, Any] = {
        "form_id": form.get("_id"),
        "name": form.get("name"),
        "page_title": form.get("pageTitle"),
        "tab_count": 0,
        "row_count": 0,
        "cell_count": 0,
        "cell_types": {},
        "action_container_count": 0,
        "action_count": 0,
        "action_icons": [],
        "style_keys": {},
        "data_sources": [],
        "role_keys": [],
        "page_titles": [],
        "headers": [],
        "field_footnotes": [],
    }

    if not str(form.get("pageTitle") or "").strip():
        _add_issue(issues, "warning", "missing_page_title", "Form has no user-facing pageTitle.", "pageTitle")

    tabs = form.get("tabs")
    if not isinstance(tabs, list) or not tabs:
        _add_issue(issues, "warning", "missing_tabs", "Form has no tabs.", "form")
        tabs = []
    inventory["tab_count"] = len(tabs)

    cell_types: Counter[str] = Counter()
    style_keys: Counter[str] = Counter()
    action_icons: list[str] = []
    data_sources: list[dict[str, Any]] = []
    role_keys: list[dict[str, Any]] = []
    page_titles: list[str] = []
    headers: list[str] = []
    field_footnotes: list[dict[str, Any]] = []
    view_data_cells: list[tuple[dict[str, Any], str]] = []
    report_cells: list[tuple[dict[str, Any], str]] = []

    _collect_role_keys(form, role_keys)
    _collect_titles(form, page_titles, headers)

    for tab_index, tab in enumerate(tabs):
        tab_path = f"tabs[{tab_index}]"
        if not isinstance(tab, dict):
            _add_issue(issues, "warning", "invalid_tab", "Tab is not an object.", tab_path)
            continue
        rows = _rows_from_tab(tab)
        if not rows:
            _add_issue(issues, "warning", "empty_tab", "Tab has no rows/cells.", tab_path)
            continue
        inventory["row_count"] += len(rows)
        for row_index, row in enumerate(rows):
            row_path = f"{tab_path}.rows[{row_index}]"
            cells = _cells_from_row(row)
            if not cells:
                _add_issue(issues, "warning", "empty_row", "Row has no cells.", row_path)
                continue
            _analyze_row_gaps(issues, cells, row_path)
            for cell_index, cell in enumerate(cells):
                cell_path = f"{row_path}.cells[{cell_index}]"
                if not isinstance(cell, dict):
                    _add_issue(issues, "warning", "invalid_cell", "Cell is not an object.", cell_path)
                    continue
                inventory["cell_count"] += 1
                cell_type = str(cell.get("type") or "unknown")
                cell_types[cell_type] += 1
                if cell_type == "view_data":
                    view_data_cells.append((cell, cell_path))
                elif cell_type == "report":
                    report_cells.append((cell, cell_path))
                _collect_style_keys(cell.get("styles"), style_keys)
                _collect_data_source(cell, cell_path, data_sources)
                _analyze_cell(cell, cell_path, issues, field_type_map or {}, field_footnotes)
                _analyze_action_containers(cell.get("cellActionContainers"), f"{cell_path}.cellActionContainers", issues, action_icons)
                _analyze_action_containers(
                    cell.get("valueActionContainers"),
                    f"{cell_path}.valueActionContainers",
                    issues,
                    action_icons,
                    row_actions=True,
                )
                if cell_type == "view_data_list":
                    _analyze_list_row_action_contract(
                        cell.get("valueActionContainers"),
                        f"{cell_path}.valueActionContainers",
                        issues,
                    )

    top_actions = form.get("formActionContainers")
    _analyze_action_containers(top_actions, "formActionContainers", issues, action_icons)
    _analyze_close_action_routing(top_actions, "formActionContainers", issues)
    _analyze_view_detail_editing(form, view_data_cells, issues)
    _analyze_page_action_contract(form, view_data_cells, report_cells, issues)

    inventory["cell_types"] = dict(sorted(cell_types.items()))
    inventory["style_keys"] = dict(sorted(style_keys.items()))
    inventory["action_container_count"] = _count_action_containers(form)
    inventory["action_count"] = _count_actions(form)
    inventory["action_icons"] = sorted(set(action_icons))
    inventory["data_sources"] = data_sources
    inventory["role_keys"] = role_keys
    inventory["page_titles"] = sorted(set(page_titles))
    inventory["headers"] = sorted(set(headers))
    inventory["field_footnotes"] = field_footnotes

    issues = apply_form_contract(issues, strict=strict)
    issue_counts = Counter(issue["code"] for issue in issues)
    severity_counts = Counter(issue["severity"] for issue in issues)
    blocking_issues = [issue for issue in issues if issue["severity"] == "error"]
    blocking_issue_counts = Counter(issue["code"] for issue in blocking_issues)
    return {
        "ok": not blocking_issues,
        "validation_profile": "contract" if strict else "default",
        "contract_version": UX_CONTRACT_VERSION,
        "blocking_issue_count": len(blocking_issues),
        "blocking_issues_by_code": dict(sorted(blocking_issue_counts.items())),
        "issue_count": len(issues),
        "issues_by_code": dict(sorted(issue_counts.items())),
        "issues_by_severity": dict(sorted(severity_counts.items())),
        "issues": issues,
        "inventory": inventory,
    }


def _add_issue(
    issues: list[dict[str, Any]],
    severity: str,
    code: str,
    message: str,
    path: str,
    details: dict[str, Any] | None = None,
) -> None:
    issue: dict[str, Any] = {
        "severity": severity,
        "code": code,
        "message": message,
        "path": path,
    }
    if details:
        issue["details"] = details
    issues.append(issue)


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
    if row.get("type"):
        return [row]
    return []


def _is_empty_cell(cell: Any) -> bool:
    if cell in (None, "", {}, []):
        return True
    if isinstance(cell, dict):
        if str(cell.get("type") or "").lower() in {"empty", "spacer", "placeholder"}:
            return True
        if not cell.get("type") and not cell.get("name") and not cell.get("params") and not cell.get("children"):
            return True
    return False


def _analyze_row_gaps(issues: list[dict[str, Any]], cells: list[Any], row_path: str) -> None:
    nonempty = [cell for cell in cells if not _is_empty_cell(cell)]
    if len(nonempty) != len(cells):
        _add_issue(
            issues,
            "warning",
            "empty_layout_slot",
            "Row contains an empty layout slot; view/content rows should not leave visible gaps.",
            row_path,
        )
    if not nonempty:
        return
    view_cells = [cell for cell in nonempty if isinstance(cell, dict) and cell.get("type") in VIEW_CELL_TYPES]
    if view_cells and len(nonempty) > 1:
        _add_issue(
            issues,
            "warning",
            "view_content_not_full_row",
            "View content shares a row with other cells; primary list/detail content should occupy the row.",
            row_path,
            {"view_cell_count": len(view_cells), "nonempty_cell_count": len(nonempty)},
        )


def _analyze_cell(
    cell: dict[str, Any],
    path: str,
    issues: list[dict[str, Any]],
    field_type_map: dict[str, str],
    field_footnotes: list[dict[str, Any]],
) -> None:
    cell_type = str(cell.get("type") or "")
    if not cell_type:
        _add_issue(issues, "warning", "missing_cell_type", "Cell has no type.", path)
        return
    _analyze_cell_header(cell, cell_type, path, issues)
    _analyze_displaying_field_footnotes(cell, path, issues, field_type_map, field_footnotes)
    if cell_type in DATA_CELL_TYPES and not _has_flexible_width(cell):
        _add_issue(
            issues,
            "warning",
            "data_cell_missing_full_width_style",
            "Data-heavy cell has no obvious full-width/flex style.",
            path,
            {"cell_type": cell_type},
        )
    if cell_type in VIEW_CELL_TYPES:
        params = _dict_or_empty(cell.get("params"))
        if not params.get("viewId"):
            _add_issue(issues, "error", "missing_view_source", "View cell has no params.viewId.", path)
        if not _embedded_view_has_filter_or_context(cell):
            _add_issue(
                issues,
                "warning",
                "embedded_view_missing_filter_or_context",
                "Embedded view_data/view_data_list must have a field-based filter or dataId/openId context.",
                path,
                {"cell_type": cell_type, "view_id": params.get("viewId")},
            )
        displaying = _dict_or_empty(cell.get("displaying"))
        if not isinstance(displaying.get("fields"), dict) or not displaying.get("fields"):
            _add_issue(
                issues,
                "warning",
                "missing_displaying_fields",
                "View cell has no displaying.fields map, so user-facing columns may be incomplete.",
                path,
            )
        if cell_type == "view_data_list":
            _analyze_technical_list_fields(displaying, path, issues)
    elif cell_type == "content":
        params = _dict_or_empty(cell.get("params"))
        if not params.get("contentTypeId"):
            _add_issue(issues, "error", "missing_content_type_source", "Content cell has no params.contentTypeId.", path)
    elif cell_type == "report":
        params = _dict_or_empty(cell.get("params"))
        if not params.get("reportId"):
            _add_issue(issues, "error", "missing_report_source", "Report cell has no params.reportId.", path)
        if params.get("openId") is not True:
            _add_issue(
                issues,
                "info",
                "report_without_openid",
                "Report cell is not explicitly bound to the current record through params.openId=true.",
                path,
            )
    elif cell_type == "comments_list":
        params = _dict_or_empty(cell.get("params"))
        if params.get("openId") is not True:
            _add_issue(
                issues,
                "warning",
                "comments_without_openid",
                "Comments cell is not explicitly bound to the current record through params.openId=true.",
                path,
            )
        if not params.get("entity"):
            _add_issue(issues, "info", "comments_without_entity_scope", "Comments cell has no params.entity scope.", path)


def _analyze_displaying_field_footnotes(
    cell: dict[str, Any],
    path: str,
    issues: list[dict[str, Any]],
    field_type_map: dict[str, str],
    field_footnotes: list[dict[str, Any]],
) -> None:
    displaying = _dict_or_empty(cell.get("displaying"))
    fields = displaying.get("fields")
    if not isinstance(fields, dict):
        return
    for field_name, field_config in fields.items():
        if not isinstance(field_config, dict) or field_config.get("hidden") is True:
            continue
        footnotes = _field_footnotes(field_config, f"{path}.displaying.fields.{field_name}")
        if not footnotes:
            continue
        field_type = _displaying_field_type(str(field_name), field_config, field_type_map)
        for footnote in footnotes:
            item = {
                "path": footnote["path"],
                "field": str(field_name),
                "key": footnote["key"],
                "field_type": field_type or "<unknown>",
            }
            field_footnotes.append(item)
            if not _is_date_type(field_type):
                _add_issue(
                    issues,
                    "warning",
                    "field_footnote_requires_date",
                    "Persistent bottom helper/footnote text is allowed only for date fields; use label, tooltip, placeholder, or a help block for other fields.",
                    footnote["path"],
                    item,
                )


def _field_footnotes(field_config: dict[str, Any], path: str) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []

    def walk(value: Any, current_path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{current_path}.{key}"
                if str(key) in FOOTNOTE_KEYS and _has_visible_footnote_text(child):
                    found.append({"path": child_path, "key": str(key)})
                if isinstance(child, (dict, list)):
                    walk(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                if isinstance(child, (dict, list)):
                    walk(child, f"{current_path}[{index}]")

    walk(field_config, path)
    return found


def _has_visible_footnote_text(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        text = value.get("text") or value.get("value") or value.get("title")
        return isinstance(text, str) and bool(text.strip())
    if isinstance(value, list):
        return any(_has_visible_footnote_text(item) for item in value)
    return False


def _displaying_field_type(field_name: str, field_config: dict[str, Any], field_type_map: dict[str, str]) -> str:
    mapped = field_type_map.get(field_name)
    if mapped:
        return str(mapped)
    discovered = _find_type_value(field_config)
    return str(discovered or "")


def _find_type_value(value: Any) -> str:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key) in FIELD_TYPE_KEYS and isinstance(child, str) and child.strip():
                return child
        for child in value.values():
            nested = _find_type_value(child)
            if nested:
                return nested
    elif isinstance(value, list):
        for child in value:
            nested = _find_type_value(child)
            if nested:
                return nested
    return ""


def _is_date_type(field_type: str) -> bool:
    normalized = str(field_type or "").strip().lower()
    return normalized in {"date", "datetime", "date_time", "date-time"} or normalized.startswith("date:")


def _embedded_view_has_filter_or_context(cell: dict[str, Any]) -> bool:
    params = _dict_or_empty(cell.get("params"))
    open_id = params.get("openId")
    if open_id is True or _references_open_id(open_id):
        return True
    for owner in (cell, params):
        data_id = owner.get("dataId")
        if data_id not in (None, "", False, [], {}):
            return True
    displaying = _dict_or_empty(cell.get("displaying"))
    fields = displaying.get("fields")
    if isinstance(fields, dict):
        for field_config in fields.values():
            if not isinstance(field_config, dict):
                continue
            field_filter = field_config.get("filter")
            if isinstance(field_filter, dict) and field_filter and field_filter.get("enabled") is not False:
                return True
            if field_filter is True:
                return True
    for owner in (cell, params, displaying):
        for key in ("userFilters", "fieldFilters"):
            configured = owner.get(key)
            if not isinstance(configured, dict):
                continue
            configured_fields = configured.get("fields")
            if isinstance(configured_fields, dict) and configured_fields:
                return True
    return False


def _references_open_id(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() in {"openid", "[openid]", "{{openid}}"}
    if isinstance(value, dict):
        return any(_references_open_id(child) for child in value.values())
    if isinstance(value, list):
        return any(_references_open_id(child) for child in value)
    return False


def _analyze_technical_list_fields(
    displaying: dict[str, Any],
    path: str,
    issues: list[dict[str, Any]],
) -> None:
    fields = displaying.get("fields")
    if not isinstance(fields, dict):
        return
    for field_name, field_config in fields.items():
        if not _is_technical_list_field(str(field_name)) or _field_is_hidden(field_config):
            continue
        _add_issue(
            issues,
            "warning",
            "technical_list_field_must_be_hidden",
            "Technical and service ID fields must be hidden in list displaying.",
            f"{path}.displaying.fields.{field_name}",
            {"field": str(field_name)},
        )


def _is_technical_list_field(field_name: str) -> bool:
    normalized = field_name.strip().casefold()
    if TECHNICAL_LIST_FIELD_PATTERN.fullmatch(normalized):
        return True
    compact = re.sub(r"[_-]", "", normalized)
    return compact in SERVICE_ID_FIELD_NAMES


def _field_is_hidden(field_config: Any) -> bool:
    if not isinstance(field_config, dict):
        return False
    hidden = field_config.get("hidden")
    return hidden is True or (isinstance(hidden, str) and hidden.strip().casefold() == "true")


def _analyze_cell_header(cell: dict[str, Any], cell_type: str, path: str, issues: list[dict[str, Any]]) -> None:
    header_path = f"{path}.header"
    header = cell.get("header")
    if not isinstance(header, dict):
        displaying = _dict_or_empty(cell.get("displaying"))
        header = displaying.get("header")
        header_path = f"{path}.displaying.header"
    if not isinstance(header, dict):
        return
    title = str(header.get("title") or "").strip()
    if not title:
        return
    if cell_type not in TABLE_CELL_TYPES:
        _add_issue(
            issues,
            "warning",
            "non_table_cell_header",
            "Non-table cells should not render a visible cell header; use field labels, page titles, or help text instead.",
            header_path,
            {"cell_type": cell_type, "title": title},
        )
        return
    styles = _dict_or_empty(header.get("styles"))
    text_align = str(styles.get("textAlign") or styles.get("text-align") or "").lower()
    font_weight = str(styles.get("fontWeight") or styles.get("font-weight") or "").lower()
    if text_align != "center" or font_weight not in {"bold", "600", "700", "800", "900"}:
        _add_issue(
            issues,
            "warning",
            "table_cell_header_style",
            "Table cell headers must be centered and bold.",
            header_path,
            {
                "title": title,
                "textAlign": styles.get("textAlign") or styles.get("text-align"),
                "fontWeight": styles.get("fontWeight") or styles.get("font-weight"),
            },
        )
    padding_top = styles.get("paddingTop", styles.get("padding-top"))
    normalized_padding = str(padding_top or "").strip().lower().removesuffix("px")
    try:
        padding_value = float(normalized_padding)
    except ValueError:
        padding_value = -1
    if padding_value != 10:
        _add_issue(
            issues,
            "warning",
            "table_cell_header_top_padding",
            "Table cell headers must have a 10px top padding.",
            header_path,
            {"title": title, "paddingTop": padding_top},
        )


def _analyze_close_action_routing(containers: Any, path: str, issues: list[dict[str, Any]]) -> None:
    if not isinstance(containers, list):
        return
    for index, container in enumerate(containers):
        if not isinstance(container, dict):
            continue
        container_path = f"{path}[{index}]"
        close_path = container_path if _is_close_action(container) else ""
        actions = container.get("actions")
        if isinstance(actions, list):
            for action_index, action in enumerate(actions):
                if isinstance(action, dict) and _is_close_action(action):
                    close_path = f"{container_path}.actions[{action_index}]"
                    break
        if close_path and not _contains_redirect_back(container):
            _add_issue(
                issues,
                "warning",
                "close_action_missing_redirect_back",
                "The Close action must contain routingType=redirect_back.",
                close_path,
            )


def _is_close_action(action: dict[str, Any]) -> bool:
    for key in ("title", "name", "tooltip"):
        label = str(action.get(key) or "").strip().casefold().rstrip(".:")
        if label in {"закрыть", "close"}:
            return True
    return False


def _contains_redirect_back(value: Any) -> bool:
    if isinstance(value, dict):
        if str(value.get("routingType") or "").strip().casefold() == "redirect_back":
            return True
        return any(_contains_redirect_back(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_redirect_back(child) for child in value)
    return False


def _analyze_page_action_contract(
    form: dict[str, Any],
    view_data_cells: list[tuple[dict[str, Any], str]],
    report_cells: list[tuple[dict[str, Any], str]],
    issues: list[dict[str, Any]],
) -> None:
    top_actions = form.get("formActionContainers")
    form_kind = _explicit_form_kind(form)
    if form_kind == "add" and not str(form.get("pageTitle") or "").strip().casefold().startswith(("добавить ", "add ")):
        _add_issue(
            issues,
            "warning",
            "add_page_title_must_start_with_add",
            "An add form pageTitle must use the pattern 'Добавить {сущность}'.",
            "pageTitle",
            {"pageTitle": form.get("pageTitle")},
        )
    if form_kind in {"add", "edit"}:
        observed = _page_action_categories(top_actions)
        if observed[:2] != ["close", "save"]:
            _add_issue(
                issues,
                "warning",
                "add_edit_page_action_order",
                "Add/edit page actions must start with Close and then Save.",
                "formActionContainers",
                {"form_kind": form_kind, "observed": observed},
            )

    has_close = _contains_close_action(top_actions)
    if form_kind == "view_detail" and view_data_cells and not _form_has_submit_action(top_actions) and not has_close:
        _add_issue(
            issues,
            "warning",
            "view_detail_close_action_missing",
            "A view/detail form must have a Close page action.",
            "formActionContainers",
        )
    if report_cells and not has_close:
        _add_issue(
            issues,
            "warning",
            "report_or_analytics_target_missing_close",
            "A printable or analytical target form with a report cell must have a Close page action.",
            "formActionContainers",
            {"report_cell_paths": [path for _, path in report_cells]},
        )


def _explicit_form_kind(form: dict[str, Any]) -> str:
    text = f"{form.get('name') or ''} {form.get('pageTitle') or ''}".casefold()
    english_words = set(re.findall(r"[a-z]+", text))
    if any(stem in text for stem in ADD_FORM_STEMS) or english_words & ADD_FORM_WORDS:
        return "add"
    if any(stem in text for stem in EDIT_FORM_STEMS) or english_words & EDIT_FORM_WORDS:
        return "edit"
    if any(stem in text for stem in VIEW_DETAIL_FORM_STEMS) or english_words & VIEW_DETAIL_FORM_WORDS:
        return "view_detail"
    return ""


def _page_action_categories(containers: Any) -> list[str]:
    if not isinstance(containers, list):
        return []
    categories: list[str] = []
    for container in containers:
        if not isinstance(container, dict):
            continue
        if _contains_close_action(container):
            categories.append("close")
        elif _is_save_action(container):
            categories.append("save")
        else:
            categories.append("other")
    return categories


def _contains_close_action(value: Any) -> bool:
    if isinstance(value, dict):
        return _is_close_action(value) or any(_contains_close_action(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_close_action(child) for child in value)
    return False


def _is_save_action(value: dict[str, Any]) -> bool:
    for key in ("title", "name", "tooltip"):
        label = str(value.get(key) or "").strip().casefold().rstrip(".:")
        if label.startswith("сохран") or label.startswith("save"):
            return True
    return _form_has_submit_action(value)


def _analyze_view_detail_editing(
    form: dict[str, Any],
    view_data_cells: list[tuple[dict[str, Any], str]],
    issues: list[dict[str, Any]],
) -> None:
    if _form_has_submit_action(form.get("formActionContainers")):
        return
    form_kind = _explicit_form_kind(form)
    for cell, path in view_data_cells:
        editing = _dict_or_empty(cell.get("editing"))
        if editing.get("enabled") is True:
            _add_issue(
                issues,
                "warning",
                "view_detail_view_data_must_be_readonly",
                "A view/detail surface must not explicitly enable view_data editing; use a submit-enabled edit form.",
                f"{path}.editing.enabled",
                {"editing_enabled": True, "surface": "view/detail"},
            )
        if form_kind != "view_detail":
            continue
        fields = _dict_or_empty(_dict_or_empty(cell.get("displaying")).get("fields"))
        for field_name, raw_config in fields.items():
            config = _dict_or_empty(raw_config)
            if _field_is_hidden(config):
                continue
            if config.get("inputConfig") not in (None, {}):
                _add_issue(
                    issues,
                    "warning",
                    "view_detail_field_input_config_present",
                    "Visible fields in a view/detail form must not expose an inputConfig.",
                    f"{path}.displaying.fields.{field_name}.inputConfig",
                )
            if not isinstance(config.get("outputConfig"), dict):
                _add_issue(
                    issues,
                    "warning",
                    "view_detail_field_output_config_missing",
                    "Visible fields in a view/detail form must define outputConfig for read-only rendering.",
                    f"{path}.displaying.fields.{field_name}.outputConfig",
                )


def _form_has_submit_action(value: Any) -> bool:
    if isinstance(value, dict):
        action_type = str(value.get("type") or "").strip().casefold()
        data_managing_type = str(value.get("dataManagingType") or "").strip().casefold()
        if action_type in {"save", "submit"}:
            return True
        if data_managing_type in {"save", "save_all", "submit", "submit_all"}:
            return True
        return any(_form_has_submit_action(child) for child in value.values())
    if isinstance(value, list):
        return any(_form_has_submit_action(child) for child in value)
    return False


def _has_flexible_width(cell: dict[str, Any]) -> bool:
    styles = _dict_or_empty(cell.get("styles"))
    values = [str(value).lower() for value in styles.values()]
    if any(value in {"100%", "stretch", "full"} for value in values):
        return True
    flex = str(styles.get("flex") or "").lower()
    if flex.startswith("1") or "1 1" in flex:
        return True
    for key in ("flexGrow", "flex-grow", "gridColumn", "grid-column"):
        value = styles.get(key)
        if value in (1, "1") or str(value).lower() in {"1 / -1", "span 12"}:
            return True
    return False


def _analyze_action_containers(
    containers: Any,
    path: str,
    issues: list[dict[str, Any]],
    action_icons: list[str],
    *,
    row_actions: bool = False,
) -> None:
    if containers is None:
        return
    if not isinstance(containers, list):
        _add_issue(issues, "warning", "invalid_action_container_list", "Action containers value is not a list.", path)
        return
    is_top_level_element_actions = ".cellActionContainers" in path and ".containers" not in path
    if is_top_level_element_actions and len(containers) > 3 and not any(
        isinstance(container, dict) and str(container.get("type") or "").strip().casefold() == "menu"
        for container in containers
    ):
        _add_issue(
            issues,
            "warning",
            "element_actions_must_use_menu",
            "More than three element actions must be grouped in a menu.",
            path,
            {"action_container_count": len(containers)},
        )
    known_order: list[tuple[str, str]] = []
    for index, container in enumerate(containers):
        container_path = f"{path}[{index}]"
        if not isinstance(container, dict):
            _add_issue(issues, "warning", "invalid_action_container", "Action container is not an object.", container_path)
            continue
        container_type = str(container.get("type") or "").lower()
        if container_type == "menu":
            container_icon = _action_icon(container)
            if container_icon:
                action_icons.append(container_icon)
            nested = container.get("containers")
            if not isinstance(nested, list) or not nested:
                if row_actions:
                    _add_issue(
                        issues,
                        "warning",
                        "row_menu_missing_containers",
                        "Row menu must contain nested action containers in containers[].",
                        container_path,
                    )
            elif row_actions and _row_menu_has_view(nested) and not _row_menu_has_default_view(nested):
                _add_issue(
                    issues,
                    "warning",
                    "row_menu_default_view_missing",
                    "Row menu should mark the view action container as default.",
                    container_path,
                )
            if isinstance(nested, list):
                _analyze_action_containers(nested, f"{container_path}.containers", issues, action_icons, row_actions=row_actions)
        actions = container.get("actions")
        if actions is None:
            actions = [container] if _looks_like_action(container) else []
        if not isinstance(actions, list):
            _add_issue(issues, "warning", "invalid_action_list", "Container actions value is not a list.", container_path)
            continue
        if row_actions and len(actions) > 1:
            _add_issue(
                issues,
                "warning",
                "row_action_container_should_be_menu",
                "A row menu must use type=menu with nested containers[]; do not place multiple row actions in one action container.",
                container_path,
            )
        if row_actions and len(actions) > 3:
            _add_issue(
                issues,
                "info",
                "row_actions_should_use_more_menu",
                "A row has many direct actions; secondary actions should be grouped behind a more_vert menu.",
                container_path,
            )
        container_icon = _action_icon(container)
        container_title = str(container.get("title") or container.get("name") or "").strip()
        is_nested_menu_item = ".containers" in path
        if container_icon:
            action_icons.append(container_icon)
        is_element_action = ".cellActionContainers" in path
        is_action_hub_item = is_element_action and str(container.get("position") or "").lower() == "top_center"
        if container_title and is_element_action and not is_nested_menu_item and not is_action_hub_item:
            _add_issue(
                issues,
                "warning",
                "element_action_title_must_be_tooltip",
                "Element actions must render as icon-only; move visible text to tooltip and clear the outer title.",
                container_path,
                {"title": container_title, "icon": container_icon or None},
            )
        elif container_icon and container_title and not is_nested_menu_item:
            _add_issue(
                issues,
                "info",
                "action_title_should_be_tooltip",
                "Action has both title and icon; verify the UI renders the title as tooltip/menu text, not as a wide text button.",
                container_path,
                {"title": container_title, "icon": container_icon},
            )
        for action_index, action in enumerate(actions):
            action_path = f"{container_path}.actions[{action_index}]"
            if not isinstance(action, dict):
                _add_issue(issues, "warning", "invalid_action", "Action is not an object.", action_path)
                continue
            icon = _action_icon(action) or container_icon
            if icon:
                action_icons.append(icon)
            else:
                _add_issue(
                    issues,
                    "warning",
                    "row_action_missing_icon" if row_actions else "missing_action_icon",
                    "Visible form/list action has no icon; Alterios actions should be icon-first.",
                    action_path,
                )
            title = str(action.get("title") or "").strip()
            if title and is_element_action and not is_nested_menu_item:
                _add_issue(
                    issues,
                    "warning",
                    "element_action_title_must_be_tooltip",
                    "Element actions must render as icon-only; move visible text to tooltip and clear the action title.",
                    action_path,
                    {"title": title, "icon": icon or None},
                )
            elif icon and title:
                _add_issue(
                    issues,
                    "info",
                    "action_title_should_be_tooltip",
                    "Action has both title and icon; verify the UI renders the title as tooltip/menu text, not as a wide text button.",
                    action_path,
                    {"title": title, "icon": icon},
                )
            category = _action_category(action, container)
            if category == "manual_script":
                _analyze_manual_script_action(
                    action,
                    action_path,
                    issues,
                    row_action=row_actions,
                )
            _analyze_report_or_analytics_opening(action, container, action_path, issues)
            if row_actions and category:
                known_order.append((category, action_path))
            if category == "delete" and row_actions:
                delete_index = EXPECTED_ROW_ACTION_ORDER["delete"]
                if any(EXPECTED_ROW_ACTION_ORDER.get(category, delete_index) > delete_index for category, _ in known_order):
                    _add_issue(
                        issues,
                        "warning",
                        "delete_action_order",
                        "Delete must remain the last destructive row action.",
                        action_path,
                    )
    if row_actions:
        order_values = [EXPECTED_ROW_ACTION_ORDER[category] for category, _ in known_order if category in EXPECTED_ROW_ACTION_ORDER]
        if order_values != sorted(order_values):
            _add_issue(
                issues,
                "warning",
                "row_action_order",
                "Row action order should be: edit, view, delete.",
                path,
                {"observed": [category for category, _ in known_order]},
            )


def _analyze_manual_script_action(
    action: dict[str, Any],
    path: str,
    issues: list[dict[str, Any]],
    *,
    row_action: bool,
) -> None:
    script_id = str(
        action.get("scriptId")
        or action.get("manualScriptId")
        or action.get("_id")
        or ""
    ).strip()
    if not UUID_PATTERN.fullmatch(script_id):
        _add_issue(
            issues,
            "warning",
            "manual_script_id_must_be_uuid",
            "A manual script form action must reference a saved script UUID.",
            path,
            {"script_id": script_id or None},
        )
    config = action.get("argumentsConfig")
    if config is None:
        return
    if not isinstance(config, dict):
        _add_issue(
            issues,
            "warning",
            "manual_script_arguments_config_invalid",
            "Manual script argumentsConfig must be an object.",
            f"{path}.argumentsConfig",
        )
        return
    if config.get("type") not in {None, "context"}:
        _add_issue(
            issues,
            "warning",
            "manual_script_arguments_config_type",
            "Manual script form actions should use argumentsConfig.type=context.",
            f"{path}.argumentsConfig.type",
            {"type": config.get("type")},
        )
    raw_bindings = config.get("args") if isinstance(config.get("args"), dict) else config
    sources: list[str] = []
    for argument, binding in raw_bindings.items():
        if argument in {"args", "type", "view_id"}:
            continue
        source = None
        if isinstance(binding, dict):
            source = binding.get("dataProviderKey") or binding.get("source")
        elif isinstance(binding, str):
            source = binding
        normalized_source = str(source or "").strip()
        if not normalized_source:
            _add_issue(
                issues,
                "warning",
                "manual_script_empty_argument_binding",
                "Manual script argument binding must contain dataProviderKey.",
                f"{path}.argumentsConfig.args.{argument}",
                {"argument": str(argument)},
            )
        else:
            sources.append(normalized_source)
    if row_action and "__entity_id" in sources and not action.get("viewEntityId"):
        _add_issue(
            issues,
            "warning",
            "manual_script_value_entity_ambiguous",
            "A row value action using __entity_id must declare viewEntityId.",
            path,
        )


def _analyze_list_row_action_contract(
    containers: Any,
    path: str,
    issues: list[dict[str, Any]],
) -> None:
    if not isinstance(containers, list) or not containers:
        return
    menus: list[tuple[int, dict[str, Any]]] = []
    non_menu_paths: list[str] = []
    for index, container in enumerate(containers):
        if not isinstance(container, dict):
            continue
        if str(container.get("type") or "").strip().casefold() == "menu":
            menus.append((index, container))
        else:
            non_menu_paths.append(f"{path}[{index}]")
    if non_menu_paths:
        _add_issue(
            issues,
            "warning",
            "list_row_actions_must_be_menu",
            "Configured list row actions must use outer type=menu containers.",
            path,
            {"non_menu_paths": non_menu_paths},
        )
    if not menus:
        return

    menu_summaries: list[tuple[int, dict[str, Any], set[str]]] = []
    missing_icon_paths: list[str] = []
    for index, menu in menus:
        menu_path = f"{path}[{index}]"
        if not _action_icon(menu):
            missing_icon_paths.append(menu_path)
        nested = menu.get("containers")
        nested_items = nested if isinstance(nested, list) else []
        categories: set[str] = set()
        for nested_index, nested_container in enumerate(nested_items):
            if not isinstance(nested_container, dict):
                continue
            nested_path = f"{menu_path}.containers[{nested_index}]"
            nested_categories = _row_action_container_categories(nested_container)
            categories.update(nested_categories)
            actions = nested_container.get("actions")
            action_items = actions if isinstance(actions, list) else []
            has_icon = bool(_action_icon(nested_container)) or any(
                isinstance(action, dict) and bool(_action_icon(action)) for action in action_items
            )
            if (nested_categories or action_items) and not has_icon:
                missing_icon_paths.append(nested_path)
        menu_summaries.append((index, menu, categories))

    required = set(EXPECTED_ROW_ACTION_ORDER)
    _, _, best_categories = max(menu_summaries, key=lambda item: len(item[2] & required))
    missing_categories = sorted(required - best_categories, key=EXPECTED_ROW_ACTION_ORDER.get)
    if missing_categories:
        _add_issue(
            issues,
            "warning",
            "list_row_menu_actions_missing",
            "The list row menu must contain edit, view, and delete actions.",
            path,
            {"missing": missing_categories},
        )
    if missing_icon_paths:
        _add_issue(
            issues,
            "warning",
            "list_row_action_icon_missing",
            "The outer row menu and every configured row action must have an icon.",
            path,
            {"missing_icon_paths": missing_icon_paths},
        )


def _row_action_container_categories(container: dict[str, Any]) -> set[str]:
    actions = container.get("actions")
    action_items = actions if isinstance(actions, list) else []
    categories: set[str] = set()
    for action in action_items:
        if not isinstance(action, dict):
            continue
        category = _action_category(action, container)
        if category:
            categories.add(category)
    container_category = _action_category(container)
    if container_category:
        categories.add(container_category)
    return categories


def _row_menu_has_view(containers: list[Any]) -> bool:
    return any(
        isinstance(container, dict) and "view" in _row_action_container_categories(container)
        for container in containers
    )


def _row_menu_has_default_view(containers: list[Any]) -> bool:
    for container in containers:
        if not isinstance(container, dict) or container.get("default") is not True:
            continue
        actions = container.get("actions")
        if not isinstance(actions, list):
            actions = [container] if _looks_like_action(container) else []
        if any(isinstance(action, dict) and _action_category(action, container) == "view" for action in actions):
            return True
        if not actions and _action_category(container) == "view":
            return True
    return False


def _action_icon(action: dict[str, Any]) -> str:
    for key in ("icon", "iconId", "materialIcon", "iconName"):
        value = action.get(key)
        if value:
            return str(value)
    return ""


def _looks_like_action(value: dict[str, Any]) -> bool:
    return any(key in value for key in ("action", "type", "iconId", "dataManagingType", "openInDialog", "openInNewTab"))


def _action_category(action: dict[str, Any], container: dict[str, Any] | None = None) -> str:
    action_type = str(action.get("type") or "").strip().lower()
    if action_type in {"manual_script", "script", "scripts"} or any(
        key in action for key in ("scriptId", "manualScriptId", "scriptName")
    ):
        return "manual_script"
    items = [action]
    if container:
        items.append(container)
    haystack = " ".join(
        str(item.get(key) or "").lower()
        for item in items
        for key in ("title", "name", "type", "dataManagingType", "action", "operation", "icon", "iconId", "materialIcon")
    )
    if any(token in haystack for token in ("delete", "remove", "удал")):
        return "delete"
    if any(token in haystack for token in ("edit", "update", "редакт", "измен")):
        return "edit"
    if any(token in haystack for token in ("view", "open", "show", "просмотр", "открыт")):
        return "view"
    return ""


def _analyze_report_or_analytics_opening(
    action: dict[str, Any],
    container: dict[str, Any],
    action_path: str,
    issues: list[dict[str, Any]],
) -> None:
    if str(action.get("type") or "").lower() != "forms":
        return
    haystack = " ".join(
        str(value or "")
        for value in (
            action.get("name"),
            action.get("title"),
            container.get("name"),
            container.get("title"),
            container.get("tooltip"),
        )
    ).lower()
    if not any(token in haystack for token in REPORT_OR_ANALYTICS_TOKENS):
        return
    if action.get("openInNewTab") is True and action.get("openInDialog") is not True:
        return
    _add_issue(
        issues,
        "warning",
        "report_or_analytics_form_should_open_new_tab",
        "Analytical and printable forms must open in a new tab, not in a dialog.",
        action_path,
        {
            "name": action.get("name"),
            "openInNewTab": action.get("openInNewTab"),
            "openInDialog": action.get("openInDialog"),
        },
    )


def _collect_style_keys(styles: Any, counter: Counter[str]) -> None:
    if not isinstance(styles, dict):
        return
    for key in styles:
        counter[str(key)] += 1


def _collect_data_source(cell: dict[str, Any], path: str, sources: list[dict[str, Any]]) -> None:
    params = _dict_or_empty(cell.get("params"))
    source: dict[str, Any] = {"path": path, "type": cell.get("type")}
    for key in ("viewId", "contentTypeId", "reportId", "openId", "entity", "dataSource", "source"):
        if key in params:
            source[key] = params.get(key)
    if len(source) > 2:
        sources.append(source)


def _collect_role_keys(value: Any, role_keys: list[dict[str, Any]], path: str = "form") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_str = str(key)
            lower = key_str.lower()
            child_path = f"{path}.{key_str}"
            if any(token in lower for token in ("role", "roles", "permission", "access", "candidate")):
                role_keys.append({"path": child_path, "key": key_str, "value_type": type(child).__name__})
            _collect_role_keys(child, role_keys, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _collect_role_keys(child, role_keys, f"{path}[{index}]")


def _collect_titles(value: Any, page_titles: list[str], headers: list[str], path: str = "form") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lower = str(key).lower()
            if child and lower in {"pagetitle", "page_title"}:
                page_titles.append(str(child))
            if child and lower in {"title", "header", "label", "caption"}:
                headers.append(str(child))
            _collect_titles(child, page_titles, headers, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _collect_titles(child, page_titles, headers, f"{path}[{index}]")


def _count_action_containers(value: Any) -> int:
    count = 0
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"formActionContainers", "cellActionContainers", "valueActionContainers"} and isinstance(child, list):
                count += len(child)
            count += _count_action_containers(child)
    elif isinstance(value, list):
        count += sum(_count_action_containers(child) for child in value)
    return count


def _count_actions(value: Any) -> int:
    count = 0
    if isinstance(value, dict):
        actions = value.get("actions")
        if isinstance(actions, list):
            count += len(actions)
        for child in value.values():
            count += _count_actions(child)
    elif isinstance(value, list):
        count += sum(_count_actions(child) for child in value)
    return count


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze Alterios form JSON for UX/layout/action guardrails.")
    parser.add_argument("json_path", help="Path to a form JSON file.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    parser.add_argument(
        "--strict",
        "--contract",
        dest="strict",
        action="store_true",
        help="Block confirmed Alterios contract violations in addition to errors.",
    )
    args = parser.parse_args(argv)

    with open(args.json_path, "r", encoding="utf-8") as fh:
        form = json.load(fh)
    result = analyze_form_surface(form, strict=args.strict)
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
