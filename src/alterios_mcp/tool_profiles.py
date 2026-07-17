from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from typing import Any, Protocol


TOOL_PROFILE_ENV_VAR = "ALTERIOS_MCP_TOOL_PROFILE"
DEFAULT_TOOL_PROFILE = "full"
TOOL_PROFILES = ("full", "live", "discovery", "admin")
TOOL_PROFILE_INTROSPECTION = "alterios_tool_profile"


RUNTIME_AND_GUARD_TOOL_NAMES = frozenset(
    {
        "alterios_config",
        "alterios_runtime_info",
        "alterios_ux_contract",
        "alterios_live_task_preflight",
        "alterios_list_profiles",
        "alterios_profile_smoke_matrix",
        "alterios_replay_smoke",
        "alterios_project_health",
        "alterios_write_safety_preflight",
        "alterios_verify_delivery_evidence",
    }
)

READ_ONLY_WORK_COORDINATION_TOOL_NAMES = frozenset(
    {
        "gitea_workboard_config",
        "gitea_workboard_probe",
        "gitea_list_work_items",
        "gitea_list_sprint_tasks",
        "local_workboard_config",
        "local_workboard_list_items",
    }
)

WORK_COORDINATION_TOOL_NAMES = frozenset(
    READ_ONLY_WORK_COORDINATION_TOOL_NAMES
    | {
        "gitea_sync_standard_labels",
        "gitea_create_work_item",
        "gitea_create_sprint",
        "gitea_add_agent_report",
        "gitea_sync_board_by_labels",
        "gitea_transition_issue_stage",
        "local_workboard_init",
        "local_workboard_create_item",
        "local_workboard_add_agent_report",
    }
)

LIVE_WORK_COORDINATION_TOOL_NAMES = frozenset(
    {
        "gitea_workboard_config",
        "gitea_workboard_probe",
        "gitea_list_work_items",
        "gitea_list_sprint_tasks",
        "gitea_create_work_item",
        "gitea_add_agent_report",
        "gitea_transition_issue_stage",
        "gitea_sync_board_by_labels",
    }
)

READ_ONLY_DISCOVERY_TOOL_NAMES = frozenset(
    {
        "alterios_list_write_plans",
        "alterios_get_write_plan",
        "alterios_write_journal",
        "alterios_list_projects",
        "alterios_service_catalog",
        "alterios_call_readonly_service",
        "alterios_rest_get",
        "alterios_list_objects",
        "alterios_view_data_simplified",
        "alterios_report_full",
        "alterios_get_view",
        "alterios_get_form",
        "alterios_view_entities",
        "alterios_view_fields_populated",
        "alterios_list_fields",
        "alterios_list_groups",
        "alterios_list_content_types",
        "alterios_list_users",
        "alterios_get_user",
        "alterios_list_user_groups",
        "alterios_get_user_group",
        "alterios_list_roles",
        "alterios_get_role",
        "alterios_file_metadata",
        "alterios_list_project_icons",
        "alterios_resolve_project_icon",
        "alterios_list_comments",
        "alterios_analyze_form_surface",
        "alterios_validate_form_contract",
        "alterios_view_data",
        "alterios_validate_script",
        "alterios_list_process_tasks",
        "alterios_validate_process_result",
        "alterios_validate_report_project_base",
        "alterios_validate_stimulsoft_layout",
        "alterios_validate_printable_render",
        "alterios_diagnose_report_viewer",
        "alterios_discover_readonly",
    }
)

SCENARIO_TOOL_NAMES = frozenset(
    {
        "alterios_fast_live_write",
        "alterios_fast_live_bulk_manual_script",
        "alterios_fast_live_bulk_process",
        "alterios_create_material_module",
        "alterios_create_report_tab",
        "alterios_create_process_flow",
    }
)

DANGEROUS_WORKFLOW_TOOL_NAMES = frozenset(
    {
        "alterios_fast_live_bulk_delete",
    }
)

ADMIN_SECURITY_WRITE_TOOL_NAMES = frozenset(
    {
        "alterios_upsert_user",
        "alterios_upsert_user_group",
        "alterios_upsert_role",
        "alterios_delete_user",
        "alterios_delete_user_group",
        "alterios_delete_role",
    }
)

