from __future__ import annotations

from typing import Any, Callable

from ..scenarios import write_audit as scenarios


TOOL_NAMES = ('alterios_list_write_plans', 'alterios_get_write_plan', 'alterios_write_journal')


def tool_functions() -> tuple[Callable[..., Any], ...]:
    return tuple(getattr(scenarios, name) for name in TOOL_NAMES)


def register(mcp: Any) -> tuple[str, ...]:
    for tool in tool_functions():
        mcp.tool()(tool)
    return TOOL_NAMES
