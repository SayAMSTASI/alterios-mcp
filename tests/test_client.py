from __future__ import annotations

import os
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import pytest

from alterios_mcp.client import (
    AlteriosClient,
    AlteriosConfig,
    AlteriosConfigError,
    AlteriosRequestError,
    AlteriosResponse,
    build_script_body,
    configured_profiles,
    discover_profile_names,
    redact_url_value,
)


def test_profile_does_not_fall_back_to_default_target() -> None:
    env = {
        "ALTERIOS_BASE_URL": "https://default.example",
        "ALTERIOS_API_TOKEN": "default-token",
        "ALTERIOS_PROJECT_ID": "default-project",
        "ALTERIOS_ENDPOINT_TEMPLATE": "{base_url}/api/scripts/execute-manual",
    }

    with patch.dict(os.environ, env, clear=True):
        config = AlteriosConfig.from_env(dotenv_path=None, profile="primary")

    assert config.profile == "primary"
    assert config.base_url == ""
    assert config.api_token == ""
    assert config.project_id == ""
    assert config.endpoint_template == "{base_url}/api/scripts/execute-manual"
    assert config.missing_for_instance_call() == [
        "ALTERIOS_PRIMARY_API_TOKEN",
        "ALTERIOS_PRIMARY_BASE_URL",
    ]
    assert config.missing_for_project_call() == [
        "ALTERIOS_PRIMARY_API_TOKEN",
        "ALTERIOS_PRIMARY_BASE_URL",
        "ALTERIOS_PRIMARY_PROJECT_ID",
    ]


def test_profile_overrides_shared_settings() -> None:
    env = {
        "ALTERIOS_PROFILE": "primary",
        "ALTERIOS_ENDPOINT_TEMPLATE": "{base_url}/api/scripts/execute-manual",
        "ALTERIOS_PRIMARY_BASE_URL": "https://primary.example",
        "ALTERIOS_PRIMARY_API_TOKEN": "profile-token",
        "ALTERIOS_PRIMARY_PROJECT_ID": "profile-project",
        "ALTERIOS_PRIMARY_AUTH_HEADER": "x-api-key",
        "ALTERIOS_PRIMARY_AUTH_SCHEME": "",
    }

    with patch.dict(os.environ, env, clear=True):
        config = AlteriosConfig.from_env(dotenv_path=None)

    assert config.profile == "primary"
    assert config.base_url == "https://primary.example"
    assert config.api_token == "profile-token"
    assert config.project_id == "profile-project"
    assert config.auth_header == "x-api-key"
    assert config.auth_scheme == ""


def test_discover_profile_names_from_explicit_list_and_prefixes() -> None:
    values = {
        "ALTERIOS_PROFILE": "primary",
        "ALTERIOS_PROFILES": "secondary; demo",
        "ALTERIOS_PRIMARY_BASE_URL": "https://primary.example",
        "ALTERIOS_SECONDARY_BASE_URL": "http://secondary.local",
        "ALTERIOS_EXTRA_INSTANCE_API_TOKEN": "token",
    }

    assert discover_profile_names(values) == ["primary", "demo", "extra_instance", "secondary"]


def test_configured_profiles_returns_redacted_multi_instance_inventory() -> None:
    env = {
        "ALTERIOS_PROFILE": "primary",
        "ALTERIOS_PROFILES": "primary, secondary",
        "ALTERIOS_ENDPOINT_TEMPLATE": "{base_url}/api/scripts/execute-manual",
        "ALTERIOS_PRIMARY_BASE_URL": "https://primary.example",
        "ALTERIOS_PRIMARY_API_TOKEN": "primary-token",
        "ALTERIOS_PRIMARY_PROJECT_ID": "primary-project",
        "ALTERIOS_PRIMARY_AUTH_HEADER": "x-api-key",
        "ALTERIOS_SECONDARY_BASE_URL": "http://secondary.local",
        "ALTERIOS_SECONDARY_API_TOKEN": "secondary-token",
    }

    with patch.dict(os.environ, env, clear=True):
        payload = configured_profiles(dotenv_path=None)

    assert payload["selected_profile"] == "primary"
    assert payload["profile_count"] == 2
    by_profile = {item["profile"]: item for item in payload["profiles"]}
    assert by_profile["primary"]["selected"] is True
    assert by_profile["primary"]["config"]["api_token"] == "<set>"
    assert by_profile["primary"]["config"]["project_id"] == "primary-project"
    assert by_profile["primary"]["missing_for_instance_call"] == []
    assert by_profile["secondary"]["selected"] is False
    assert by_profile["secondary"]["config"]["api_token"] == "<set>"
    assert by_profile["secondary"]["missing_for_project_call"] == ["ALTERIOS_SECONDARY_PROJECT_ID"]
    assert "primary-token" not in json_dump(payload)
    assert "secondary-token" not in json_dump(payload)


