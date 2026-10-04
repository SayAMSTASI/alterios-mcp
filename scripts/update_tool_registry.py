"""Explicitly refresh the reviewed public MCP schema fixture after a tool change."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

# Ensure all tools are registered even if the developer normally uses live.
os.environ["ALTERIOS_MCP_TOOL_PROFILE"] = "full"
from alterios_mcp.server import mcp
from alterios_mcp.tool_profiles import TOOL_PROFILES, allowed_tool_names


def main() -> None:
    tools = asyncio.run(mcp.list_tools())
    names = [tool.name for tool in tools]
    target = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "tool_registry_snapshot.json"
    previous = json.loads(target.read_text(encoding="utf-8"))
    previous.update({"tool_count": len(tools),
                     "tools": {tool.name: tool.inputSchema for tool in sorted(tools, key=lambda t: t.name)},
                     "profiles": {p: sorted(allowed_tool_names(names, p)) for p in TOOL_PROFILES}})
    target.write_text(json.dumps(previous, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"Updated schema fixture for {len(tools)} tools.")


if __name__ == "__main__":
    main()
