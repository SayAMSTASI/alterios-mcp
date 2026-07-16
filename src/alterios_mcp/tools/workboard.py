from __future__ import annotations

from typing import Any, Callable

from ..scenarios import workboard as scenarios


TOOL_NAMES = ('gitea_workboard_config', 'gitea_workboard_probe', 'local_workboard_config', 'local_workboard_init', 'local_workboard_create_item', 'local_workboard_list_items', 'local_workboard_add_agent_report', 'gitea_list_work_items', 'gitea_sync_standard_labels', 'gitea_create_work_item', 'gitea_create_sprint', 'gitea_list_sprint_tasks', 'gitea_add_agent_report', 'gitea_sync_board_by_labels', 'gitea_transition_issue_stage')


def tool_functions() -> tuple[Callable[..., Any], ...]:
    return tuple(getattr(scenarios, name) for name in TOOL_NAMES)


def register(mcp: Any) -> tuple[str, ...]:
    for tool in tool_functions():
        mcp.tool()(tool)
    return TOOL_NAMES
