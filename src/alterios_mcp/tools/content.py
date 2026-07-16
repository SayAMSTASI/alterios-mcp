from __future__ import annotations

from typing import Any, Callable

from ..scenarios import content as scenarios


TOOL_NAMES = ('alterios_list_comments', 'alterios_add_comment', 'alterios_upsert_content_type', 'alterios_plan_content_type_publish', 'alterios_clone_shared_content_type', 'alterios_upsert_field', 'alterios_create_content', 'alterios_upsert_group', 'alterios_upsert_help', 'alterios_update_content_fields', 'alterios_bulk_update_selected_content_fields', 'alterios_file_upload_to_field')


def tool_functions() -> tuple[Callable[..., Any], ...]:
    return tuple(getattr(scenarios, name) for name in TOOL_NAMES)


def register(mcp: Any) -> tuple[str, ...]:
    for tool in tool_functions():
        mcp.tool()(tool)
    return TOOL_NAMES
