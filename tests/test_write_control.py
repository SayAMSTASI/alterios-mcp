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


def test_upsert_content_type_dry_run_returns_diff_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeClient:
        def list_content_types(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return FakeResponse(
                [
                    [
                        {
                            "_id": "ct-1",
                            "name": "Type",
                            "description": "Codex-managed: existing",
                            "settings": {"maxRefDepth": 0},
                            "share": False,
                        }
                    ],
                    1,
                ]
            )

    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_upsert_content_type(
            "Type",
            settings={"maxRefDepth": 1},
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is True
    assert result["audit"]["operation"]["kind"] == "content_type"
    assert result["audit"]["operation"]["path"] == "/api/content-types/save"
    assert {"field": "settings", "before": {"maxRefDepth": 0}, "after": {"maxRefDepth": 1}, "changed": True} in result["response"]["diff"]


def test_upsert_field_execution_saves_and_reads_back_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

        def as_dict(self) -> dict[str, object]:
            return {"status_code": 200, "content_type": "application/json", "body": self.body}

    class FakeClient:
        def __init__(self) -> None:
            self.saved = False

        def content_type_by_id(self, content_type_id: str) -> FakeResponse:
            assert content_type_id == "ct-1"
            return FakeResponse({"_id": "ct-1", "name": "Type"})

        def list_fields(self, *, content_type_id: str, field_id: str | None = None, limit: int | None = None, offset: int | None = None) -> FakeResponse:
            assert content_type_id == "ct-1"
            return FakeResponse([])

        def save_field(self, payload: dict[str, object]) -> FakeResponse:
            assert payload["contentTypeId"] == "ct-1"
            assert payload["mname"] == "field_title"
            self.saved = True
            return FakeResponse({"_id": "field-1", "saved": True})

        def field_by_id(self, field_id: str) -> FakeResponse:
            assert self.saved is True
            assert field_id == "field-1"
            return FakeResponse({"_id": "field-1", "name": "Title", "mname": "field_title", "type": "text"})

    fake_client = FakeClient()
    with (
        patch.dict("os.environ", {"ALTERIOS_MCP_ALLOW_WRITE": "1"}, clear=True),
        patch.object(server, "_client", return_value=fake_client),
    ):
        result = server.alterios_upsert_field(
            "ct-1",
            "Title",
            "text",
            mname="field_title",
            settings={"widget": "text"},
            dry_run=False,
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is False
    assert result["response"]["saved"]["body"] == {"_id": "field-1", "saved": True}
    assert result["response"]["readback"]["body"]["mname"] == "field_title"


def test_upsert_field_execution_requires_write_gate_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeClient:
        def content_type_by_id(self, content_type_id: str) -> FakeResponse:
            return FakeResponse({"_id": content_type_id, "name": "Type"})

        def list_fields(self, *, content_type_id: str, field_id: str | None = None, limit: int | None = None, offset: int | None = None) -> FakeResponse:
            return FakeResponse([])

    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
        pytest.raises(ControlledWriteError, match="disabled"),
    ):
        server.alterios_upsert_field(
            "ct-1",
            "Title",
            "text",
            mname="field_title",
            dry_run=False,
            profile="vniimt",
            project_id="project-1",
        )


def test_upsert_field_rejects_mismatched_content_type_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeClient:
        def content_type_by_id(self, content_type_id: str) -> FakeResponse:
            return FakeResponse({"_id": content_type_id, "name": "Type"})

        def field_by_id(self, field_id: str) -> FakeResponse:
            return FakeResponse(
                {
                    "_id": field_id,
                    "name": "Title",
                    "mname": "field_title",
                    "contentTypeId": "ct-2",
                    "description": "Codex-managed: existing",
                }
            )

    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
        pytest.raises(ValueError, match="belongs to content type"),
    ):
        server.alterios_upsert_field(
            "ct-1",
            "Title",
            "text",
            field_id="field-1",
            profile="vniimt",
            project_id="project-1",
        )


def test_create_content_execution_saves_and_reads_back_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

        def as_dict(self) -> dict[str, object]:
            return {"status_code": 200, "content_type": "application/json", "body": self.body}

    class FakeClient:
        def content_type_by_id(self, content_type_id: str) -> FakeResponse:
            return FakeResponse({"_id": content_type_id, "name": "Type"})

        def create_content(
            self,
            content_type_id: str,
            field_values: dict[str, object],
            *,
            groups_ids: list[str] | None = None,
            name: str | None = None,
        ) -> FakeResponse:
            assert content_type_id == "ct-1"
            assert field_values == {"field_title": "Row"}
            assert groups_ids == ["group-1"]
            assert name == "Row"
            return FakeResponse({"_id": "content-1"})

        def content_by_id(self, content_id: str) -> FakeResponse:
            assert content_id == "content-1"
            return FakeResponse({"_id": content_id, "contentTypeId": "ct-1", "name": "Row", "fields": {"field_title": ["Row"]}})

    with (
        patch.dict("os.environ", {"ALTERIOS_MCP_ALLOW_WRITE": "1"}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_create_content(
            "ct-1",
            {"field_title": "Row"},
            groups_ids=["group-1"],
            name="Row",
            dry_run=False,
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is False
    assert result["audit"]["operation"]["kind"] == "content_create"
    assert result["response"]["content_id"] == "content-1"
    assert result["response"]["readback"]["body"]["fields"]["field_title"] == ["Row"]


def test_upsert_group_and_help_dry_run_use_managed_guards_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeClient:
        def list_groups(self) -> FakeResponse:
            return FakeResponse(
                [
                    {"_id": "root", "name": "root", "root": True},
                    {"_id": "group-1", "name": "Group", "description": "Codex-managed: existing", "formId": "old-form"},
                ]
            )

        def list_helps(self) -> FakeResponse:
            return FakeResponse([{"_id": "help-1", "name": "Help", "description": "manual", "value": "old"}])

    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        group_result = server.alterios_upsert_group(
            "Group",
            form_id="form-1",
            profile="vniimt",
            project_id="project-1",
        )
        with pytest.raises(ValueError, match="not marked"):
            server.alterios_upsert_help(
                "Help",
                "new",
                profile="vniimt",
                project_id="project-1",
            )

    assert group_result["dry_run"] is True
    assert group_result["audit"]["operation"]["kind"] == "group"
    assert {"field": "formId", "before": "old-form", "after": "form-1", "changed": True} in group_result["response"]["diff"]


def test_upsert_group_rejects_missing_explicit_targets_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeClient:
        def list_groups(self) -> FakeResponse:
            return FakeResponse(
                [
                    {"_id": "root", "name": "root", "root": True},
                    {"_id": "group-1", "name": "Group", "description": "Codex-managed: existing"},
                ]
            )

    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        with pytest.raises(ValueError, match="Group 'missing' was not found"):
            server.alterios_upsert_group(
                "Group",
                group_id="missing",
                profile="vniimt",
                project_id="project-1",
            )
        with pytest.raises(ValueError, match="Parent group 'missing-parent' was not found"):
            server.alterios_upsert_group(
                "New Group",
                parent_group_id="missing-parent",
                profile="vniimt",
                project_id="project-1",
            )


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


def test_upsert_script_dry_run_uses_put_route_and_redacts_secret_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeClient:
        def list_scripts(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return FakeResponse(
                [
                    [
                        {
                            "_id": "script-1",
                            "name": "Script",
                            "description": "Codex-managed: existing",
                            "type": "manual",
                            "active": True,
                            "body": "old",
                            "apiKey": "secret-token",
                        }
                    ],
                    1,
                ]
            )

    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_upsert_script(
            "Script",
            body="new",
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is True
    assert result["audit"]["operation"]["kind"] == "script"
    assert result["audit"]["operation"]["name"] == "PUT /api/scripts"
    assert result["audit"]["operation"]["target_ids"] == ["script-1"]
    assert {"field": "body", "before": "old", "after": "new", "changed": True} in result["response"]["diff"]
    assert "secret-token" not in str(result)


def test_execute_manual_script_dry_run_prefights_script_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeClient:
        def script_by_id(self, script_id: str) -> FakeResponse:
            return FakeResponse({"_id": script_id, "name": "Script", "description": "manual", "type": "manual", "active": True})

    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_execute_manual_script(
            "11111111-1111-4111-8111-111111111111",
            {"contentId": "content-1"},
            expected_name="Script",
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is True
    assert result["audit"]["operation"]["kind"] == "manual_script"
    assert result["response"]["preflight"]["_id"] == "11111111-1111-4111-8111-111111111111"
    assert result["response"]["script_type"] == "manual"


def test_start_process_execution_returns_process_and_task_readback_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

        def as_dict(self) -> dict[str, object]:
            return {"status_code": 200, "content_type": "application/json", "body": self.body}

    class FakeClient:
        def diagram_by_id(self, diagram_id: str) -> FakeResponse:
            return FakeResponse({"_id": diagram_id, "name": "Diagram", "description": "Codex-managed: diagram"})

        def content_by_id(self, content_id: str) -> FakeResponse:
            return FakeResponse({"_id": content_id, "name": "Content", "contentTypeId": "ct-1", "fields": {}})

        def list_processes(
            self,
            *,
            diagram_id: str | None = None,
            content_id: str | None = None,
            process_id: str | None = None,
            limit: int = 20,
            offset: int = 0,
        ) -> FakeResponse:
            if process_id:
                return FakeResponse([[{"_id": process_id, "diagramId": diagram_id, "contentId": content_id}], 1])
            return FakeResponse([[], 0])

        def list_tasks(
            self,
            *,
            diagram_id: str | None = None,
            content_id: str | None = None,
            process_id: str | None = None,
            task_id: str | None = None,
        ) -> FakeResponse:
            return FakeResponse([{"_id": "task-1", "processId": process_id, "diagramId": diagram_id, "contentId": content_id}])

        def start_process(
            self,
            diagram_id: str,
            **kwargs: object,
        ) -> FakeResponse:
            assert diagram_id == "diagram-1"
            assert kwargs["content_id"] == "content-1"
            return FakeResponse({"processId": "process-1"})

    with (
        patch.dict("os.environ", {"ALTERIOS_MCP_ALLOW_WRITE": "1"}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_start_process(
            "diagram-1",
            content_id="content-1",
            params={"source": "test"},
            dry_run=False,
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is False
    assert result["audit"]["operation"]["risk_level"] == "workflow_side_effect"
    assert result["response"]["process_id"] == "process-1"
    assert result["response"]["readback_tasks"][0]["_id"] == "task-1"


def test_complete_task_dry_run_checks_expected_context_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeClient:
        def list_tasks(
            self,
            *,
            diagram_id: str | None = None,
            content_id: str | None = None,
            process_id: str | None = None,
            task_id: str | None = None,
        ) -> FakeResponse:
            return FakeResponse(
                [
                    {
                        "_id": task_id,
                        "processId": process_id,
                        "diagramId": diagram_id,
                        "contentId": content_id,
                    }
                ]
            )

    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_complete_task(
            "task-1",
            next_flow_id="Flow_to_end",
            expected_process_id="process-1",
            expected_content_id="content-1",
            expected_diagram_id="diagram-1",
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is True
    assert result["audit"]["operation"]["kind"] == "task_complete"
    assert result["audit"]["operation"]["risk_level"] == "workflow_side_effect"
    assert result["response"]["preflight_task"]["_id"] == "task-1"


def test_report_project_base_validation_checks_template_and_view_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

        def as_dict(self) -> dict[str, object]:
            return {"status_code": 201, "content_type": "application/json", "body": self.body}

    template = {
        "CodexMarker": "Codex-managed: alterios-mcp report sandbox.",
        "Pages": {"0": {"Ident": "StiDashboard"}},
        "Dictionary": {"Databases": {"0": {"ServiceName": "Project Database"}}, "DataSources": {"0": {"Name": "MCP Practice. Список"}}},
    }

    class FakeClient:
        def report_by_id(self, report_id: str) -> FakeResponse:
            return FakeResponse({"_id": report_id, "name": "Report", "description": "Codex-managed: report", "template": template})

        def view_data_simplified(self, view_id: str, *, limit: int = 20, offset: int = 0) -> FakeResponse:
            return FakeResponse({"rows": [{"_id": "row-1"}], "viewId": view_id})

    with patch.object(server, "_client", return_value=FakeClient()):
        result = server.alterios_validate_report_project_base(
            "report-1",
            expected_view_id="view-1",
            expected_view_name="MCP Practice. Список",
            expected_marker="Codex-managed: alterios-mcp report sandbox.",
            profile="vniimt",
            project_id="project-1",
        )

    assert result["validation"]["has_dashboard_page"] is True
    assert result["validation"]["has_project_database"] is True
    assert result["validation"]["view_name_matches"] is True
    assert result["validation"]["view_row_count"] == 1


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
