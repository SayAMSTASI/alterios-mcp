from __future__ import annotations

from typing import Any, Callable

from ..scenarios import runtime as scenarios


TOOL_NAMES = ('alterios_config', 'alterios_runtime_info', 'alterios_ux_contract', 'alterios_tool_profile', 'alterios_verify_delivery_evidence', 'alterios_live_task_preflight', 'alterios_list_profiles')


def tool_functions() -> tuple[Callable[..., Any], ...]:
    return tuple(getattr(scenarios, name) for name in TOOL_NAMES)


def register(mcp: Any) -> tuple[str, ...]:
    for tool in tool_functions():
        mcp.tool()(tool)
    return TOOL_NAMES
