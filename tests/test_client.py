from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from alterios_mcp.client import AlteriosClient, AlteriosConfig, AlteriosConfigError, AlteriosRequestError, build_script_body


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
