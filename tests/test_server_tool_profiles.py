from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _server_profile(profile: str) -> dict[str, object]:
    env = dict(os.environ)
    env["ALTERIOS_MCP_TOOL_PROFILE"] = profile
    source_root = str(Path(__file__).parents[1] / "src")
    env["PYTHONPATH"] = source_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    code = (
        "import asyncio,json; "
        "from alterios_mcp.server import mcp,alterios_tool_profile; "
        "tools=asyncio.run(mcp.list_tools()); "
        "print(json.dumps({'names':sorted(tool.name for tool in tools),'summary':alterios_tool_profile()}))"
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


@pytest.mark.parametrize("profile", ["full", "live", "discovery", "admin"])
def test_server_applies_requested_tool_profile(profile: str) -> None:
    result = _server_profile(profile)
    summary = result["summary"]

    assert summary["profile"] == profile
    assert summary["enabled_count"] == len(result["names"])
    assert "alterios_tool_profile" in result["names"]


def test_live_profile_keeps_delivery_tools_and_hides_raw_escape_hatches() -> None:
    names = set(_server_profile("live")["names"])

    assert {
        "alterios_live_task_preflight",
        "alterios_validate_form_contract",
        "alterios_fast_live_write",
        "alterios_fast_live_bulk_manual_script",
        "alterios_fast_live_bulk_process",
        "alterios_create_material_module",
        "alterios_create_report_tab",
        "alterios_create_process_flow",
        "alterios_verify_delivery_evidence",
        "gitea_create_work_item",
        "gitea_add_agent_report",
    } <= names
    assert "alterios_rest_write" not in names
    assert "alterios_call_write_service" not in names
    assert "alterios_upsert_user" not in names
    assert "alterios_fast_live_bulk_delete" not in names


def test_discovery_profile_has_no_mutating_work_tools() -> None:
    names = set(_server_profile("discovery")["names"])

    assert "alterios_project_health" in names
    assert "alterios_get_form" in names
    assert "alterios_validate_form_contract" in names
    assert "gitea_workboard_probe" in names
    assert "alterios_create_material_module" not in names
    assert "gitea_create_work_item" not in names
    assert "alterios_upsert_form" not in names


def test_admin_profile_keeps_typed_security_but_not_generic_write() -> None:
    names = set(_server_profile("admin")["names"])

    assert "alterios_upsert_user" in names
    assert "alterios_delete_role" in names
    assert "alterios_fast_live_bulk_delete" in names
    assert "alterios_rest_write" not in names
    assert "alterios_call_write_service" not in names