def test_configured_profiles_can_inventory_default_config() -> None:
    env = {
        "ALTERIOS_BASE_URL": "https://default.example",
        "ALTERIOS_API_TOKEN": "default-token",
        "ALTERIOS_PROJECT_ID": "default-project",
    }

    with patch.dict(os.environ, env, clear=True):
        payload = configured_profiles(dotenv_path=None)

    assert payload["profile_count"] == 1
    assert payload["profiles"][0]["profile"] == "<default>"
    assert payload["profiles"][0]["profile_argument"] is None
    assert payload["profiles"][0]["selected"] is True
    assert payload["profiles"][0]["missing_for_instance_call"] == []
    assert "default-token" not in json_dump(payload)


def test_profile_script_missing_key_is_profile_scoped() -> None:
    env = {
        "ALTERIOS_PROFILE": "secondary",
        "ALTERIOS_SECONDARY_BASE_URL": "http://secondary.local",
        "ALTERIOS_SECONDARY_API_TOKEN": "secondary-token",
        "ALTERIOS_SECONDARY_PROJECT_ID": "secondary-project",
    }

    with patch.dict(os.environ, env, clear=True):
        config = AlteriosConfig.from_env(dotenv_path=None)

    assert config.missing_for_script_call() == ["ALTERIOS_SECONDARY_ENDPOINT_TEMPLATE"]


def test_redacted_config_strips_url_credentials_and_sensitive_query() -> None:
    assert (
        redact_url_value("https://user:password@example.local/path?token=secret&limit=1")
        == "https://<redacted>@example.local/path?token=%3Credacted%3E&limit=1"
    )


def test_alterios_dotenv_path_overrides_default_dotenv(tmp_path) -> None:
    env_file = tmp_path / "alterios.env"
    env_file.write_text(
        "\n".join(
            [
                "ALTERIOS_PROFILE=primary",
                "ALTERIOS_PRIMARY_BASE_URL=https://primary.example",
                "ALTERIOS_PRIMARY_API_TOKEN=profile-token",
                "ALTERIOS_PRIMARY_PROJECT_ID=profile-project",
            ]
        ),
        encoding="utf-8",
    )

    with patch.dict(os.environ, {"ALTERIOS_DOTENV_PATH": str(env_file)}, clear=True):
        config = AlteriosConfig.from_env()

    assert config.profile == "primary"
    assert config.base_url == "https://primary.example"
    assert config.api_token == "profile-token"
    assert config.project_id == "profile-project"


def test_prepare_script_request_redacts_secret_headers() -> None:
    config = AlteriosConfig(
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="project-1",
        endpoint_template="{base_url}/api/services/{function}",
        auth_header="x-api-key",
        auth_scheme="",
    )

    prepared = AlteriosClient(config).prepare_script_request("getTasks", {"limit": 1})

    redacted = prepared.redacted()
    assert redacted["headers"]["x-api-key"] == "<redacted>"
    assert redacted["headers"]["projectid"] == "project-1"


def test_project_id_can_be_overridden_per_call() -> None:
    config = AlteriosConfig(
        profile="primary",
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="default-project",
    )

    override = config.with_project_id("explicit-project")

    assert override.project_id == "explicit-project"
    assert override.profile == "primary"
    assert override.base_url == "https://alterios.example"


def test_report_full_builds_encoded_filter_path_without_network() -> None:
    config = AlteriosConfig(
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="project-1",
    )
    client = AlteriosClient(config)

    with patch.object(client, "_send", return_value=AlteriosResponse(200, "application/json", {})) as send:
        response = client.report_full("report 1")

    assert response.status_code == 200
    prepared = send.call_args.args[0]
    assert prepared.method == "GET"
    assert prepared.url == "https://alterios.example/api/reports/full/%7B%22_id%22%3A%22report%201%22%7D"
    assert prepared.body is None
    assert prepared.headers["projectid"] == "project-1"


