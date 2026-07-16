from __future__ import annotations

import pytest

from alterios_mcp.form_script_actions import (
    build_manual_script_action_container,
    find_manual_script_action,
    resolve_entity_id_provider_key,
    upsert_manual_script_action,
    validate_manual_script_bindings,
)


SCRIPT_ID = "11111111-1111-4111-8111-111111111111"
SCRIPT = {
    "_id": SCRIPT_ID,
    "name": "Update row",
    "type": "manual",
    "active": True,
    "config": {"arguments": [{"key": "contentId"}]},
}


def test_resolve_entity_id_provider_key_uses_view_field_mname() -> None:
    result = resolve_entity_id_provider_key(
        [
            {"_id": "field-main", "entityId": "entity-main", "mname": "_id", "type": "attribute"},
            {"_id": "field-related", "entityId": "entity-related", "mname": "_id5", "type": "attribute"},
            {"_id": "field-name", "entityId": "entity-related", "mname": "name", "type": "field"},
        ],
        "entity-related",
    )

    assert result == {
        "entity_id": "entity-related",
        "provider_key": "_id5",
        "view_field_id": "field-related",
        "alias": None,
        "candidate_count": 1,
    }


def test_value_action_is_created_inside_menu_and_is_idempotent() -> None:
    form = {
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {
                                "type": "view_data_list",
                                "params": {"viewId": "view-1"},
                                "valueActionContainers": [],
                            }
                        ]
                    }
                ]
            }
        ]
    }
    container = build_manual_script_action_container(
        script=SCRIPT,
        scope="value",
        title="Update",
        tooltip="Update row",
        icon_id="22222222-2222-4222-8222-222222222222",
        bindings={"contentId": "_id5"},
        action_view_entity_id="entity-related",
        position=None,
        default=False,
        save_before_execute=False,
    )

    created, location = upsert_manual_script_action(
        form,
        scope="value",
        action_container=container,
        script_id=SCRIPT_ID,
        tab_index=0,
        row_index=0,
        cell_index=0,
        menu_icon_id="33333333-3333-4333-8333-333333333333",
    )
    updated, second_location = upsert_manual_script_action(
        created,
        scope="value",
        action_container=container,
        script_id=SCRIPT_ID,
        tab_index=0,
        row_index=0,
        cell_index=0,
        menu_icon_id="33333333-3333-4333-8333-333333333333",
    )

    menus = updated["tabs"][0]["rows"][0]["cells"][0]["valueActionContainers"]
    assert location["operation"] == "created"
    assert second_location["operation"] == "updated"
    assert len(menus) == 1
    assert menus[0]["type"] == "menu"
    assert len(menus[0]["containers"]) == 1
    assert find_manual_script_action(updated, SCRIPT_ID) == {
        "scope": "value",
        "path": "tabs[0].rows[0].cells[0].valueActionContainers[0].containers[0].actions[0]",
        "script_id": SCRIPT_ID,
        "script_name": "Update row",
        "arguments_config": {
            "args": {"contentId": {"dataProviderKey": "_id5"}},
            "type": "context",
        },
        "view_entity_id": "entity-related",
    }


def test_element_action_is_icon_only_and_can_save_before_script() -> None:
    container = build_manual_script_action_container(
        script=SCRIPT,
        scope="element",
        title="Process",
        tooltip=None,
        icon_id="22222222-2222-4222-8222-222222222222",
        bindings={"contentId": "__entity_id"},
        action_view_entity_id=None,
        position=None,
        default=False,
        save_before_execute=True,
    )

    assert container["title"] == ""
    assert container["tooltip"] == "Process"
    assert [action["type"] for action in container["actions"]] == ["data_managing", "manual_script"]
    assert container["actions"][0]["dataManagingType"] == "submit_all"


def test_binding_validation_blocks_provider_missing_from_view() -> None:
    result = validate_manual_script_bindings(
        script=SCRIPT,
        scope="value",
        bindings={"contentId": "_id9"},
        available_provider_keys={"__entity_id", "openId", "_id", "_id5"},
        action_view_entity_id="entity-related",
    )

    assert result["ok"] is False
    assert result["issues"][0]["code"] == "manual_script_provider_not_in_view"


def test_repeated_script_actions_require_a_unique_title() -> None:
    form = {
        "formActionContainers": [
            {
                "type": "action",
                "title": "First",
                "actions": [{"_id": SCRIPT_ID, "name": "Update row", "type": "manual_script"}],
            },
            {
                "type": "action",
                "title": "Second",
                "actions": [{"_id": SCRIPT_ID, "name": "Update row", "type": "manual_script"}],
            },
        ]
    }
    ambiguous = build_manual_script_action_container(
        script=SCRIPT,
        scope="page",
        title="Third",
        tooltip=None,
        icon_id="22222222-2222-4222-8222-222222222222",
        bindings={},
        action_view_entity_id=None,
        position=None,
        default=False,
        save_before_execute=False,
    )

    with pytest.raises(ValueError, match="multiple actions"):
        upsert_manual_script_action(
            form,
            scope="page",
            action_container=ambiguous,
            script_id=SCRIPT_ID,
            tab_index=None,
            row_index=None,
            cell_index=None,
            menu_icon_id=None,
        )
