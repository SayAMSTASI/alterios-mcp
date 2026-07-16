from __future__ import annotations

import pytest

from alterios_mcp.tool_profiles import (
    DEFAULT_TOOL_PROFILE,
    TOOL_PROFILE_ENV_VAR,
    TOOL_PROFILE_INTROSPECTION,
    allowed_tool_names,
    apply_tool_profile,
    build_tool_profile_summary,
    classify_tool,
    normalize_tool_profile,
)


SAMPLE_TOOLS = [
    "alterios_rest_write",
    "alterios_tool_profile",
    "alterios_list_content_types",
    "alterios_live_task_preflight",
    "alterios_validate_form_contract",
    "alterios_fast_live_write",
    "alterios_create_material_module",
    "alterios_upsert_content_type",
    "alterios_upsert_user",
    "alterios_delete_role",
    "alterios_call_write_service",
    "gitea_create_work_item",
    "future_unclassified_tool",
]


class FakeMCP:
    def __init__(self, tool_names: list[str]) -> None:
        self.tool_names = set(tool_names)
        self.removed: list[str] = []

    def remove_tool(self, name: str) -> None:
        self.removed.append(name)
        self.tool_names.remove(name)


def test_normalize_tool_profile_defaults_to_full_for_compatibility() -> None:
    assert normalize_tool_profile(environ={}) == DEFAULT_TOOL_PROFILE == "full"
    assert normalize_tool_profile(environ={TOOL_PROFILE_ENV_VAR: ""}) == "full"
    assert normalize_tool_profile(environ={TOOL_PROFILE_ENV_VAR: " LIVE "}) == "live"
    assert normalize_tool_profile(" Admin ", environ={TOOL_PROFILE_ENV_VAR: "discovery"}) == "admin"


def test_normalize_tool_profile_rejects_unknown_profile() -> None:
    with pytest.raises(ValueError, match="Unknown Alterios MCP tool profile"):
        normalize_tool_profile("operator")


def test_classify_tool_covers_profile_boundaries() -> None:
    assert classify_tool(TOOL_PROFILE_INTROSPECTION) == "introspection"
    assert classify_tool("alterios_list_content_types") == "read_only_discovery"
    assert classify_tool("alterios_live_task_preflight") == "runtime_guard"
    assert classify_tool("alterios_validate_form_contract") == "read_only_discovery"
    assert classify_tool("alterios_fast_live_write") == "scenario"
    assert classify_tool("alterios_create_material_module") == "scenario"
    assert classify_tool("alterios_upsert_content_type") == "typed_write"
    assert classify_tool("alterios_delete_user") == "admin_security_write"
    assert classify_tool("alterios_rest_write") == "raw_write_escape_hatch"
    assert classify_tool("gitea_create_work_item") == "work_coordination"
    assert classify_tool("future_unclassified_tool") == "unknown"


def test_full_profile_preserves_all_input_tools() -> None:
    assert allowed_tool_names(SAMPLE_TOOLS, "full") == tuple(sorted(SAMPLE_TOOLS))


def test_discovery_profile_is_read_only_and_preserves_introspection() -> None:
    enabled = set(allowed_tool_names(SAMPLE_TOOLS, "discovery"))

    assert enabled == {
        TOOL_PROFILE_INTROSPECTION,
        "alterios_list_content_types",
        "alterios_live_task_preflight",
        "alterios_validate_form_contract",
    }


def test_live_profile_keeps_scenarios_and_typed_helpers() -> None:
    enabled = set(allowed_tool_names(SAMPLE_TOOLS, "live"))

    assert {
        TOOL_PROFILE_INTROSPECTION,
        "alterios_live_task_preflight",
        "alterios_create_material_module",
        "alterios_fast_live_write",
        "alterios_upsert_content_type",
        "alterios_list_content_types",
    } <= enabled
    assert "alterios_upsert_user" not in enabled
    assert "alterios_delete_role" not in enabled
    assert "gitea_create_work_item" in enabled
    assert "future_unclassified_tool" not in enabled


def test_admin_profile_adds_typed_admin_and_security_tools_without_raw_escapes() -> None:
    enabled = set(allowed_tool_names(SAMPLE_TOOLS, "admin"))

    assert "alterios_list_content_types" in enabled
    assert "alterios_upsert_content_type" in enabled
    assert "alterios_upsert_user" in enabled
    assert "alterios_delete_role" in enabled
    assert "gitea_create_work_item" in enabled
    assert "alterios_rest_write" not in enabled
    assert "alterios_call_write_service" not in enabled


@pytest.mark.parametrize("profile", ["live", "discovery", "admin"])
def test_restricted_profiles_exclude_raw_write_escape_hatches(profile: str) -> None:
    enabled = set(allowed_tool_names(SAMPLE_TOOLS, profile))

    assert "alterios_rest_write" not in enabled
    assert "alterios_call_write_service" not in enabled


def test_apply_tool_profile_uses_public_remove_tool_in_deterministic_order() -> None:
    fake = FakeMCP(SAMPLE_TOOLS)

    summary = apply_tool_profile(fake, SAMPLE_TOOLS, "discovery")

    assert fake.removed == sorted(set(SAMPLE_TOOLS) - set(summary["enabled_tool_names"]))
    assert fake.tool_names == set(summary["enabled_tool_names"])
    assert summary["applied"] is True
    assert summary["profile"] == "discovery"
    assert summary["removed_count"] == len(fake.removed)
    assert summary["introspection_enabled"] is True


def test_profile_summary_is_machine_readable_and_reports_raw_escape_decisions() -> None:
    summary = build_tool_profile_summary(SAMPLE_TOOLS, "admin")

    assert summary["input_count"] == len(SAMPLE_TOOLS)
    assert summary["enabled_count"] + summary["removed_count"] == summary["input_count"]
    assert summary["raw_write_escape_hatches"] == {
        "enabled": [],
        "removed": ["alterios_call_write_service", "alterios_rest_write"],
    }
    assert summary["classifications"]["unknown"] == ["future_unclassified_tool"]
    assert summary["introspection_registered"] is True
