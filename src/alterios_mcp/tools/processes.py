from __future__ import annotations

from typing import Any, Callable

from ..scenarios import processes as scenarios


TOOL_NAMES = ('alterios_view_data', 'alterios_upsert_script', 'alterios_validate_script', 'alterios_upsert_bpmn_diagram', 'alterios_list_process_tasks', 'alterios_start_process', 'alterios_complete_task', 'alterios_validate_process_result', 'alterios_create_process_flow')


def tool_functions() -> tuple[Callable[..., Any], ...]:
    return tuple(getattr(scenarios, name) for name in TOOL_NAMES)


def register(mcp: Any) -> tuple[str, ...]:
    for tool in tool_functions():
        mcp.tool()(tool)
    return TOOL_NAMES
