from __future__ import annotations

from typing import Any, Callable

from ..scenarios import security as scenarios


TOOL_NAMES = ('alterios_upsert_user', 'alterios_upsert_user_group', 'alterios_upsert_role', 'alterios_delete_user', 'alterios_delete_user_group', 'alterios_delete_role')


def tool_functions() -> tuple[Callable[..., Any], ...]:
    return tuple(getattr(scenarios, name) for name in TOOL_NAMES)


def register(mcp: Any) -> tuple[str, ...]:
    for tool in tool_functions():
        mcp.tool()(tool)
    return TOOL_NAMES
