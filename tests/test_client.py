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
        config = AlteriosConfig.from_env(dotenv_path=None, profile="vniimt")

    assert config.profile == "vniimt"
    assert config.base_url == ""
    assert config.api_token == ""
    assert config.project_id == ""
    assert config.endpoint_template == "{base_url}/api/scripts/execute-manual"
    assert config.missing_for_instance_call() == [
        "ALTERIOS_VNIIMT_API_TOKEN",
        "ALTERIOS_VNIIMT_BASE_URL",
    ]
    assert config.missing_for_project_call() == [
        "ALTERIOS_VNIIMT_API_TOKEN",
        "ALTERIOS_VNIIMT_BASE_URL",
        "ALTERIOS_VNIIMT_PROJECT_ID",
    ]


def test_profile_overrides_shared_settings() -> None:
    env = {
        "ALTERIOS_PROFILE": "vniimt",
        "ALTERIOS_ENDPOINT_TEMPLATE": "{base_url}/api/scripts/execute-manual",
        "ALTERIOS_VNIIMT_BASE_URL": "http://lims.vniimt.local",
        "ALTERIOS_VNIIMT_API_TOKEN": "profile-token",
        "ALTERIOS_VNIIMT_PROJECT_ID": "profile-project",
        "ALTERIOS_VNIIMT_AUTH_HEADER": "x-api-key",
        "ALTERIOS_VNIIMT_AUTH_SCHEME": "",
    }

    with patch.dict(os.environ, env, clear=True):
        config = AlteriosConfig.from_env(dotenv_path=None)

    assert config.profile == "vniimt"
    assert config.base_url == "http://lims.vniimt.local"
    assert config.api_token == "profile-token"
    assert config.project_id == "profile-project"
    assert config.auth_header == "x-api-key"
    assert config.auth_scheme == ""


def test_discover_profile_names_from_explicit_list_and_prefixes() -> None:
    values = {
        "ALTERIOS_PROFILE": "vniimt",
        "ALTERIOS_PROFILES": "artx-prod; demo",
        "ALTERIOS_VNIIMT_BASE_URL": "http://lims.vniimt.local",
        "ALTERIOS_ARTX_PROD_BASE_URL": "http://artx.local",
        "ALTERIOS_EXTRA_INSTANCE_API_TOKEN": "token",
    }

    assert discover_profile_names(values) == ["vniimt", "artx-prod", "demo", "extra_instance"]


