from __future__ import annotations

from typing import Any, Callable
from ..scenarios import read_workflows as scenarios

TOOL_NAMES = (
    "alterios_export_dataset", "alterios_read_all_objects", "alterios_find_usages",
    "alterios_relation_graph", "alterios_diagnose_view", "alterios_audit_log",
    "alterios_list_notifications",
    "alterios_list_files", "alterios_download_files",
)


def tool_functions() -> tuple[Callable[..., Any], ...]:
    return tuple(getattr(scenarios, name) for name in TOOL_NAMES)


def register(mcp: Any) -> tuple[str, ...]:
    for tool in tool_functions():
        mcp.tool()(tool)
    return TOOL_NAMES
