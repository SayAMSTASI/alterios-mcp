from __future__ import annotations

from typing import Any, Callable

from ..scenarios import discovery as scenarios


TOOL_NAMES = ('alterios_list_projects', 'alterios_service_catalog', 'alterios_call_readonly_service', 'alterios_rest_get', 'alterios_list_objects', 'alterios_view_data_simplified', 'alterios_report_full', 'alterios_get_view', 'alterios_get_form', 'alterios_view_entities', 'alterios_view_fields_populated', 'alterios_list_fields', 'alterios_list_groups', 'alterios_list_content_types', 'alterios_list_users', 'alterios_get_user', 'alterios_list_user_groups', 'alterios_get_user_group', 'alterios_list_roles', 'alterios_get_role')


def tool_functions() -> tuple[Callable[..., Any], ...]:
    return tuple(getattr(scenarios, name) for name in TOOL_NAMES)


def register(mcp: Any) -> tuple[str, ...]:
    for tool in tool_functions():
        mcp.tool()(tool)
    return TOOL_NAMES
