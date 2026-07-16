from __future__ import annotations

from alterios_mcp.deep_inventory import build_deep_inventory


def test_deep_inventory_links_forms_scripts_bpmn_and_icons() -> None:
    forms = [
        {
            "_id": "form-main",
            "name": "Main",
            "pageTitle": "Main",
            "tabs": [
                {
                    "name": "List",
                    "rows": [
                        {
                            "cells": [
                                {
                                    "name": "Rows",
                                    "type": "view_data_list",
                                    "params": {"viewId": "view-1", "openId": True},
                                    "styles": {"width": "100%"},
                                    "displaying": {"fields": {"title": {"title": "Title"}}},
                                    "valueActionContainers": [
                                        {
                                            "title": "Run",
                                            "iconId": "sync",
                                            "actions": [
                                                {
                                                    "_id": "script-1",
                                                    "name": "Import rows",
                                                    "type": "manual_script",
                                                    "argumentsConfig": {"contentId": {"source": "openId"}},
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ]
                        }
                    ],
                }
            ],
            "formActionContainers": [
                {
                    "title": "Save",
                    "iconId": "save",
                    "actions": [{"type": "data_managing", "dataManagingType": "submit_all"}],
                }
            ],
        }
    ]
    scripts = [
        {
            "_id": "script-1",
            "name": "Import rows",
            "type": "manual",
            "active": True,
            "body": "createContent({}); getTasks({});",
            "config": {"arguments": {"contentId": "string"}},
            "librariesIds": [],
        }
    ]
    diagrams = [
        {
            "_id": "diagram-1",
            "name": "Flow",
            "value": """
<bpmn2:definitions xmlns:bpmn2="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
  <bpmn2:process id="Process_1">
    <bpmn2:userTask id="Task_1" name="Fill" camunda:formKey="form-main">
      <bpmn2:outgoing>Flow_1</bpmn2:outgoing>
    </bpmn2:userTask>
    <bpmn2:scriptTask id="Script_1" name="Script step" camunda:class="script-1" />
  </bpmn2:process>
</bpmn2:definitions>
""",
        }
    ]

    result = build_deep_inventory(
        forms=forms,
        scripts=scripts,
        diagrams=diagrams,
        groups=[],
        processes_by_diagram={"diagram-1": [{"_id": "process-1", "status": "done"}]},
        tasks_by_diagram={"diagram-1": [{"_id": "task-1", "name": "Fill", "status": "active"}]},
        profile="test",
        project_id="project-1",
        generated_at="2026-07-10T00:00:00+00:00",
    )

    forms_inventory = result["form_surface_inventory"]
    linkage = result["script_bpmn_linkage"]
    icons = result["icon_usage_matrix"]

    assert forms_inventory["totals"]["forms"] == 1
    assert forms_inventory["totals"]["cell_types"]["view_data_list"] == 1
    assert forms_inventory["totals"]["action_types"]["manual_script"] == 1
    assert forms_inventory["totals"]["action_types"]["save_submit"] == 1
    assert linkage["totals"]["form_script_links"] == 1
    assert linkage["form_script_links"][0]["script_match"]["script_id"] == "script-1"
    assert linkage["form_script_links"][0]["argument_bindings"] == {"contentId": "openId"}
    assert linkage["form_script_links"][0]["argument_contract"] == {
        "ok": True,
        "bindings": {"contentId": "openId"},
        "declared_arguments": ["contentId"],
        "issues": [],
    }
    assert linkage["totals"]["user_task_form_links"] == 1
    assert linkage["user_task_form_links"][0]["form_match"]["form_id"] == "form-main"
    assert linkage["totals"]["service_calls"]["createContent"] == 1
    assert linkage["diagrams"][0]["process_summary"]["process_count"] == 1
    assert icons["totals"]["icon_usages"] >= 2


def test_deep_inventory_flattens_nested_row_menu_actions() -> None:
    result = build_deep_inventory(
        forms=[
            {
                "_id": "form-list",
                "name": "Questions",
                "pageTitle": "Questions",
                "tabs": [
                    {
                        "rows": [
                            {
                                "cells": [
                                    {
                                        "type": "view_data_list",
                                        "params": {"viewId": "view-1"},
                                        "styles": {"width": "100%"},
                                        "displaying": {"fields": {"title": {}}},
                                        "valueActionContainers": [
                                            {
                                                "type": "menu",
                                                "iconId": "more_vert",
                                                "actions": [],
                                                "containers": [
                                                    {
                                                        "type": "action",
                                                        "title": "Edit",
                                                        "iconId": "edit",
                                                        "actions": [{"_id": "form-edit", "type": "forms"}],
                                                    },
                                                    {
                                                        "type": "action",
                                                        "title": "View",
                                                        "iconId": "preview",
                                                        "default": True,
                                                        "actions": [{"_id": "form-view", "type": "forms"}],
                                                    },
                                                    {
                                                        "type": "action",
                                                        "title": "Delete",
                                                        "iconId": "delete",
                                                        "actions": [{"type": "delete_contents"}],
                                                    },
                                                ],
                                            }
                                        ],
                                    }
                                ]
                            }
                        ]
                    }
                ],
            }
        ],
        scripts=[],
        diagrams=[],
        groups=[],
        profile="test",
        project_id="project-1",
        generated_at="2026-07-10T00:00:00+00:00",
    )

    actions = result["form_surface_inventory"]["action_matrix"]
    titles = [action["title"] for action in actions]

    assert titles == ["Edit", "View", "Delete"]
    assert actions[1]["default"] is True
    assert actions[1]["target_form_id"] == "form-view"
    assert actions[2]["category"] == "delete"


def test_deep_inventory_flags_empty_manual_script_argument_binding() -> None:
    result = build_deep_inventory(
        forms=[
            {
                "_id": "form-1",
                "name": "Form",
                "pageTitle": "Form",
                "tabs": [{"rows": [{"cells": [{"type": "field"}]}]}],
                "formActionContainers": [
                    {
                        "type": "action",
                        "title": "Run",
                        "actions": [
                            {
                                "_id": "script-1",
                                "name": "Script",
                                "type": "manual_script",
                                "argumentsConfig": {
                                    "type": "context",
                                    "args": {"contentId": {}},
                                },
                            }
                        ],
                    }
                ],
            }
        ],
        scripts=[
            {
                "_id": "script-1",
                "name": "Script",
                "type": "manual",
                "active": True,
                "config": {"arguments": [{"key": "contentId"}]},
            }
        ],
        diagrams=[],
        groups=[],
        profile="test",
        project_id="project-1",
        generated_at="2026-07-10T00:00:00+00:00",
    )

    link = result["script_bpmn_linkage"]["form_script_links"][0]
    assert link["argument_bindings"] == {"contentId": None}
    assert link["argument_contract"]["ok"] is False
    assert link["argument_contract"]["issues"][0]["code"] == "manual_script_empty_argument_binding"


def test_deep_inventory_does_not_export_script_body_or_api_key() -> None:
    result = build_deep_inventory(
        forms=[],
        scripts=[
            {
                "_id": "script-1",
                "name": "Secret script",
                "type": "manual",
                "active": True,
                "apiKey": "secret",
                "body": "const token = 'secret'; updateContent({});",
                "config": {"apiKey": "secret", "visible": True},
            }
        ],
        diagrams=[],
        groups=[],
        profile="test",
        project_id="project-1",
        generated_at="2026-07-10T00:00:00+00:00",
    )

    script = result["script_bpmn_linkage"]["scripts"][0]

    assert "body" not in script
    assert "apiKey" not in script["config_shape"]
    assert script["body_length"] > 0
    assert script["body_sha256"]
    assert script["service_calls"][0]["name"] == "updateContent"
