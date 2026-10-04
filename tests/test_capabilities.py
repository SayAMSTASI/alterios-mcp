from pathlib import Path

from alterios_mcp.capabilities import render_capabilities
from alterios_mcp.tool_profiles import allowed_tool_names, classify_tool
from alterios_mcp.tools.read_workflows import TOOL_NAMES


def test_catalog_is_generated_from_current_registry():
    path = Path(__file__).parents[1] / "docs" / "capabilities.md"
    assert path.read_text(encoding="utf-8") == render_capabilities()


def test_read_workflows_do_not_open_write_escape_hatches():
    for profile in ("live", "discovery", "admin"):
        enabled = set(allowed_tool_names([*TOOL_NAMES, "alterios_rest_write", "alterios_call_write_service"], profile))
        assert enabled == set(TOOL_NAMES)
    assert all(classify_tool(name) == "read_only_discovery" for name in TOOL_NAMES)