def test_configured_profiles_returns_redacted_multi_instance_inventory() -> None:
    env = {
        "ALTERIOS_PROFILE": "vniimt",
        "ALTERIOS_PROFILES": "vniimt, artx-prod",
        "ALTERIOS_ENDPOINT_TEMPLATE": "{base_url}/api/scripts/execute-manual",
        "ALTERIOS_VNIIMT_BASE_URL": "http://lims.vniimt.local",
        "ALTERIOS_VNIIMT_API_TOKEN": "vniimt-token",
        "ALTERIOS_VNIIMT_PROJECT_ID": "vniimt-project",
        "ALTERIOS_VNIIMT_AUTH_HEADER": "x-api-key",
        "ALTERIOS_ARTX_PROD_BASE_URL": "http://artx.local",
        "ALTERIOS_ARTX_PROD_API_TOKEN": "artx-token",
    }

    with patch.dict(os.environ, env, clear=True):
        payload = configured_profiles(dotenv_path=None)

    assert payload["selected_profile"] == "vniimt"
    assert payload["profile_count"] == 2
    by_profile = {item["profile"]: item for item in payload["profiles"]}
    assert by_profile["vniimt"]["selected"] is True
    assert by_profile["vniimt"]["config"]["api_token"] == "<set>"
    assert by_profile["vniimt"]["config"]["project_id"] == "vniimt-project"
    assert by_profile["vniimt"]["missing_for_instance_call"] == []
    assert by_profile["artx-prod"]["selected"] is False
    assert by_profile["artx-prod"]["config"]["api_token"] == "<set>"
    assert by_profile["artx-prod"]["missing_for_project_call"] == ["ALTERIOS_ARTX_PROD_PROJECT_ID"]
    assert "vniimt-token" not in json_dump(payload)
    assert "artx-token" not in json_dump(payload)


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
        "ALTERIOS_PROFILE": "artx-prod",
        "ALTERIOS_ARTX_PROD_BASE_URL": "http://artx.local",
        "ALTERIOS_ARTX_PROD_API_TOKEN": "artx-token",
        "ALTERIOS_ARTX_PROD_PROJECT_ID": "artx-project",
    }

    with patch.dict(os.environ, env, clear=True):
        config = AlteriosConfig.from_env(dotenv_path=None)

    assert config.missing_for_script_call() == ["ALTERIOS_ARTX_PROD_ENDPOINT_TEMPLATE"]


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
                "ALTERIOS_PROFILE=vniimt",
                "ALTERIOS_VNIIMT_BASE_URL=http://lims.vniimt.local",
                "ALTERIOS_VNIIMT_API_TOKEN=profile-token",
                "ALTERIOS_VNIIMT_PROJECT_ID=profile-project",
            ]
        ),
        encoding="utf-8",
    )

    with patch.dict(os.environ, {"ALTERIOS_DOTENV_PATH": str(env_file)}, clear=True):
        config = AlteriosConfig.from_env()

    assert config.profile == "vniimt"
    assert config.base_url == "http://lims.vniimt.local"
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
        profile="vniimt",
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="default-project",
    )

    override = config.with_project_id("explicit-project")

    assert override.project_id == "explicit-project"
    assert override.profile == "vniimt"
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
        client.save_view_field({"_id": "vf-1", "alias": "Title", "contentType": {"name": "ignored"}})

    requests = [call.args[0] for call in send.call_args_list]
    assert requests[0].method == "PATCH"
    assert requests[0].url == "https://alterios.example/api/view-entities/entity-1"
    assert requests[0].body == {"_id": "entity-1", "name": "Entity"}
    assert requests[1].method == "POST"
    assert requests[1].url == "https://alterios.example/api/view-entities/add-one-field"
    assert requests[1].body == {"entityId": "entity-1", "contentTypeFieldId": "field-1"}
    assert requests[2].method == "POST"
    assert requests[2].url == "https://alterios.example/api/view-fields/save"
    assert requests[2].body == {"_id": "vf-1", "alias": "Title", "contentType": {"name": "ignored"}}


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
    assert requests[2].url == "https://alterios.example/api/diagrams/diagram-1"
    assert requests[3].method == "PUT"
    assert requests[3].url == "https://alterios.example/api/reports"
    assert requests[4].method == "POST"
    assert requests[4].url == "https://alterios.example/api/processes"
    assert requests[4].body == {"diagramId": "diagram-1", "contentId": "content-1", "params": {"source": "test"}}
    assert requests[5].method == "DELETE"
    assert requests[5].url == "https://alterios.example/api/tasks/complete"
    assert requests[5].body == {"_id": "task-1", "nextFlowId": "Flow_to_end", "contents": []}


def test_list_fields_builds_expected_query_without_network() -> None:
    config = AlteriosConfig(
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="project-1",
    )
    client = AlteriosClient(config)

    with patch.object(client, "_send", return_value=AlteriosResponse(200, "application/json", {})) as send:
        client.list_fields(content_type_id="ct-1", field_id="field-1", limit=10, offset=5)

    parsed = urlparse(send.call_args.args[0].url)
    assert parsed.path == "/api/fields"
    assert parse_qs(parsed.query) == {
        "contentTypeId": ["ct-1"],
        "_id": ["field-1"],
        "limit": ["10"],
        "offset": ["5"],
    }


