from __future__ import annotations

import ast
import json
from pathlib import Path

from alterios_mcp.builders.common import _content_summary, _resource_operation
from alterios_mcp.scenarios.runtime import alterios_ux_contract
from alterios_mcp.scenarios.views_forms import alterios_analyze_form_surface
from alterios_mcp.tools import DOMAIN_MODULES, all_tool_functions, all_tool_names
from alterios_mcp.validators.common import _validate_script_type_config
from alterios_mcp.ux_contract import (
    BLOCKING_FORM_ISSUE_CODES,
    PRINTABLE_REPORT_DEFAULT,
    SCENARIO_APPLY_REQUIRES,
    UX_CONTRACT_VERSION,
)


PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "alterios_mcp"
REPO_ROOT = Path(__file__).parents[1]


def test_server_is_a_small_composition_root() -> None:
    server_path = PACKAGE_ROOT / "server.py"
    lines = server_path.read_text(encoding="utf-8").splitlines()

    assert len(lines) < 500
    assert "FastMCP" in "\n".join(lines)
    assert "register_all_tools(mcp)" in "\n".join(lines)


def test_domain_registration_modules_are_thin_and_complete() -> None:
    functions = all_tool_functions()
    names = all_tool_names()

    assert len(functions) == len(names) == 107
    assert len(names) == len(set(names))
    for module in DOMAIN_MODULES:
        path = Path(module.__file__)
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        function_names = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert function_names <= {"tool_functions", "register"}
        assert len(source.splitlines()) < 80


def test_scenarios_builders_and_validators_do_not_import_fastmcp_or_server() -> None:
    roots = (
        PACKAGE_ROOT / "scenarios",
        PACKAGE_ROOT / "builders",
        PACKAGE_ROOT / "validators",
    )
    for root in roots:
        for path in root.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert "mcp.server.fastmcp" not in source
            assert "alterios_mcp.server" not in source
            assert "from ..server" not in source
            assert "@mcp.tool" not in source


def test_builders_and_validators_are_callable_without_fastmcp() -> None:
    summary = _content_summary({"_id": "content-1", "name": "Row", "contentTypeId": "type-1"})
    operation = _resource_operation(
        name="PATCH test",
        kind="test",
        method="PATCH",
        path="/api/test",
        summary="Builder smoke",
        request={"_id": "content-1"},
    )

    assert summary == {
        "_id": "content-1",
        "name": "Row",
        "contentTypeId": "type-1",
        "field_keys": [],
    }
    assert operation.target_ids == ("content-1",)
    _validate_script_type_config("manual", {"arguments": []})


def test_scenarios_are_directly_testable_without_fastmcp() -> None:
    contract = alterios_ux_contract()
    surface = alterios_analyze_form_surface(
        form={"name": "Список", "tabs": [{"name": "Список", "rows": []}]},
    )

    assert contract["version"]
    assert surface["form"]["name"] == "Список"
    assert isinstance(surface["surface"]["issues"], list)


def test_machine_readable_ux_contract_is_synchronized_with_code_and_docs() -> None:
    contract_json = json.loads((REPO_ROOT / "docs" / "ux-contract.json").read_text(encoding="utf-8"))
    contract_markdown = (REPO_ROOT / "docs" / "ux-contract.md").read_text(encoding="utf-8")

    assert contract_json["version"] == UX_CONTRACT_VERSION
    assert set(contract_json["blocking_form_issue_codes"]) == set(BLOCKING_FORM_ISSUE_CODES)
    assert contract_json["scenario_apply_requires"] == list(SCENARIO_APPLY_REQUIRES)
    assert contract_json["printable_report_default"] == PRINTABLE_REPORT_DEFAULT
    assert f"Версия контракта: `{UX_CONTRACT_VERSION}`" in contract_markdown