def test_view_data_builds_context_body_without_network() -> None:
    config = AlteriosConfig(
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="project-1",
    )
    client = AlteriosClient(config)

    with patch.object(client, "_send", return_value=AlteriosResponse(200, "application/json", {})) as send:
        response = client.view_data(
            "view-1",
            limit=5,
            offset=10,
            content_id="content-1",
            data_id=["data-1", "data-2"],
            user_filters={"status": ["open"]},
        )

    assert response.status_code == 200
    prepared = send.call_args.args[0]
    assert prepared.method == "POST"
    assert prepared.url == "https://alterios.example/api/views/v2/get-data"
    assert prepared.body == {
        "viewId": "view-1",
        "limit": 5,
        "offset": 10,
        "contentId": "content-1",
        "dataId": ["data-1", "data-2"],
        "userFilters": {"status": ["open"]},
    }
    assert prepared.headers["projectid"] == "project-1"


def test_view_data_omits_optional_context_without_network() -> None:
    config = AlteriosConfig(
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="project-1",
    )
    client = AlteriosClient(config)

    with patch.object(client, "_send", return_value=AlteriosResponse(200, "application/json", {})) as send:
        client.view_data("view-1")

    assert send.call_args.args[0].body == {"viewId": "view-1", "limit": 20, "offset": 0}


def test_detailed_inventory_routes_are_built_without_network() -> None:
    config = AlteriosConfig(
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="project-1",
    )
    client = AlteriosClient(config)

    with patch.object(client, "_send", return_value=AlteriosResponse(200, "application/json", {})) as send:
        client.view_full("view 1")
        client.form_full("form 1")
        client.view_entities("view 1")
        client.view_fields_populated("view 1")
        client.list_groups()

    urls = [call.args[0].url for call in send.call_args_list]
    assert urls == [
        "https://alterios.example/api/views/view%201",
        "https://alterios.example/api/forms/form%201",
        "https://alterios.example/api/view-entities/by-view/view%201",
        "https://alterios.example/api/view-fields/populated/view%201",
        "https://alterios.example/api/groups",
    ]


def test_view_and_form_listandcount_by_id_use_id_filter_without_network() -> None:
    config = AlteriosConfig(
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="project-1",
    )
    client = AlteriosClient(config)
    responses = [
        AlteriosResponse(200, "application/json", [[{"_id": "view-1", "name": "View"}], 1]),
        AlteriosResponse(200, "application/json", [[{"_id": "form-1", "name": "Form"}], 1]),
    ]

    with patch.object(client, "_send", side_effect=responses) as send:
        assert client.view_by_id("view-1").body == {"_id": "view-1", "name": "View"}
        assert client.form_by_id("form-1").body == {"_id": "form-1", "name": "Form"}

    urls = [call.args[0].url for call in send.call_args_list]
    assert urls == [
        "https://alterios.example/api/views/listandcount?_id=view-1&limit=1&offset=0",
        "https://alterios.example/api/forms/listandcount?_id=form-1&limit=1&offset=0",
    ]


def test_script_diagram_and_report_reads_use_verified_routes_without_network() -> None:
    config = AlteriosConfig(
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="project-1",
    )
    client = AlteriosClient(config)
    responses = [
        AlteriosResponse(200, "application/json", [[{"_id": "script-1", "name": "Script"}], 1]),
        AlteriosResponse(200, "application/json", [[{"_id": "diagram-1", "name": "Diagram"}], 1]),
        AlteriosResponse(200, "application/json", [{"_id": "report-1", "name": "Report", "template": "{}"}]),
    ]

    with patch.object(client, "_send", side_effect=responses) as send:
        assert client.script_by_id("script-1").body == {"_id": "script-1", "name": "Script"}
        assert client.diagram_by_id("diagram-1").body == {"_id": "diagram-1", "name": "Diagram"}
        assert client.report_by_id("report-1").body["_id"] == "report-1"

    urls = [call.args[0].url for call in send.call_args_list]
    assert urls == [
        "https://alterios.example/api/scripts/listandcount?_id=script-1&limit=1&offset=0",
        "https://alterios.example/api/diagrams/listandcount?_id=diagram-1&limit=1&offset=0",
        "https://alterios.example/api/reports/full/%7B%22_id%22%3A%22report-1%22%7D",
    ]


def test_save_resource_create_and_update_routes_without_network() -> None:
    config = AlteriosConfig(
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="project-1",
    )
    client = AlteriosClient(config)

    with patch.object(client, "_send", return_value=AlteriosResponse(200, "application/json", {})) as send:
        client.save_view({"_id": "view 1", "name": "View", "author": {"_id": "user-1"}})
        client.save_form({"name": "Form"})

    update_request = send.call_args_list[0].args[0]
    create_request = send.call_args_list[1].args[0]
    assert update_request.method == "PATCH"
    assert update_request.url == "https://alterios.example/api/views/view%201"
    assert update_request.body == {"_id": "view 1", "name": "View"}
    assert create_request.method == "POST"
    assert create_request.url == "https://alterios.example/api/forms"
    assert create_request.body == {"name": "Form"}


