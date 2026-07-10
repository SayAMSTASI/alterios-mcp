from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_practice_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "artx_practice_metadata.py"
    spec = importlib.util.spec_from_file_location("artx_practice_metadata", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dashboard_column_name_uses_actual_view_field_mname() -> None:
    module = load_practice_module()

    assert (
        module.dashboard_column_name(
            {"field_mcp_practice_title": {"mname": "test__mcp_practice_mcp_practice_title"}},
            "title",
        )
        == "test__mcp_practice_mcp_practice_title"
    )


def test_report_template_helpers_read_nested_dashboard_template() -> None:
    module = load_practice_module()
    report = {
        "template": {
            "Dictionary": {
                "Databases": {
                    "0": {
                        "ServiceName": "Project Database",
                    }
                }
            },
            "Pages": {
                "0": {
                    "Components": {
                        "0": {
                            "Name": "OpenIdCurrentRowTitle",
                            "Text": "{data.test__mcp_practice_mcp_practice_title}",
                        }
                    }
                }
            },
        }
    }

    assert module.report_has_project_database(report) is True
    assert module.report_template_contains_text(report, "OpenIdCurrentRowTitle") is True
    assert module.report_template_contains_text(report, "test__mcp_practice_mcp_practice_title") is True
    assert module.report_template_contains_text(report, "missing_field") is False
