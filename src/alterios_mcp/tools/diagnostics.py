from __future__ import annotations

from typing import Any, Callable

from ..scenarios import diagnostics as scenarios


TOOL_NAMES = ('alterios_discover_readonly', 'alterios_profile_smoke_matrix', 'alterios_replay_smoke', 'alterios_project_health', 'alterios_write_safety_preflight', 'alterios_call_write_service', 'alterios_execute_manual_script', 'alterios_rest_write')


def tool_functions() -> tuple[Callable[..., Any], ...]:
    return tuple(getattr(scenarios, name) for name in TOOL_NAMES)


def register(mcp: Any) -> tuple[str, ...]:
    for tool in tool_functions():
        mcp.tool()(tool)
    return TOOL_NAMES