def test_file_metadata_requires_ids_and_repeats_query_without_network() -> None:
    config = AlteriosConfig(
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="project-1",
    )
    client = AlteriosClient(config)

    with pytest.raises(ValueError, match="file_ids"):
        client.file_metadata([])

    with patch.object(client, "_send", return_value=AlteriosResponse(200, "application/json", {})) as send:
        client.file_metadata(["file-1", "file-2"])

    parsed = urlparse(send.call_args.args[0].url)
    assert parsed.path == "/api/file/list"
    assert parse_qs(parsed.query) == {"id": ["file-1", "file-2"]}


def test_content_by_id_uses_id_filter_and_returns_single_row_without_network() -> None:
    config = AlteriosConfig(
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="project-1",
    )
    client = AlteriosClient(config)

    body = {"total": 1, "values": [{"_id": "content-1", "fields": {"field_title": ["Old"]}}]}
    with patch.object(client, "_send", return_value=AlteriosResponse(200, "application/json", body)) as send:
        response = client.content_by_id("content-1")

    parsed = urlparse(send.call_args.args[0].url)
    assert parsed.path == "/api/contents/listandcount"
    assert parse_qs(parsed.query) == {"_id": ["content-1"], "limit": ["1"], "offset": ["0"]}
    assert response.body == {"_id": "content-1", "fields": {"field_title": ["Old"]}}


def test_update_content_fields_patches_existing_content_without_network() -> None:
    config = AlteriosConfig(
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="project-1",
    )
    client = AlteriosClient(config)
    responses = [
        AlteriosResponse(
            200,
            "application/json",
            {
                "total": 1,
                "values": [
                    {
                        "_id": "content-1",
                        "contentTypeId": "ct-1",
                        "name": "Row",
                        "groupsIds": ["group-1"],
                        "fields": {"field_title": ["Old"], "field_score": [1]},
                    }
                ],
            },
        ),
        AlteriosResponse(200, "application/json", {"_id": "content-1", "ok": True}),
    ]

    with patch.object(client, "_send", side_effect=responses) as send:
        client.update_content_fields("content-1", {"field_title": "New", "field_empty": []})

    prepared = send.call_args_list[1].args[0]
    assert prepared.method == "PATCH"
    assert prepared.url == "https://alterios.example/api/contents/save"
    assert prepared.body == {
        "_id": "content-1",
        "contentTypeId": "ct-1",
        "name": "Row",
        "groupsIds": ["group-1"],
        "fields": {"field_title": ["New"], "field_score": [1], "field_empty": []},
    }


def test_upload_file_to_field_posts_multipart_without_network() -> None:
    config = AlteriosConfig(
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="project-1",
        auth_header="x-api-key",
        auth_scheme="",
    )
    client = AlteriosClient(config)
    captured = {}

    class FakeHTTPResponse:
        status = 200
        headers = {"Content-Type": "application/json"}

        def __enter__(self) -> "FakeHTTPResponse":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"_id":"file-1","filename":"demo.txt","size":4}'

    def fake_urlopen(request: object, timeout: float) -> FakeHTTPResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeHTTPResponse()

    with patch("alterios_mcp.client.urlopen", side_effect=fake_urlopen):
        response = client.upload_file_to_field(
            b"demo",
            filename="demo.txt",
            content_type_id="ct-1",
            field_id="field-1",
            mime_type="text/plain",
        )

    request = captured["request"]
    headers = {key.lower(): value for key, value in request.header_items()}
    assert request.get_method() == "POST"
    assert request.full_url == "https://alterios.example/api/file/upload/field"
    assert headers["projectid"] == "project-1"
    assert headers["x-api-key"] == "secret-token"
    assert headers["contenttype"] == "ct-1"
    assert headers["field"] == "field-1"
    assert headers["content-type"].startswith("multipart/form-data; boundary=")
    assert b'filename="demo.txt"' in request.data
    assert b"demo" in request.data
    assert response.body == {"_id": "file-1", "filename": "demo.txt", "size": 4}