def test_delete_user_uses_ui_observed_body_route_without_network() -> None:
    config = AlteriosConfig(
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="project-1",
    )
    client = AlteriosClient(config)

    with patch.object(client, "_send", return_value=AlteriosResponse(200, "application/json", {})) as send:
        client.delete_user("user 1")

    request = send.call_args.args[0]
    assert request.method == "DELETE"
    assert request.url == "https://alterios.example/api/users"
    assert request.body == {"_id": "user 1"}
    assert request.headers["projectid"] == "project-1"


def test_shared_content_type_routes_without_network() -> None:
    config = AlteriosConfig(
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="target-project",
    )
    client = AlteriosClient(config)

    with patch.object(client, "_send", return_value=AlteriosResponse(200, "application/json", [])) as send:
        client.list_shared_content_types()
        client.clone_content_type("source-type")

    shared_request = send.call_args_list[0].args[0]
    clone_request = send.call_args_list[1].args[0]
    assert shared_request.method == "GET"
    assert shared_request.url == "https://alterios.example/api/content-types?share=true"
    assert clone_request.method == "POST"
    assert clone_request.url == "https://alterios.example/api/content-types/clone"
    assert clone_request.body == {"id": "source-type"}
    assert clone_request.headers["projectid"] == "target-project"


def test_view_entity_and_field_write_routes_without_network() -> None:
    config = AlteriosConfig(
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="project-1",
    )
    client = AlteriosClient(config)

    with patch.object(client, "_send", return_value=AlteriosResponse(200, "application/json", {})) as send:
        client.save_view_entity({"_id": "entity-1", "name": "Entity", "updatedBy": "ignored"})
        client.add_view_entity_field("entity-1", content_type_field_id="field-1")
        client.add_view_entity_field("entity-1", attribute="_id", content_type_id="content-type-1")
        client.save_view_field({"_id": "vf-1", "alias": "Title", "contentType": {"name": "ignored"}})

    requests = [call.args[0] for call in send.call_args_list]
    assert requests[0].method == "PATCH"
    assert requests[0].url == "https://alterios.example/api/view-entities/entity-1"
    assert requests[0].body == {"_id": "entity-1", "name": "Entity"}
    assert requests[1].method == "POST"
    assert requests[1].url == "https://alterios.example/api/view-entities/add-one-field"
    assert requests[1].body == {"entityId": "entity-1", "contentTypeFieldId": "field-1"}
    assert requests[2].method == "POST"
    assert requests[2].url == "https://alterios.example/api/view-entities/add-one-field"
    assert requests[2].body == {"entityId": "entity-1", "attribute": "_id"}
    assert requests[3].method == "POST"
    assert requests[3].url == "https://alterios.example/api/view-fields/save"
    assert requests[3].body == {"_id": "vf-1", "alias": "Title", "contentType": {"name": "ignored"}}


def test_script_diagram_report_process_and_task_write_routes_without_network() -> None:
    config = AlteriosConfig(
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="project-1",
    )
    client = AlteriosClient(config)

    with patch.object(client, "_send", return_value=AlteriosResponse(200, "application/json", {})) as send:
        client.save_script({"_id": "script-1", "name": "Script", "body": "code", "apiKey": "ignored"})
        client.save_script({"name": "Script", "body": "code"})
        client.save_diagram({"_id": "diagram-1", "name": "Diagram"})
        client.save_report({"_id": "report-1", "name": "Report"})
        client.start_process("diagram-1", content_id="content-1", params={"source": "test"})
        client.complete_task("task-1", next_flow_id="Flow_to_end", contents=[])

    requests = [call.args[0] for call in send.call_args_list]
    assert requests[0].method == "PUT"
    assert requests[0].url == "https://alterios.example/api/scripts"
    assert requests[0].body["apiKey"] == "secret-token"
    assert requests[1].method == "POST"
    assert requests[1].url == "https://alterios.example/api/scripts"
    assert requests[2].method == "PATCH"
    assert requests[2].url == "https://alterios.example/api/diagrams/di…16026 tokens truncated…                              {
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
        profile="secondary",
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
    loaded = load_latest_snapshot(profile="secondary", project_id="project-1")

    assert loaded is not None
    assert Path(tmp_path, written["latest_path"]).exists()

    result = server.alterios_project_health(
        profile="secondary",
        project_id="project-1",
        refresh=False,
        use_cache=True,
        write_cache=False,
    )

    assert result["source"] == "cache"
    assert result["readonly"] is True
    assert result["summary"]["issue_count"] >= 1
