from __future__ import annotations

from typing import Any, Callable

from ..scenarios import icons as scenarios


TOOL_NAMES = ('alterios_file_metadata', 'alterios_list_project_icons', 'alterios_resolve_project_icon', 'alterios_export_project_icons', 'alterios_ensure_project_icons', 'alterios_ensure_project_icon_library')


def tool_functions() -> tuple[Callable[..., Any], ...]:
    return tuple(getattr(scenarios, name) for name in TOOL_NAMES)


def register(mcp: Any) -> tuple[str, ...]:
    for tool in tool_functions():
        mcp.tool()(tool)
    return TOOL_NAMES