TYPED_WRITE_TOOL_NAMES = frozenset(
    {
        "alterios_export_project_icons",
        "alterios_ensure_project_icons",
        "alterios_ensure_project_icon_library",
        "alterios_add_comment",
        "alterios_upsert_content_type",
        "alterios_plan_content_type_publish",
        "alterios_clone_shared_content_type",
        "alterios_upsert_field",
        "alterios_create_content",
        "alterios_upsert_group",
        "alterios_upsert_help",
        "alterios_update_content_fields",
        "alterios_bulk_update_selected_content_fields",
        "alterios_file_upload_to_field",
        "alterios_upsert_view",
        "alterios_upsert_view_entity",
        "alterios_upsert_view_field",
        "alterios_upsert_form",
        "alterios_patch_form_actions",
        "alterios_patch_form_tabs",
        "alterios_patch_form_cell_listeners",
        "alterios_upsert_form_manual_script_action",
        "alterios_upsert_script",
        "alterios_upsert_bpmn_diagram",
        "alterios_start_process",
        "alterios_complete_task",
        "alterios_upsert_report",
        "alterios_patch_report_template",
        "alterios_execute_manual_script",
    }
)

RAW_WRITE_ESCAPE_HATCH_TOOL_NAMES = frozenset(
    {
        "alterios_call_write_service",
        "alterios_rest_write",
    }
)

LIVE_READ_HELPER_TOOL_NAMES = frozenset(
    {
        "alterios_list_write_plans",
        "alterios_get_write_plan",
        "alterios_write_journal",
        "alterios_list_projects",
        "alterios_list_objects",
        "alterios_view_data_simplified",
        "alterios_report_full",
        "alterios_get_view",
        "alterios_get_form",
        "alterios_view_entities",
        "alterios_view_fields_populated",
        "alterios_list_fields",
        "alterios_list_groups",
        "alterios_list_content_types",
        "alterios_file_metadata",
        "alterios_list_project_icons",
        "alterios_resolve_project_icon",
        "alterios_list_comments",
        "alterios_analyze_form_surface",
        "alterios_validate_form_contract",
        "alterios_view_data",
        "alterios_validate_script",
        "alterios_list_process_tasks",
        "alterios_validate_process_result",
        "alterios_validate_report_project_base",
        "alterios_validate_stimulsoft_layout",
        "alterios_validate_printable_render",
        "alterios_diagnose_report_viewer",
    }
)

LIVE_WRITE_HELPER_TOOL_NAMES = frozenset(
    {
        "alterios_ensure_project_icons",
        "alterios_ensure_project_icon_library",
        "alterios_add_comment",
        "alterios_upsert_content_type",
        "alterios_plan_content_type_publish",
        "alterios_clone_shared_content_type",
        "alterios_upsert_field",
        "alterios_create_content",
        "alterios_upsert_group",
        "alterios_upsert_help",
        "alterios_update_content_fields",
        "alterios_bulk_update_selected_content_fields",
        "alterios_file_upload_to_field",
        "alterios_upsert_view",
        "alterios_upsert_view_entity",
        "alterios_upsert_view_field",
        "alterios_upsert_form",
        "alterios_patch_form_actions",
        "alterios_patch_form_tabs",
        "alterios_patch_form_cell_listeners",
        "alterios_upsert_form_manual_script_action",
        "alterios_upsert_script",
        "alterios_upsert_bpmn_diagram",
        "alterios_start_process",
        "alterios_complete_task",
        "alterios_upsert_report",
        "alterios_patch_report_template",
        "alterios_execute_manual_script",
    }
)

LIVE_TOOL_NAMES = frozenset(
    RUNTIME_AND_GUARD_TOOL_NAMES
    | SCENARIO_TOOL_NAMES
    | LIVE_READ_HELPER_TOOL_NAMES
    | LIVE_WRITE_HELPER_TOOL_NAMES
    | LIVE_WORK_COORDINATION_TOOL_NAMES
)
DISCOVERY_TOOL_NAMES = frozenset(
    RUNTIME_AND_GUARD_TOOL_NAMES | READ_ONLY_DISCOVERY_TOOL_NAMES | READ_ONLY_WORK_COORDINATION_TOOL_NAMES
)
ADMIN_TOOL_NAMES = frozenset(
    DISCOVERY_TOOL_NAMES
    | SCENARIO_TOOL_NAMES
    | DANGEROUS_WORKFLOW_TOOL_NAMES
    | TYPED_WRITE_TOOL_NAMES
    | ADMIN_SECURITY_WRITE_TOOL_NAMES
    | WORK_COORDINATION_TOOL_NAMES
)


class ToolRemover(Protocol):
    def remove_tool(self, name: str) -> None: ...


