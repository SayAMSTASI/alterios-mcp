from __future__ import annotations

from typing import Any, Callable

from ..scenarios import live as scenarios


TOOL_NAMES = ('alterios_fast_live_write', 'alterios_fast_live_bulk_manual_script', 'alterios_fast_live_bulk_process', 'alterios_fast_live_bulk_delete')


def tool_functions() -> tuple[Callable[..., Any], ...]:
    return tuple(getattr(scenarios, name) for name in TOOL_NAMES)


def register(mcp: Any) -> tuple[str, ...]:
    for tool in tool_functions():
        mcp.tool()(tool)
    return TOOL_NAMES
