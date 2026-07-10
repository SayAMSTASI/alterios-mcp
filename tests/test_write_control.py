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


def test_update_content_fields_dry_run_returns_preflight_diff_without_real_network() -> None:
    class FakeResponse:
        body = {
            "_id": "content-1",
            "contentTypeId": "ct-1",
            "name": "Row",
            "fields": {"field_title": ["Old"]},
        }

    class FakeClient:
        def content_by_id(self, content_id: str) -> FakeResponse:
            assert content_id == "content-1"
            return FakeResponse()

    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_update_content_fields(
            "content-1",
            {"field_title": "New"},
            expected_content_type_id="ct-1",
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is True
    assert result["audit"]["operation"]["kind"] == "content_fields"
    assert result["audit"]["operation"]["target_ids"] == ["content-1", "ct-1"]
    assert result["response"]["field_diff"] == [
        {"field": "field_title", "before": ["Old"], "after": ["New"], "changed": True}
    ]
    assert result["response"]["planned_payload"]["fields"]["field_title"] == ["New"]


def test_update_content_fields_execution_uses_write_gate_and_readback_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

        def as_dict(self) -> dict[str, object]:
            return {"status_code": 200, "content_type": "application/json", "body": self.body}

    class FakeClient:
        def __init__(self) -> None:
            self.saved = False

        def content_by_id(self, content_id: str) -> FakeResponse:
            fields = {"field_title": ["New"]} if self.saved else {"field_title": ["Old"]}
            return FakeResponse({"_id": content_id, "contentTypeId": "ct-1", "name": "Row", "fields": fields})

        def update_content_fields(
            self,
            content_id: str,
            field_values: dict[str, object],
            *,
            content_type_id: str | None = None,
            groups_ids: list[str] | None = None,
            name: str | None = None,
        ) -> FakeResponse:
            assert content_id == "content-1"
            assert field_values == {"field_title": "New"}
            assert content_type_id == "ct-1"
            self.saved = True
            return FakeResponse({"_id": content_id, "updated": True})

    fake_client = FakeClient()
    with (
        patch.dict("os.environ", {"ALTERIOS_MCP_ALLOW_WRITE": "1"}, clear=True),
        patch.object(server, "_client", return_value=fake_client),
    ):
        result = server.alterios_update_content_fields(
            "content-1",
            {"field_title": "New"},
            expected_content_type_id="ct-1",
            dry_run=False,
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is False
    assert result["response"]["updated"]["body"] == {"_id": "content-1", "updated": True}
    assert result["response"]["readback"]["body"]["fields"] == {"field_title": ["New"]}


def test_file_upload_to_field_dry_run_resolves_file_field_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeClient:
        def content_by_id(self, content_id: str) -> FakeResponse:
            assert content_id == "content-1"
            return FakeResponse({"_id": content_id, "contentTypeId": "ct-1", "name": "Row", "fields": {}})

        def list_fields(self, *, content_type_id: str, field_id: str | None = None, limit: int | None = None, offset: int | None = None) -> FakeResponse:
            assert content_type_id == "ct-1"
            return FakeResponse([{"_id": "field-1", "mname": "field_file", "type": "file"}])

    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_file_upload_to_field(
            "content-1",
            "field_file",
            "demo.txt",
            text="demo",
            expected_content_type_id="ct-1",
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is True
    assert result["audit"]["operation"]["kind"] == "file_upload"
    assert result["response"]["file"]["field_id"] == "field-1"
    assert result["response"]["file"]["size"] == 4
    assert result["response"]["existing_file_value_count"] == 0


def test_file_upload_to_field_execution_uploads_saves_and_reads_back_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

        def as_dict(self) -> dict[str, object]:
            return {"status_code": 200, "content_type": "application/json", "body": self.body}

    class FakeClient:
        def __init__(self) -> None:
            self.saved_value: list[object] | None = None

        def content_by_id(self, content_id: str) -> FakeResponse:
            fields = {"field_file": self.saved_value or []}
            return FakeResponse({"_id": content_id, "contentTypeId": "ct-1", "name": "Row", "fields": fields})

        def list_fields(self, *, content_type_id: str, field_id: str | None = None, limit: int | None = None, offset: int | None = None) -> FakeResponse:
            return FakeResponse([{"_id": "field-1", "mname": "field_file", "type": "file"}])

        def upload_file_to_field(
            self,
            data: bytes,
            *,
            filename: str,
            content_type_id: str,
            field_id: str,
            mime_type: str | None = None,
        ) -> FakeResponse:
            assert data == b"demo"
            assert filename == "demo.txt"
            assert content_type_id == "ct-1"
            assert field_id == "field-1"
            return FakeResponse({"_id": "file-1", "filename": "demo.txt", "mimeType": "text/plain", "size": 4})

        def update_content_fields(
            self,
            content_id: str,
            field_values: dict[str, object],
            *,
            content_type_id: str | None = None,
            groups_ids: list[str] | None = None,
            name: str | None = None,
        ) -> FakeResponse:
            self.saved_value = field_values["field_file"]  # type: ignore[assignment]
            return FakeResponse({"_id": content_id, "updated": True})

        def file_metadata(self, file_ids: list[str]) -> FakeResponse:
            assert file_ids == ["file-1"]
            return FakeResponse([{"_id": "file-1", "filename": "demo.txt"}])

    fake_client = FakeClient()
    with (
        patch.dict("os.environ", {"ALTERIOS_MCP_ALLOW_WRITE": "1"}, clear=True),
        patch.object(server, "_client", return_value=fake_client),
    ):
        result = server.alterios_file_upload_to_field(
            "content-1",
            "field_file",
            "demo.txt",
            text="demo",
            expected_content_type_id="ct-1",
            dry_run=False,
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is False
    assert result["response"]["uploaded"]["body"]["_id"] == "file-1"
    assert result["response"]["file_metadata"]["body"] == [{"_id": "file-1", "filename": "demo.txt"}]
    assert result["response"]["readback"]["body"]["fields"]["field_file"][0]["id"] == "file-1"


def test_upsert_view_dry_run_returns_diff_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeClient:
        def list_views(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return FakeResponse(
                [
                    [
                        {
                            "_id": "view-1",
                            "name": "View",
                            "description": "Codex-managed: existing",
                            "format": "cards",
                            "settings": {},
                            "strict": True,
                        }
                    ],
                    1,
                ]
            )

    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_upsert_view(
            "View",
            settings={"engineVersion": "v2"},
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is True
    assert result["audit"]["operation"]["kind"] == "view"
    assert result["audit"]["operation"]["target_ids"] == ["view-1"]
    assert result["audit"]["operation"]["request"] == {"_id": "view-1", "name": "View"}
    assert result["response"]["preflight"]["_id"] == "view-1"
    assert {"field": "settings", "before": {}, "after": {"engineVersion": "v2"}, "changed": True} in result["response"]["diff"]
    assert {"field": "format", "before": "cards", "after": "cards", "changed": False} in result["response"]["diff"]
    assert {"field": "strict", "before": True, "after": True, "changed": False} in result["response"]["diff"]


def test_upsert_view_rejects_unmanaged_existing_object_without_flag() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeClient:
        def list_views(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return FakeResponse([[{"_id": "view-1", "name": "View", "description": "manual"}], 1])

    with patch.object(server, "_client", return_value=FakeClient()), pytest.raises(ValueError, match="not marked"):
        server.alterios_upsert_view("View", profile="vniimt", project_id="project-1")


def test_upsert_form_execution_saves_and_reads_back_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

        def as_dict(self) -> dict[str, object]:
            return {"status_code": 200, "content_type": "application/json", "body": self.body}

    class FakeClient:
        def form_by_id(self, form_id: str) -> FakeResponse:
            return FakeResponse(
                {
                    "_id": form_id,
                    "name": "Form",
                    "description": "Codex-managed: existing",
                    "pageTitle": "Form",
                    "tabs": [],
                    "formActionContainers": [],
                }
            )

        def save_form(self, payload: dict[str, object]) -> FakeResponse:
            assert payload["_id"] == "form-1"
            assert payload["tabs"] == [{"name": None, "rows": []}]
            return FakeResponse({"_id": "form-1", "saved": True})

    with (
        patch.dict("os.environ", {"ALTERIOS_MCP_ALLOW_WRITE": "1"}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_upsert_form(
            "Form",
            form_id="form-1",
            tabs=[{"name": None, "rows": []}],
            dry_run=False,
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is False
    assert result["response"]["saved"]["body"] == {"_id": "form-1", "saved": True}
    assert result["response"]["readback"]["body"]["_id"] == "form-1"


def test_upsert_view_entity_dry_run_uses_parent_view_guard_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeClient:
        def view_by_id(self, view_id: str) -> FakeResponse:
            return FakeResponse({"_id": view_id, "name": "View", "description": "Codex-managed: view"})

        def view_entities(self, view_id: str) -> FakeResponse:
            return FakeResponse([{"_id": "entity-1", "name": "Entity", "type": "content", "config": {}, "joins": []}])

    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_upsert_view_entity(
            "view-1",
            "Entity",
            config={"main": True},
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is True
    assert result["audit"]["operation"]["kind"] == "view_entity"
    assert result["audit"]["operation"]["target_ids"] == ["entity-1", "view-1"]
    assert result["response"]["preflight"]["_id"] == "entity-1"
    assert {"field": "config", "before": {}, "after": {"main": True}, "changed": True} in result["response"]["diff"]


def test_upsert_view_field_execution_adds_then_saves_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

        def as_dict(self) -> dict[str, object]:
            return {"status_code": 200, "content_type": "application/json", "body": self.body}

    class FakeClient:
        def __init__(self) -> None:
            self.added = False

        def view_by_id(self, view_id: str) -> FakeResponse:
            return FakeResponse({"_id": view_id, "name": "View", "description": "Codex-managed: view"})

        def view_fields_populated(self, view_id: str) -> FakeResponse:
            if not self.added:
                return FakeResponse([])
            return FakeResponse(
                [
                    {
                        "_id": "vf-1",
                        "entityId": "entity-1",
                        "contentTypeFieldId": "field-1",
                        "alias": "Old",
                        "mname": "old",
                        "order": 99,
                    }
                ]
            )

        def add_view_entity_field(
            self,
            entity_id: str,
            *,
            attribute: str | None = None,
            content_type_field_id: str | None = None,
        ) -> FakeResponse:
            assert entity_id == "entity-1"
            assert content_type_field_id == "field-1"
            self.added = True
            return FakeResponse({"_id": "vf-1"})

        def save_view_field(self, payload: dict[str, object]) -> FakeResponse:
            assert payload["_id"] == "vf-1"
            assert payload["alias"] == "Title"
            assert payload["mname"] == "title"
            assert payload["order"] == 1
            return FakeResponse({"_id": "vf-1", "saved": True})

    fake_client = FakeClient()
    with (
        patch.dict("os.environ", {"ALTERIOS_MCP_ALLOW_WRITE": "1"}, clear=True),
        patch.object(server, "_client", return_value=fake_client),
    ):
        result = server.alterios_upsert_view_field(
            "view-1",
            "entity-1",
            content_type_field_id="field-1",
            alias="Title",
            mname="title",
            order=1,
            dry_run=False,
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is False
    assert result["response"]["added"]["body"] == {"_id": "vf-1"}
    assert result["response"]["saved"]["body"] == {"_id": "vf-1", "saved": True}
    assert result["response"]["readback"]["_id"] == "vf-1"


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
