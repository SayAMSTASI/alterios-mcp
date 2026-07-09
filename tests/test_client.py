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
