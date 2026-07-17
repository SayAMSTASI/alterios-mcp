"""Pure Alterios module UX-contract validation.

The validator intentionally has no client or FastMCP dependency. Live wrappers
must load only the exact resources requested by the caller and pass them here.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any
from xml.etree import ElementTree

from ..client import looks_like_uuid
from ..form_surface import analyze_form_surface
from ..ux_contract import BLOCKING_MODULE_ISSUE_CODES, UX_CONTRACT_VERSION


REQUIRED_FORM_ROLES = ("add", "edit", "view", "list")
ICON_SOURCE_SIZE = 16
ICON_RENDER_SIZE = 20
ICON_COLOR = "#4B77D1"

ACTION_ICON_SEMANTICS = {
    "add": {"add", "add_2"},
    "bulk": {"checklist", "list_alt_add"},
    "close": {"keyboard_return"},
    "delete": {"delete"},
    "edit": {"edit", "edit_document"},
    "menu": {"menu", "more_vert"},
    "print": {"print"},
    "save": {"save"},
    "script": {"forms_apps_script"},
    "view": {"preview", "visibility"},
}


def validate_module_contract(
    module: dict[str, Any],
    *,
    strict: bool = True,
    require_bulk_interface: bool = False,
    icon_payloads: dict[str, bytes | str] | None = None,
) -> dict[str, Any]:
    """Validate a complete material module from already loaded payloads."""
    if not isinstance(module, dict):
        raise ValueError("module must be a JSON object.")

    issues: list[dict[str, Any]] = []
    content_type = _mapping(module.get("content_type"))
    fields = _object_list(module.get("fields"))
    view = _mapping(module.get("view"))
    view_entities = _object_list(module.get("view_entities") or view.get("entities"))
    view_fields = _object_list(module.get("view_fields") or view.get("fields"))
    forms = _mapping(module.get("forms"))
    reports = _object_list(module.get("reports"))

    _validate_content_type(content_type, fields, issues)
    _validate_view(view, view_entities, view_fields, issues)
    form_results = _validate_forms(forms, issues)
    _validate_view_edit_action_parity(forms, issues)
    _validate_bulk(forms, issues, required=require_bulk_interface)
    _validate_reports(reports, view_fields, issues)
    icon_inventory = _validate_icons(module, forms, issues, icon_payloads=icon_payloads or {})

    normalized_issues = []
    for issue in issues:
        item = dict(issue)
        if strict and item["code"] in BLOCKING_MODULE_ISSUE_CODES:
            item["severity"] = "error"
            item["contract_version"] = UX_CONTRACT_VERSION
        normalized_issues.append(item)

    counts = Counter(item["code"] for item in normalized_issues)
    blocking = [item for item in normalized_issues if item["severity"] == "error"]
    blocking_counts = Counter(item["code"] for item in blocking)
    return {
        "ok": not blocking,
        "contract_version": UX_CONTRACT_VERSION,
        "validation_profile": "module_contract" if strict else "module_advisory",
        "blocking_issue_count": len(blocking),
        "blocking_issues_by_code": dict(sorted(blocking_counts.items())),
        "issue_count": len(normalized_issues),
        "issues_by_code": dict(sorted(counts.items())),
        "issues": normalized_issues,
        "forms": form_results,
        "inventory": {
            "field_count": len(fields),
            "view_entity_count": len(view_entities),
            "view_field_count": len(view_fields),
            "form_roles": sorted(forms),
            "report_count": len(reports),
            "icons": icon_inventory,
        },
    }


def assert_module_contract(result: dict[str, Any]) -> None:
    errors = [issue for issue in result.get("issues", []) if issue.get("severity") == "error"]
    if not errors:
        return
    summary = ", ".join(f"{item.get('code')} at {item.get('path')}" for item in errors[:10])
    raise ValueError(f"Alterios module UX contract {UX_CONTRACT_VERSION} failed: {summary}")


def is_meaningful_description(value: Any) -> bool:
    """Return whether a content-type description contains real user context."""
    return _meaningful_text(value, minimum=10)


def validate_icon_svg(payload: bytes | str) -> dict[str, Any]:
    """Validate the physical SVG contract: 20px canvas and #4B77D1 fill."""
    text = payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)
    try:
        root = ElementTree.fromstring(text)
    except (ElementTree.ParseError, UnicodeDecodeError) as exc:
        return {"ok": False, "parse_error": str(exc), "width": None, "height": None, "colors": []}
    width = _css_pixel_value(root.attrib.get("width"))
    height = _css_pixel_value(root.attrib.get("height"))
    colors = {
        str(node.attrib.get("fill") or "").upper()
        for node in root.iter()
        if str(node.attrib.get("fill") or "").strip() and str(node.attrib.get("fill")).lower() != "none"
    }
    if not colors and root.attrib.get("style"):
        match = re.search(r"(?:^|;)\s*fill\s*:\s*([^;]+)", root.attrib["style"], flags=re.IGNORECASE)
        if match:
            colors.add(match.group(1).strip().upper())
    expected_color = ICON_COLOR.upper()
    return {
        "ok": width == ICON_RENDER_SIZE and height == ICON_RENDER_SIZE and colors == {expected_color},
        "width": width,
        "height": height,
        "colors": sorted(colors),
        "expected_width": ICON_RENDER_SIZE,
        "expected_height": ICON_RENDER_SIZE,
        "expected_color": ICON_COLOR,
    }


