from __future__ import annotations

from typing import Any, Callable

from ..scenarios import reports as scenarios


TOOL_NAMES = ('alterios_upsert_report', 'alterios_patch_report_template', 'alterios_validate_report_project_base', 'alterios_validate_stimulsoft_layout', 'alterios_validate_printable_render', 'alterios_diagnose_report_viewer', 'alterios_create_report_tab')


def tool_functions() -> tuple[Callable[..., Any], ...]:
    return tuple(getattr(scenarios, name) for name in TOOL_NAMES)


def register(mcp: Any) -> tuple[str, ...]:
    for tool in tool_functions():
        mcp.tool()(tool)
    return TOOL_NAMES
