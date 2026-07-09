from __future__ import annotations

from unittest.mock import patch

import pytest

from alterios_mcp import server
from alterios_mcp.write_control import (
    ControlledWriteError,
    WriteOperation,
    assert_write_allowed,
    build_write_audit,
    collect_target_ids,
)


def test_write_audit_requires_explicit_profile_and_project() -> None:
    operation = WriteOperation(
        name="PUT /api/reports",
        kind="rest",
        risk_level="write",
        summary="Update report",
    )

    with pytest.raises(ControlledWriteError, match="explicit profile"):
        build_write_audit(
            profile=None,
            project_id="project-1",
            operation=operation,
            dry_run=True,
            write_enabled=False,
        )

    with pytest.raises(ControlledWriteError, match="explicit project_id"):
        build_write_audit(
            profile="vniimt",
            project_id=None,
            operation=operation,
            dry_run=True,
            write_enabled=False,
        )


def test_dry_run_audit_redacts_sensitive_request_values() -> None:
    operation = WriteOperation(
        name="POST /api/example",
        kind="rest",
        risk_level="write",
        summary="Example write",
        method="POST",
        path="/api/example",
        target_ids=("record-1",),
        request={"body": {"token": "secret-token", "password": "secret-password", "name": "demo"}},
    )

    audit = build_write_audit(
        profile="vniimt",
        project_id="project-1",
        operation=operation,
        dry_run=True,
        write_enabled=False,
    ).as_dict()

    assert audit["status"] == "dry_run"
    assert audit["operation"]["request"]["body"]["token"] == "<redacted>"
    assert audit["operation"]["request"]["body"]["password"] == "<redacted>"
    assert audit["operation"]["request"]["body"]["name"] == "demo"


def test_write_execution_requires_env_gate() -> None:
    operation = WriteOperation(
        name="PUT /api/reports",
        kind="rest",
        risk_level="write",
        summary="Update report",
    )

    with pytest.raises(ControlledWriteError, match="ALTERIOS_MCP_ALLOW_WRITE"):
        assert_write_allowed(
            profile="vniimt",
            project_id="project-1",
            operation=operation,
            write_enabled=False,
        )


def test_destructive_execution_requires_extra_flag() -> None:
    operation = WriteOperation(
        name="DELETE /api/contents",
        kind="rest",
        risk_level="destructive",
        summary="Delete content",
    )

    with pytest.raises(ControlledWriteError, match="allow_destructive"):
        assert_write_allowed(
            profile="vniimt",
            project_id="project-1",
            operation=operation,
            write_enabled=True,
            allow_destructive=False,
        )


def test_collect_target_ids_finds_common_id_shapes() -> None:
    assert collect_target_ids(
        {
            "_id": ["content-1", "content-2"],
            "nested": {"taskId": "task_1", "processesIds": ["process-1"]},
            "ignored": "value",
        }
    ) == ("content-1", "content-2", "task_1", "process-1")


