from __future__ import annotations

from typing import Any, Callable

from ..scenarios import views_forms as scenarios


TOOL_NAMES = ('alterios_upsert_view', 'alterios_upsert_view_entity', 'alterios_upsert_view_field', 'alterios_upsert_form', 'alterios_create_material_module', 'alterios_patch_form_actions', 'alterios_patch_form_tabs', 'alterios_patch_form_cell_listeners', 'alterios_upsert_form_manual_script_action', 'alterios_analyze_form_surface', 'alterios_validate_form_contract', 'alterios_validate_module_contract')


def tool_functions() -> tuple[Callable[..., Any], ...]:
    return tuple(getattr(scenarios, name) for name in TOOL_NAMES)


def register(mcp: Any) -> tuple[str, ...]:
    for tool in tool_functions():
        mcp.tool()(tool)
    return TOOL_NAMES