def test_list_comments_builds_v1_query_without_network() -> None:
    config = AlteriosConfig(
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="project-1",
    )
    client = AlteriosClient(config)

    with patch.object(client, "_send", return_value=AlteriosResponse(200, "application/json", {})) as send:
        client.list_comments("entity-1", entity="content", limit=50, depth=4, page=2)

    parsed = urlparse(send.call_args.args[0].url)
    assert parsed.path == "/api/v1/comments"
    assert parse_qs(parsed.query) == {
        "entity": ["content"],
        "entityId": ["entity-1"],
        "limit": ["50"],
        "depth": ["4"],
        "page": ["2"],
    }


def test_add_comment_posts_v1_payload_without_network() -> None:
    config = AlteriosConfig(
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="project-1",
    )
    client = AlteriosClient(config)

    with patch.object(client, "_send", return_value=AlteriosResponse(200, "application/json", {})) as send:
        client.add_comment("entity-1", "Body", entity="content", parent_id="parent-1")

    prepared = send.call_args.args[0]
    parsed = urlparse(prepared.url)
    assert parsed.path == "/api/v1/comments"
    assert prepared.method == "POST"
    assert prepared.body == {
        "entity": "content",
        "entityId": "entity-1",
        "body": "Body",
        "parentId": "parent-1",
    }


def test_mutating_service_requires_allow_write() -> None:
    config = AlteriosConfig(
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="project-1",
        endpoint_template="{base_url}/api/scripts/execute-manual",
    )

    with pytest.raises(AlteriosRequestError):
        AlteriosClient(config).prepare_script_request("deleteManyContents", {"_id": ["1"]})


def test_execute_manual_endpoint_requires_script_uuid() -> None:
    config = AlteriosConfig(
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="project-1",
        endpoint_template="{base_url}/api/scripts/execute-manual",
    )

    with pytest.raises(AlteriosRequestError, match="requires a script UUID"):
        AlteriosClient(config).prepare_script_request("getTasks", {"limit": 1})


def test_execute_manual_script_bypasses_runtime_service_catalog_without_network() -> None:
    script_id = "11111111-1111-4111-8111-111111111111"
    config = AlteriosConfig(
        base_url="https://alterios.example",
        api_token="secret-token",
        project_id="project-1",
        endpoint_template="{base_url}/api/scripts/execute-manual",
        body_style="rpc",
    )
    client = AlteriosClient(config)

    with patch.object(client, "_send", return_value=AlteriosResponse(200, "application/json", {"ok": True})) as send:
        client.execute_manual_script(script_id, {"contentId": "content-1"})

    prepared = send.call_args.args[0]
    assert prepared.method == "POST"
    assert prepared.url == "https://alterios.example/api/scripts/execute-manual"
    assert prepared.body == {"_id": script_id, "args": {"contentId": "content-1"}}


def test_script_body_styles() -> None:
    assert build_script_body("getTasks", {"limit": 1}, "rpc") == {"function": "getTasks", "args": {"limit": 1}}
    assert build_script_body("getTasks", {"limit": 1}, "service") == {"service": "getTasks", "args": {"limit": 1}}
    assert build_script_body("getTasks", {"limit": 1}, "params") == {"function": "getTasks", "params": {"limit": 1}}
    assert build_script_body("getTasks", {"limit": 1}, "direct") == {"function": "getTasks", "args": {"limit": 1}}


def test_direct_body_uses_script_id_shape_for_uuid() -> None:
    script_id = "11111111-2222-3333-4444-555555555555"

    assert build_script_body(script_id, {"contentId": "c1"}, "direct") == {
        "_id": script_id,
        "args": {"contentId": "c1"},
    }


def test_manual_script_body_requires_uuid() -> None:
    script_id = "11111111-2222-3333-4444-555555555555"

    assert build_script_body(script_id, {"contentId": "c1"}, "manual_script") == {
        "_id": script_id,
        "args": {"contentId": "c1"},
    }
    with pytest.raises(AlteriosConfigError):
        build_script_body("getTasks", {"limit": 1}, "manual_script")


def json_dump(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True)
