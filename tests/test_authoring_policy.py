import pytest

from alterios_mcp.authoring_policy import AUTHORING_INSTRUCTIONS, MANAGED_MARKER
from alterios_mcp.validators.common import _assert_managed_or_allowed, _assert_help_managed_or_allowed
from alterios_mcp.validators.module_contract import is_meaningful_description
from alterios_mcp import server


@pytest.mark.parametrize("marker", [MANAGED_MARKER, "Codex-managed"])
def test_ownership_checks_accept_current_and_legacy_markers(marker):
    _assert_managed_or_allowed({"description": marker}, kind="Form", allow_unmanaged_update=False)
    _assert_help_managed_or_allowed({"value": marker}, allow_unmanaged_update=False)
    assert not is_meaningful_description(marker)


def test_unmanaged_description_remains_protected():
    with pytest.raises(ValueError):
        _assert_managed_or_allowed({"description": "Подробное описание формы обработки данных"},
                                   kind="Form", allow_unmanaged_update=False)


def test_generated_description_replaces_legacy_marker_and_preserves_reference():
    text = server._managed_description("Codex-managed: Форма; источник field_example.", "")
    assert "Codex" not in text
    assert MANAGED_MARKER in text
    assert "field_example" in text


def test_server_initialize_instructions_and_contract_share_policy():
    assert server.mcp._mcp_server.create_initialization_options().instructions == AUTHORING_INSTRUCTIONS
    assert server.alterios_ux_contract()["authoring_instructions"] == AUTHORING_INSTRUCTIONS