def _validate_content_type(content_type: dict[str, Any], fields: list[dict[str, Any]], issues: list[dict[str, Any]]) -> None:
    if not _meaningful_text(content_type.get("description"), minimum=10):
        _issue(issues, "content_type_description_missing", "Content type must have a meaningful description.", "content_type.description")
    for index, field in enumerate(fields):
        tooltip = field.get("tooltip") or field.get("help")
        if not _meaningful_text(tooltip, minimum=3):
            _issue(
                issues,
                "field_tooltip_missing",
                "Every material field must have a user-facing tooltip or help value.",
                f"fields[{index}].tooltip",
                {"field": field.get("mname") or field.get("name")},
            )


def _validate_view(view: dict[str, Any], entities: list[dict[str, Any]], fields: list[dict[str, Any]], issues: list[dict[str, Any]]) -> None:
    settings = _mapping(view.get("settings"))
    if settings.get("engineVersion") != "v2":
        _issue(issues, "view_engine_not_v2", "Views must use Alterios experimental/v2 mode.", "view.settings.engineVersion")
    if not entities:
        _issue(issues, "view_entity_missing", "The module view must contain a source entity.", "view_entities")
    if not fields:
        _issue(issues, "view_field_missing", "The module view must expose fields.", "view_fields")
    for index, entity in enumerate(entities):
        config = _mapping(entity.get("config"))
        is_main = bool(config.get("main") or entity.get("main"))
        joins = entity.get("joins")
        if index > 0 and not is_main and (not isinstance(joins, list) or not joins):
            _issue(issues, "relation_join_missing", "Every non-main related view entity must declare joins.", f"view_entities[{index}].joins")
        if isinstance(joins, list):
            for join_index, join in enumerate(joins):
                if not isinstance(join, dict) or not _join_has_both_sides(join):
                    _issue(issues, "relation_join_invalid", "A join must identify both linked fields/entities.", f"view_entities[{index}].joins[{join_index}]")


