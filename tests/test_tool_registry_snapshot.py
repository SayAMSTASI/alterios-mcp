from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


SNAPSHOT_PATH = Path(__file__).parent / "fixtures" / "tool_registry_snapshot.json"
PROFILES = ("full", "live", "discovery", "admin")


def _profile_registry(profile: str) -> list[dict[str, object]]:
    env = dict(os.environ)
    env["ALTERIOS_MCP_TOOL_PROFILE"] = profile
    code = (
        "import asyncio,json; "
        "from alterios_mcp.server import mcp; "
        "tools=asyncio.run(mcp.list_tools()); "
        "print(json.dumps([{'name':t.name,'inputSchema':t.inputSchema} for t in tools],sort_keys=True))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=30,
        check=True,
    )
    return json.loads(completed.stdout)


def test_tool_names_argument_schemas_and_profiles_match_snapshot() -> None:
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    registries = {profile: _profile_registry(profile) for profile in PROFILES}
    full_tools = registries["full"]

    assert snapshot["tool_count"] == len(full_tools)
    assert snapshot["tools"] == {
        item["name"]: item["inputSchema"]
        for item in sorted(full_tools, key=lambda item: item["name"])
    }
    assert snapshot["profiles"] == {
        profile: sorted(item["name"] for item in registries[profile])
        for profile in PROFILES
    }