def test_rest_write_defaults_to_dry_run_without_network() -> None:
    with patch.dict("os.environ", {}, clear=True):
        result = server.alterios_rest_write(
            "PUT",
            "/api/reports",
            {"_id": "report-1", "name": "Report"},
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is True
    assert result["response"] is None
    assert result["audit"]["write_enabled"] is False
    assert result["audit"]["operation"]["target_ids"] == ["report-1"]


def test_add_comment_defaults_to_dry_run_without_network() -> None:
    with patch.dict("os.environ", {}, clear=True):
        result = server.alterios_add_comment(
            "content-1",
            "Practice comment",
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is True
    assert result["response"] is None
    assert result["audit"]["operation"]["path"] == "/api/v1/comments"
    assert result["audit"]["operation"]["target_ids"] == ["content-1"]


def test_server_lists_configured_profiles_without_secrets() -> None:
    env = {
        "ALTERIOS_PROFILE": "vniimt",
        "ALTERIOS_PROFILES": "vniimt, artx",
        "ALTERIOS_VNIIMT_BASE_URL": "http://lims.vniimt.local",
        "ALTERIOS_VNIIMT_API_TOKEN": "vniimt-token",
        "ALTERIOS_ARTX_BASE_URL": "http://artx.local",
        "ALTERIOS_ARTX_API_TOKEN": "artx-token",
    }

    with patch.dict("os.environ", env, clear=True):
        result = server.alterios_list_profiles(profile="artx")

    assert result["profile_count"] == 2
    assert result["selected_profile"] == "artx"
    assert [item["profile"] for item in result["profiles"]] == ["artx", "vniimt"]
    assert result["profiles"][0]["config"]["api_token"] == "<set>"
    assert "vniimt-token" not in str(result)
    assert "artx-token" not in str(result)


def test_rest_write_execution_fails_without_write_env() -> None:
    with patch.dict("os.environ", {}, clear=True), pytest.raises(ControlledWriteError, match="disabled"):
        server.alterios_rest_write(
            "PUT",
            "/api/reports",
            {"_id": "report-1"},
            dry_run=False,
            profile="vniimt",
            project_id="project-1",
        )


def test_delete_rest_write_execution_requires_destructive_flag() -> None:
    with patch.dict("os.environ", {"ALTERIOS_MCP_ALLOW_WRITE": "1"}, clear=True), pytest.raises(
        ControlledWriteError,
        match="allow_destructive",
    ):
        server.alterios_rest_write(
            "DELETE",
            "/api/contents",
            {"_id": ["content-1"]},
            dry_run=False,
            profile="vniimt",
            project_id="project-1",
        )


def test_write_service_rejects_readonly_service_name() -> None:
    with pytest.raises(ValueError, match="readonly|read-only"):
        server.alterios_call_write_service(
            "getTasks",
            {"query": {"limit": 1}},
            profile="vniimt",
            project_id="project-1",
        )


def test_manual_script_dry_run_requires_uuid() -> None:
    with pytest.raises(ValueError, match="script UUID"):
        server.alterios_execute_manual_script(
            "getTasks",
            {"limit": 1},
            profile="vniimt",
            project_id="project-1",
        )


def test_rest_write_execution_returns_audit_and_response_without_real_network() -> None:
    class FakeResponse:
        def as_dict(self) -> dict[str, object]:
            return {
                "status_code": 200,
                "content_type": "application/json",
                "body": {"ok": True, "token": "secret-token"},
            }

    class FakeClient:
        def request(self, method: str, path: str, *, params: dict[str, object], body: dict[str, object]) -> FakeResponse:
            assert method == "PUT"
            assert path == "/api/reports"
            assert params == {}
            assert body == {"_id": "report-1"}
            return FakeResponse()

    with (
        patch.dict("os.environ", {"ALTERIOS_MCP_ALLOW_WRITE": "1"}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_rest_write(
            "PUT",
            "/api/reports",
            {"_id": "report-1"},
            dry_run=False,
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is False
    assert result["audit"]["status"] == "ready_to_execute"
    assert result["audit"]["write_enabled"] is True
    assert result["response"]["body"] == {"ok": True, "token": "<redacted>"}


def test_add_comment_execution_returns_created_comment_and_readback_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self._body = body

        def as_dict(self) -> dict[str, object]:
            return {"status_code": 200, "content_type": "application/json", "body": self._body}

    class FakeClient:
        def add_comment(self, entity_id: str, body: str, *, entity: str, parent_id: str | None = None) -> FakeResponse:
            assert entity_id == "content-1"
            assert body == "Practice comment"
            assert entity == "any"
            assert parent_id is None
            return FakeResponse({"_id": "comment-1", "body": body})

        def list_comments(
            self,
            entity_id: str,
            *,
            entity: str = "any",
            limit: int = 20,
            depth: int = 1,
            page: int = 1,
        ) -> FakeResponse:
            assert entity_id == "content-1"
            assert entity == "any"
            assert limit == 20
            assert depth == 4
            assert page == 1
            return FakeResponse([{"_id": "comment-1", "body": "Practice comment"}])

    with (
        patch.dict("os.environ", {"ALTERIOS_MCP_ALLOW_WRITE": "1"}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_add_comment(
            "content-1",
            "Practice comment",
            dry_run=False,
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is False
    assert result["response"]["created"]["body"]["_id"] == "comment-1"
    assert result["response"]["readback"]["body"] == [{"_id": "comment-1", "body": "Practice comment"}]