def _validate_forms(forms: dict[str, Any], issues: list[dict[str, Any]]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for role in REQUIRED_FORM_ROLES:
        form = forms.get(role)
        if not isinstance(form, dict):
            _issue(issues, "module_form_role_missing", f"Module form role {role!r} is missing.", f"forms.{role}")
            continue
        normalized = _normalized_form(form)
        result = analyze_form_surface(normalized, strict=True)
        results[role] = result
        for form_issue in result["issues"]:
            if form_issue.get("severity") != "error":
                continue
            copied = dict(form_issue)
            copied["path"] = f"forms.{role}.{form_issue.get('path')}"
            copied["form_role"] = role
            issues.append(copied)
    return results


def _validate_view_edit_action_parity(forms: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    view_form = forms.get("view")
    edit_form = forms.get("edit")
    if not isinstance(view_form, dict) or not isinstance(edit_form, dict):
        return
    view_actions = _element_action_signatures(_normalized_form(view_form), omit_edit_transition=True)
    edit_actions = _element_action_signatures(_normalized_form(edit_form), omit_edit_transition=False)
    if view_actions != edit_actions:
        _issue(
            issues,
            "view_edit_element_actions_mismatch",
            "View and edit forms must expose the same element actions; only the view-to-edit transition may differ.",
            "forms.view/forms.edit.cellActionContainers",
            {"view": list(view_actions), "edit": list(edit_actions)},
        )


def _validate_bulk(forms: dict[str, Any], issues: list[dict[str, Any]], *, required: bool) -> None:
    if not required:
        return
    if any(_action_category(container) == "bulk" for form in forms.values() if isinstance(form, dict) for container in _action_containers(form)):
        return
    _issue(issues, "bulk_interface_missing", "The requested module has no dedicated bulk-selection/edit action.", "forms")


def _validate_reports(reports: list[dict[str, Any]], view_fields: list[dict[str, Any]], issues: list[dict[str, Any]]) -> None:
    for index, report in enumerate(reports):
        template = report.get("template") or report.get("reportTemplate") or report.get("value")
        source_text = template if isinstance(template, str) else str(template or "")
        has_project_database = "project database" in source_text.casefold() or "projectdatabase" in source_text.casefold()
        has_source = has_project_database and any(token in source_text for token in ("view", "View", "DataSource", "Databases"))
        if not has_source:
            _issue(issues, "report_source_missing", "Report must contain a Project Database source binding.", f"reports[{index}].template")
        if has_source and not view_fields:
            _issue(issues, "report_source_fields_missing", "Report source view has no fields available for the report.", f"reports[{index}].source")


def _validate_icons(
    module: dict[str, Any],
    forms: dict[str, Any],
    issues: list[dict[str, Any]],
    *,
    icon_payloads: dict[str, bytes | str],
) -> dict[str, Any]:
    registry = _mapping(module.get("icon_registry"))
    entries = _mapping(registry.get("icons") if "icons" in registry else registry)
    by_file_id = {str(entry.get("file_id")): entry for entry in entries.values() if isinstance(entry, dict) and entry.get("file_id")}
    usages = _icon_usages(forms)
    group = _mapping(module.get("group"))
    group_icon_id = str(group.get("iconId") or group.get("icon_id") or "").strip()
    if group_icon_id:
        usages.append(
            {
                "icon_id": group_icon_id,
                "path": "group.iconId",
                "expected_semantics": set(),
            }
        )
    verified_ids: set[str] = set()
    for usage in usages:
        icon_id = usage["icon_id"]
        path = usage["path"]
        expected = usage.get("expected_semantics") or set()
        entry = by_file_id.get(icon_id)
        if not looks_like_uuid(icon_id) or not isinstance(entry, dict):
            _issue(issues, "icon_registry_entry_missing", "Every action iconId must resolve to the target project's verified icon registry.", path, {"icon_id": icon_id})
            continue
        semantic = str(entry.get("semantic") or "").strip().lower()
        google_name = str(entry.get("google_name") or semantic).strip().lower()
        if expected and semantic not in expected and google_name not in expected:
            _issue(issues, "icon_semantic_mismatch", "The registered icon does not match the action semantics.", path, {"semantic": semantic, "google_name": google_name, "expected": sorted(expected)})
        source_size = _css_pixel_value(entry.get("size"))
        if entry.get("size") is not None and source_size != ICON_SOURCE_SIZE:
            _issue(issues, "icon_source_size_mismatch", "Google icon source size must be 16.", path, {"actual": entry.get("size")})
        filename = str(entry.get("filename") or "").casefold()
        if entry.get("source") == "repo_icon_library" and filename and "_16dp" not in filename:
            _issue(issues, "icon_source_size_mismatch", "Repository icon filename must identify the Google Size=16 source.", path, {"filename": entry.get("filename")})
        if entry.get("color") and str(entry["color"]).upper() != ICON_COLOR.upper():
            _issue(issues, "icon_file_color_mismatch", "Icon color must be #4B77D1.", path, {"actual": entry.get("color")})
        payload = icon_payloads.get(icon_id)
        if payload is None:
            render_size = entry.get("render_size")
            verified_color = str(entry.get("color") or "").upper()
            if render_size != ICON_RENDER_SIZE or verified_color != ICON_COLOR.upper() or not entry.get("file_contract_verified"):
                _issue(
                    issues,
                    "icon_file_contract_unverified",
                    "Icon file size/color is not verified; run deep icon verification once or re-upload from the repository library.",
                    path,
                    {"render_size": render_size, "color": entry.get("color")},
                )
            continue
        verified_ids.add(icon_id)
        svg = validate_icon_svg(payload)
        if svg["width"] != ICON_RENDER_SIZE or svg["height"] != ICON_RENDER_SIZE:
            _issue(issues, "icon_file_size_mismatch", "SVG width and height must be 20px.", path, svg)
        if svg["colors"] != [ICON_COLOR.upper()]:
            _issue(issues, "icon_file_color_mismatch", "SVG fill must be #4B77D1.", path, svg)
    return {
        "usage_count": len(usages),
        "unique_icon_count": len({item["icon_id"] for item in usages}),
        "registry_entry_count": len(entries),
        "file_verified_count": len(verified_ids),
        "file_verification_mode": "provided_payloads" if icon_payloads else "registry_metadata_only",
    }


def _icon_usages(forms: dict[str, Any]) -> list[dict[str, Any]]:
    usages: list[dict[str, Any]] = []
    for role, form in forms.items():
        if not isinstance(form, dict):
            continue
        for container, path in _walk_action_containers(_normalized_form(form)):
            icon_id = str(container.get("iconId") or "").strip()
            if not icon_id:
                continue
            category = _action_category(container)
            usages.append({"icon_id": icon_id, "path": f"forms.{role}.{path}.iconId", "expected_semantics": ACTION_ICON_SEMANTICS.get(category, set())})
    return usages


def _element_action_signatures(form: dict[str, Any], *, omit_edit_transition: bool) -> tuple[str, ...]:
    signatures: list[str] = []
    for container, path in _walk_action_containers(form):
        if ".cellActionContainers" not in path and not path.startswith("cellActionContainers"):
            continue
        category = _action_category(container)
        if omit_edit_transition and category == "edit" and _contains_action_type(container, "forms"):
            continue
        signatures.append(_action_signature(container, category))
    return tuple(sorted(signatures))


def _action_signature(container: dict[str, Any], category: str) -> str:
    action_types = sorted(str(value.get("type") or "") for value in _walk_dicts(container.get("actions")) if value.get("type"))
    script_ids = sorted(str(value.get("_id") or value.get("scriptId") or "") for value in _walk_dicts(container.get("actions")) if str(value.get("type") or "").casefold() in {"manual_script", "script"})
    return "|".join([category or "other", ",".join(action_types), ",".join(script_ids)])


def _action_category(container: dict[str, Any]) -> str:
    labels = " ".join(str(container.get(key) or "") for key in ("title", "tooltip", "name")).casefold()
    if any(token in labels for token in ("массов", "bulk", "пакетн")):
        return "bulk"
    if any(token in labels for token in ("закрыть", "close")):
        return "close"
    if any(token in labels for token in ("сохран", "save")):
        return "save"
    if any(token in labels for token in ("редакт", "edit")):
        return "edit"
    if any(token in labels for token in ("просмотр", "view", "preview")):
        return "view"
    if any(token in labels for token in ("удал", "delete")) or _contains_action_type(container, "delete_contents"):
        return "delete"
    if any(token in labels for token in ("добав", "add")):
        return "add"
    if any(token in labels for token in ("печать", "print")):
        return "print"
    if any(token in labels for token in ("скрипт", "script", "обработ")) or _contains_action_type(container, "manual_script"):
        return "script"
    if str(container.get("type") or "").casefold() == "menu":
        return "menu"
    return ""


def _action_containers(value: Any) -> list[dict[str, Any]]:
    return [container for container, _ in _walk_action_containers(value)]


def _walk_action_containers(value: Any, path: str = "") -> list[tuple[dict[str, Any], str]]:
    found: list[tuple[dict[str, Any], str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if key in {"formActionContainers", "cellActionContainers", "valueActionContainers", "containers"} and isinstance(child, list):
                for index, container in enumerate(child):
                    if isinstance(container, dict):
                        container_path = f"{child_path}[{index}]"
                        found.append((container, container_path))
                        found.extend(_walk_action_containers(container, container_path))
            elif key not in {"actions", "containers"}:
                found.extend(_walk_action_containers(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_walk_action_containers(child, f"{path}[{index}]"))
    return found


def _walk_dicts(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        found.append(value)
        for child in value.values():
            found.extend(_walk_dicts(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_dicts(child))
    return found


def _contains_action_type(container: dict[str, Any], action_type: str) -> bool:
    expected = action_type.casefold()
    return any(str(item.get("type") or "").casefold() == expected for item in _walk_dicts(container.get("actions")))


def _normalized_form(form: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(form)
    if "pageTitle" not in normalized and "page_title" in normalized:
        normalized["pageTitle"] = normalized["page_title"]
    return normalized


def _join_has_both_sides(join: dict[str, Any]) -> bool:
    text_values = [str(value).strip() for value in join.values() if isinstance(value, (str, int)) and str(value).strip()]
    if len(text_values) >= 2:
        return True
    keys = {str(key).casefold() for key, value in join.items() if value not in (None, "", [], {})}
    left = any(token in key for key in keys for token in ("left", "source", "from", "parent"))
    right = any(token in key for key in keys for token in ("right", "target", "to", "child"))
    return left and right


def _css_pixel_value(value: Any) -> int | None:
    match = re.fullmatch(r"\s*(\d+(?:\.0+)?)\s*(?:px)?\s*", str(value or ""), flags=re.IGNORECASE)
    return int(float(match.group(1))) if match else None


def _meaningful_text(value: Any, *, minimum: int) -> bool:
    text = re.sub(r"(?i)codex-managed\s*:?", "", str(value or "")).strip(" .:-")
    return len(text) >= minimum


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _object_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _issue(issues: list[dict[str, Any]], code: str, message: str, path: str, details: dict[str, Any] | None = None) -> None:
    item: dict[str, Any] = {"severity": "warning", "code": code, "message": message, "path": path}
    if details:
        item["details"] = details
    issues.append(item)


__all__ = [
    "ICON_COLOR",
    "ICON_RENDER_SIZE",
    "ICON_SOURCE_SIZE",
    "assert_module_contract",
    "is_meaningful_description",
    "validate_icon_svg",
    "validate_module_contract",
]
