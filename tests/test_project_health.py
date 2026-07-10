from __future__ import annotations

from pathlib import Path

from alterios_mcp import server
from alterios_mcp.deep_inventory import build_deep_inventory
from alterios_mcp.project_health import (
    build_health_snapshot,
    build_project_health,
    diff_snapshots,
    load_latest_snapshot,
    save_snapshot,
)


def _deep_inventory(*, script_body: str = "noop();") -> dict:
    forms = [
        {
            "_id": "form-main",
            "name": "Main",
            "pageTitle": "Main",
            "tabs": [
                {
                    "rows": [
                        {
                            "cells": [
                                {
                                    "name": "Rows",
                                    "type": "view_data_list",
                                    "params": {"viewId": "missing-view", "openId": True},
                                    "styles": {"width": "100%"},
                                    "displaying": {"fields": {"title": {"title": "Title"}}},
                                    "valueActionContainers": [
                                        {
                                            "title": "Open missing form",
                                            "actions": [{"type": "forms", "_id": "missing-form"}],
                                        },
                                        {
                                            "title": "Run missing script",
                                            "actions": [{"type": "manual_script", "scriptId": "missing-script"}],
                                        },
                                    ],
                                },
                                {
                                    "name": "Report",
                                    "type": "report",
                                    "params": {"reportId": "missing-report", "openId": True},
                                    "styles": {"width": "100%"},
                                },
                            ]
                        }
                    ]
                }
            ],
        }
    ]
    scripts = [{"_id": "script-existing", "name": "Existing", "type": "manual", "body": script_body}]
    diagrams = [
        {
            "_id": "diagram-1",
            "name": "Flow",
            "value": """
<bpmn2:definitions xmlns:bpmn2="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
  <bpmn2:process id="Process_1">
    <bpmn2:userTask id="Task_1" name="Fill" camunda:formKey="missing-task-form" />
  </bpmn2:process>
</bpmn2:definitions>
""",
        },
        {"_id": "diagram-bad", "name": "Broken XML", "value": "<bpmn2:definitions>"},
    ]
    return build_deep_inventory(
        forms=forms,
        scripts=scripts,
        diagrams=diagrams,
        groups=[],
        profile="artx",
        project_id="project-1",
        generated_at="2026-07-10T00:00:00Z",
    )


def _snapshot(*, script_body: str = "noop();") -> dict:
    return build_health_snapshot(
        deep_inventory=_deep_inventory(script_body=script_body),
        views=[{"_id": "view-ok", "name": "Visible view"}],
        reports=[{"_id": "report-ok", "name": "Visible report"}],
        full_reports=[
            {
                "_id": "report-layout-bad",
                "name": "Bad layout",
                "template": {
                    "Pages": {
                        "0": {
                            "Width": 100,
                            "Height": 100,
                            "Components": {
                                "0": {"Ident": "StiTextElement", "Name": "A", "ClientRectangle": "0,0,0,30"},
                            },
                        }
                    }
                },
            }
        ],
    )


def test_project_health_detects_prewrite_risks() -> None:
    health = build_project_health(snapshot=_snapshot())
    codes = health["summary"]["issues_by_code"]

    assert health["summary"]["ok"] is False
    assert codes["missing_view_ref"] == 1
    assert codes["missing_report_ref"] == 1
    assert codes["missing_form_action_target"] == 1
    assert codes["missing_form_script_ref"] == 1
    assert codes["missing_bpmn_form_key"] == 1
    assert codes["bpmn_parse_error"] == 1
    assert codes["report_layout_issues"] == 1
    assert health["summary"]["counts"] == {"forms": 1, "scripts": 1, "diagrams": 2, "views": 1, "reports": 1}


def test_project_health_diff_detects_changed_script() -> None:
    before = _snapshot(script_body="noop();")
    after = _snapshot(script_body="updateContent({});")

    diff = diff_snapshots(before, after)

    assert diff["available"] is True
    assert diff["changed"] is True
    assert diff["entities"]["scripts"]["changed"] == 1
    assert diff["entities"]["forms"]["changed"] == 0


def test_project_health_cache_roundtrip_and_server_tool(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALTERIOS_MCP_ARTIFACTS_DIR", str(tmp_path))
    written = save_snapshot(_snapshot())
    loaded = load_latest_snapshot(profile="artx", project_id="project-1")

    assert loaded is not None
    assert Path(tmp_path, written["latest_path"]).exists()

    result = server.alterios_project_health(
        profile="artx",
        project_id="project-1",
        refresh=False,
        use_cache=True,
        write_cache=False,
    )

    assert result["source"] == "cache"
    assert result["readonly"] is True
    assert result["summary"]["issue_count"] >= 1