def normalize_tool_profile(
    profile: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Return a validated lowercase profile, defaulting to ``full``."""
    env = os.environ if environ is None else environ
    raw_profile = profile if profile is not None else env.get(TOOL_PROFILE_ENV_VAR, DEFAULT_TOOL_PROFILE)
    normalized = str(raw_profile or DEFAULT_TOOL_PROFILE).strip().lower()
    if normalized not in TOOL_PROFILES:
        allowed = ", ".join(TOOL_PROFILES)
        raise ValueError(f"Unknown Alterios MCP tool profile {raw_profile!r}; expected one of: {allowed}.")
    return normalized


def classify_tool(tool_name: str) -> str:
    """Classify a tool name without inspecting a FastMCP instance."""
    name = str(tool_name).strip()
    if name == TOOL_PROFILE_INTROSPECTION:
        return "introspection"
    if name in RAW_WRITE_ESCAPE_HATCH_TOOL_NAMES:
        return "raw_write_escape_hatch"
    if name in ADMIN_SECURITY_WRITE_TOOL_NAMES:
        return "admin_security_write"
    if name in DANGEROUS_WORKFLOW_TOOL_NAMES:
        return "dangerous_workflow"
    if name in SCENARIO_TOOL_NAMES:
        return "scenario"
    if name in TYPED_WRITE_TOOL_NAMES:
        return "typed_write"
    if name in RUNTIME_AND_GUARD_TOOL_NAMES:
        return "runtime_guard"
    if name in READ_ONLY_DISCOVERY_TOOL_NAMES:
        return "read_only_discovery"
    if name in WORK_COORDINATION_TOOL_NAMES:
        return "work_coordination"
    return "unknown"


def allowed_tool_names(
    tool_names: Iterable[str],
    profile: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Return the sorted tool names enabled by a profile."""
    normalized_profile = normalize_tool_profile(profile, environ=environ)
    names = _normalized_tool_names(tool_names)
    if normalized_profile == "full":
        return names

    profile_names = {
        "live": LIVE_TOOL_NAMES,
        "discovery": DISCOVERY_TOOL_NAMES,
        "admin": ADMIN_TOOL_NAMES,
    }[normalized_profile]
    return tuple(
        name
        for name in names
        if name == TOOL_PROFILE_INTROSPECTION or name in profile_names
    )


def build_tool_profile_summary(
    tool_names: Iterable[str],
    profile: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build a deterministic JSON-serializable profile decision summary."""
    names = _normalized_tool_names(tool_names)
    normalized_profile = normalize_tool_profile(profile, environ=environ)
    enabled = allowed_tool_names(names, normalized_profile, environ=environ)
    enabled_set = set(enabled)
    removed = tuple(name for name in names if name not in enabled_set)

    classifications: dict[str, list[str]] = {}
    for name in names:
        classifications.setdefault(classify_tool(name), []).append(name)

    raw_enabled = sorted(enabled_set & RAW_WRITE_ESCAPE_HATCH_TOOL_NAMES)
    raw_removed = sorted(set(removed) & RAW_WRITE_ESCAPE_HATCH_TOOL_NAMES)
    return {
        "profile": normalized_profile,
        "environment_variable": TOOL_PROFILE_ENV_VAR,
        "default_profile": DEFAULT_TOOL_PROFILE,
        "available_profiles": list(TOOL_PROFILES),
        "input_count": len(names),
        "enabled_count": len(enabled),
        "removed_count": len(removed),
        "enabled_tool_names": list(enabled),
        "removed_tool_names": list(removed),
        "classifications": classifications,
        "raw_write_escape_hatches": {
            "enabled": raw_enabled,
            "removed": raw_removed,
        },
        "introspection_registered": TOOL_PROFILE_INTROSPECTION in names,
        "introspection_enabled": TOOL_PROFILE_INTROSPECTION in enabled_set,
    }


def apply_tool_profile(
    mcp: ToolRemover,
    tool_names: Iterable[str],
    profile: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Remove disabled tools from FastMCP through its public ``remove_tool`` API."""
    summary = build_tool_profile_summary(tool_names, profile, environ=environ)
    for name in summary["removed_tool_names"]:
        mcp.remove_tool(name)
    return {**summary, "applied": True}


def _normalized_tool_names(tool_names: Iterable[str]) -> tuple[str, ...]:
    normalized: set[str] = set()
    for tool_name in tool_names:
        if not isinstance(tool_name, str):
            raise TypeError("Tool names must be strings.")
        name = tool_name.strip()
        if name:
            normalized.add(name)
    return tuple(sorted(normalized))
