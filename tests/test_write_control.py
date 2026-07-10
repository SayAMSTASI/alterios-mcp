from __future__ import annotations

from unittest.mock import patch

import pytest

from alterios_mcp import server
from alterios_mcp.client import redact_sensitive
from alterios_mcp.write_control import (
    ControlledWriteError,
    WriteOperation,
    assert_write_allowed,
    build_write_audit,
    classify_rest_write_risk,
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
        request={
            "body": {
                "token": "secret-token",
                "password": "secret-password",
                "repassword": "secret-password",
                "passwordRecoverCode": "recover-code",
                "clientSecret": "client-secret",
                "name": "demo",
            }
        },
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
    assert audit["operation"]["request"]["body"]["repassword"] == "<redacted>"
    assert audit["operation"]["request"]["body"]["passwordRecoverCode"] == "<redacted>"
    assert audit["operation"]["request"]["body"]["clientSecret"] == "<redacted>"
    assert audit["operation"]["request"]["body"]["name"] == "demo"
    assert redact_sensitive({"planned_payload": {"repassword": "secret-password"}}) == {
        "planned_payload": {"repassword": "<redacted>"}
    }


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
            dangerous_write_enabled=True,
            allow_destructive=False,
        )


def test_dangerous_execution_requires_environment_gate() -> None:
    operation = WriteOperation(
        name="DELETE /api/contents",
        kind="rest",
        risk_level="destructive",
        summary="Delete content",
    )

    with pytest.raises(ControlledWriteError, match="ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE"):
        assert_write_allowed(
            profile="vniimt",
            project_id="project-1",
            operation=operation,
            write_enabled=True,
            dangerous_write_enabled=False,
            allow_destructive=True,
        )


def test_security_route_is_classified_as_dangerous() -> None:
    assert classify_rest_write_risk("PATCH", "/api/users/user-1") == "security"
    assert classify_rest_write_risk("POST", "/api/roles") == "security"
    assert classify_rest_write_risk("DELETE", "/api/contents/content-1") == "destructive"
    assert classify_rest_write_risk("PATCH", "/api/reports") == "write"


def test_collect_target_ids_finds_common_id_shapes() -> None:
    assert collect_target_ids(
        {
            "_id": ["content-1", "content-2"],
            "nested": {"taskId": "task_1", "processesIds": ["process-1"]},
            "ignored": "value",
        }
    ) == ("content-1", "content-2", "task_1", "process-1")


def test_rest_write_defaults_to_dry_run_without_network(tmp_path) -> None:
    with patch.dict("os.environ", {"ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)}, clear=True):
        result = server.alterios_rest_write(
            "PATCH",
            "/api/reports",
            {"_id": "report-1", "name": "Report"},
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is True
    assert result["response"] is None
    assert result["audit"]["write_enabled"] is False
    assert result["audit"]["dangerous_write_enabled"] is False
    assert result["audit"]["operation"]["method"] == "PATCH"
    assert result["audit"]["operation"]["target_ids"] == ["report-1"]
    assert result["plan"]["plan_id"].startswith("wp_")
    assert (tmp_path / result["plan"]["path"]).exists()


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
    with patch.dict(
        "os.environ",
        {"ALTERIOS_MCP_ALLOW_WRITE": "1", "ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE": "1"},
        clear=True,
    ), pytest.raises(
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


def test_delete_rest_write_execution_requires_dangerous_env() -> None:
    with patch.dict("os.environ", {"ALTERIOS_MCP_ALLOW_WRITE": "1"}, clear=True), pytest.raises(
        ControlledWriteError,
        match="ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE",
    ):
        server.alterios_rest_write(
            "DELETE",
            "/api/contents",
            {"_id": ["content-1"]},
            dry_run=False,
            allow_destructive=True,
            profile="vniimt",
            project_id="project-1",
        )


def test_write_safety_preflight_classifies_security_without_network() -> None:
    with patch.dict("os.environ", {"ALTERIOS_MCP_ALLOW_WRITE": "1"}, clear=True):
        result = server.alterios_write_safety_preflight(
            "PATCH",
            "/api/users/user-1",
            {"_id": "user-1", "rolesIds": ["role-1"]},
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is True
    assert result["audit"]["operation"]["risk_level"] == "security"
    assert result["audit"]["write_enabled"] is True
    assert result["audit"]["dangerous_write_enabled"] is False
    assert result["response"]["dangerous"] is True
    assert "ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE=1" in result["response"]["required_execution_gates"]


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


def test_rest_write_execution_returns_audit_and_response_without_real_network(tmp_path) -> None:
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

    with patch.dict("os.environ", {"ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)}, clear=True):
        dry_run = server.alterios_rest_write(
            "PUT",
            "/api/reports",
            {"_id": "report-1"},
            profile="vniimt",
            project_id="project-1",
        )

    with (
        patch.dict(
            "os.environ",
            {"ALTERIOS_MCP_ALLOW_WRITE": "1", "ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)},
            clear=True,
        ),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_rest_write(
            "PUT",
            "/api/reports",
            {"_id": "report-1"},
            dry_run=False,
            plan_id=dry_run["plan"]["plan_id"],
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is False
    assert result["audit"]["status"] == "ready_to_execute"
    assert result["audit"]["write_enabled"] is True
    assert result["response"]["body"] == {"ok": True, "token": "<redacted>"}
    assert result["journal"]["event_id"].startswith("wj_")


def test_rest_write_execution_rejects_changed_payload_plan_without_real_network(tmp_path) -> None:
    with patch.dict("os.environ", {"ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)}, clear=True):
        dry_run = server.alterios_rest_write(
            "PUT",
            "/api/reports",
            {"_id": "report-1", "name": "Original"},
            profile="vniimt",
            project_id="project-1",
        )

    with (
        patch.dict(
            "os.environ",
            {"ALTERIOS_MCP_ALLOW_WRITE": "1", "ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)},
            clear=True,
        ),
        pytest.raises(ValueError, match="operation does not match"),
    ):
        server.alterios_rest_write(
            "PUT",
            "/api/reports",
            {"_id": "report-1", "name": "Changed"},
            dry_run=False,
            plan_id=dry_run["plan"]["plan_id"],
            profile="vniimt",
            project_id="project-1",
        )


def test_write_plan_reader_tools_return_stored_plan_and_journal_without_network(tmp_path) -> None:
    with patch.dict("os.environ", {"ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)}, clear=True):
        dry_run = server.alterios_rest_write(
            "PATCH",
            "/api/reports",
            {"_id": "report-1", "name": "Report"},
            profile="vniimt",
            project_id="project-1",
        )
        plan_id = dry_run["plan"]["plan_id"]
        plans = server.alterios_list_write_plans(profile="vniimt", project_id="project-1")
        plan = server.alterios_get_write_plan(plan_id, profile="vniimt", project_id="project-1")
        journal = server.alterios_write_journal(profile="vniimt", project_id="project-1")

    assert plans["plans"][0]["plan_id"] == plan_id
    assert plan["plan_id"] == plan_id
    assert plan["audit"]["operation"]["path"] == "/api/reports"
    assert journal["entries"][0]["event"] == "plan_created"
    assert journal["entries"][0]["payload"]["plan_id"] == plan_id


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


def test_upsert_user_dry_run_is_security_write_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeClient:
        def user_by_id(self, user_id: str) -> FakeResponse:
            assert user_id == "user-1"
            return FakeResponse({"_id": "user-1", "email": "user@example.test", "isActive": True})

    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_upsert_user(
            {"isActive": False},
            user_id="user-1",
            expected_email="user@example.test",
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is True
    assert result["audit"]["operation"]["kind"] == "user"
    assert result["audit"]["operation"]["risk_level"] == "security"
    assert result["audit"]["operation"]["path"] == "/api/users/user-1"
    assert result["response"]["preflight"]["email"] == "user@example.test"
    assert result["response"]["planned_payload"]["isActive"] is False


def test_upsert_user_execution_requires_dangerous_gate_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeClient:
        def user_by_id(self, user_id: str) -> FakeResponse:
            return FakeResponse({"_id": user_id, "email": "user@example.test"})

    with (
        patch.dict("os.environ", {"ALTERIOS_MCP_ALLOW_WRITE": "1"}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
        pytest.raises(ControlledWriteError, match="ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE"),
    ):
        server.alterios_upsert_user(
            {"isActive": False},
            user_id="user-1",
            dry_run=False,
            allow_destructive=True,
            profile="vniimt",
            project_id="project-1",
        )


def test_delete_user_dry_run_uses_ui_observed_body_delete_path_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeClient:
        def user_by_id(self, user_id: str) -> FakeResponse:
            assert user_id == "user-1"
            return FakeResponse({"_id": "user-1", "email": "user@example.test", "name": "Test User"})

    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_delete_user(
            "user-1",
            expected_email="user@example.test",
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is True
    assert result["audit"]["operation"]["kind"] == "user_delete"
    assert result["audit"]["operation"]["risk_level"] == "security"
    assert result["audit"]["operation"]["method"] == "DELETE"
    assert result["audit"]["operation"]["path"] == "/api/users"
    assert result["audit"]["operation"]["request"]["_id"] == "user-1"
    assert result["response"]["preflight"]["email"] == "user@example.test"


def test_security_upsert_audit_strips_readback_metadata_target_ids_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeClient:
        def user_group_by_id(self, user_group_id: str) -> FakeResponse:
            assert user_group_id == "group-1"
            return FakeResponse(
                {
                    "_id": "group-1",
                    "name": "Sandbox group",
                    "projectId": "project-1",
                    "authorId": "author-1",
                    "updatedBy": {"_id": "updated-by-1"},
                    "users": [],
                }
            )

    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_upsert_user_group(
            {"description": "changed"},
            user_group_id="group-1",
            expected_name="Sandbox group",
            profile="vniimt",
            project_id="project-1",
        )

    assert result["audit"]["operation"]["target_ids"] == ["group-1", "project-1"]
    assert "author-1" not in str(result["audit"])
    assert "updated-by-1" not in str(result["audit"])


def test_delete_role_dry_run_uses_security_delete_path_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeClient:
        def role_by_id(self, role_id: str) -> FakeResponse:
            assert role_id == "role-1"
            return FakeResponse({"_id": "role-1", "name": "Operator"})

    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_delete_role(
            "role-1",
            expected_name="Operator",
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is True
    assert result["audit"]["operation"]["kind"] == "role_delete"
    assert result["audit"]["operation"]["risk_level"] == "security"
    assert result["audit"]["operation"]["method"] == "DELETE"
    assert result["audit"]["operation"]["path"] == "/api/roles/role-1"


def test_form_cell_listener_patch_dry_run_updates_only_target_cell_without_real_network() -> None:
    form = {
        "_id": "form-1",
        "name": "Managed form",
        "description": "Codex-managed form",
        "tabs": [
            {
                "rows": [
                    {
                        "cells": [
                            {"type": "field", "emitting": {"listeners": [{"type": "old"}]}},
                            {"type": "field", "emitting": {"listeners": [{"type": "keep"}]}},
                        ]
                    }
                ]
            }
        ],
    }

    class FakeResponse:
        body = form

    class FakeClient:
        def form_by_id(self, form_id: str) -> FakeResponse:
            assert form_id == "form-1"
            return FakeResponse()

    listeners = [{"type": "manual_script", "scriptId": "script-1", "args": {"openId": True}}]
    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_patch_form_cell_listeners(
            "form-1",
            0,
            0,
            0,
            listeners,
            expected_name="Managed form",
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is True
    assert result["audit"]["operation"]["kind"] == "form_listeners"
    assert result["response"]["before"] == [{"type": "old"}]
    assert result["response"]["after"] == listeners
    patched_tabs = result["response"]["planned_payload"]["tabs"]
    assert patched_tabs[0]["rows"][0]["cells"][0]["emitting"]["listeners"] == listeners
    assert patched_tabs[0]["rows"][0]["cells"][1]["emitting"]["listeners"] == [{"type": "keep"}]


def test_bulk_update_selected_content_fields_dry_run_returns_per_row_diff_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeClient:
        rows = {
            "content-1": {"_id": "content-1", "contentTypeId": "ct-1", "fields": {"status": ["old"]}},
            "content-2": {"_id": "content-2", "contentTypeId": "ct-1", "fields": {"status": ["old"]}},
        }

        def content_by_id(self, content_id: str) -> FakeResponse:
            return FakeResponse(self.rows[content_id])

    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_bulk_update_selected_content_fields(
            ["content-1", "content-2"],
            {"status": "new"},
            expected_count=2,
            expected_content_type_id="ct-1",
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is True
    assert result["audit"]["operation"]["kind"] == "bulk_selection"
    assert result["audit"]["operation"]["target_ids"] == ["content-1", "content-2", "ct-1"]
    assert result["response"]["selected_count"] == 2
    assert result["response"]["rows"][0]["field_diff"] == [
        {"field": "status", "before": ["old"], "after": ["new"], "changed": True}
    ]


def test_content_type_publish_planner_blocks_native_without_ui_har_evidence() -> None:
    class FakeResponse:
        body = {"_id": "ct-1", "name": "Material", "description": "Codex-managed"}

    class FakeClient:
        def content_type_by_id(self, content_type_id: str) -> FakeResponse:
            assert content_type_id == "ct-1"
            return FakeResponse()

    with patch.object(server, "_client", return_value=FakeClient()):
        result = server.alterios_plan_content_type_publish(
            "ct-1",
            ["project-2"],
            profile="vniimt",
            project_id="project-1",
        )

    assert result["native_publish"]["ready"] is False
    assert result["native_publish"]["status"] == "blocked_until_ui_har_evidence"
    assert result["target_project_ids"] == ["project-2"]


def test_clone_shared_content_type_dry_run_uses_native_clone_route_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeClient:
        def list_shared_content_types(self) -> FakeResponse:
            return FakeResponse(
                [
                    {
                        "_id": "ct-source",
                        "name": "Shared material",
                        "projectId": "source-project",
                        "share": True,
                    }
                ]
            )

    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_clone_shared_content_type(
            "ct-source",
            expected_source_name="Shared material",
            profile="vniimt",
            project_id="target-project",
        )

    assert result["dry_run"] is True
    assert result["audit"]["operation"]["kind"] == "content_type_clone"
    assert result["audit"]["operation"]["method"] == "POST"
    assert result["audit"]["operation"]["path"] == "/api/content-types/clone"
    assert result["audit"]["operation"]["request"]["id"] == "ct-source"
    assert result["response"]["source"]["name"] == "Shared material"
    assert result["response"]["source_project_id"] == "source-project"
    assert result["response"]["target_project_id"] == "target-project"


def test_create_material_module_dry_run_stores_plan_without_real_network(tmp_path) -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeClient:
        def list_content_types(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return FakeResponse([[], 0])

        def list_views(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return FakeResponse([[], 0])

        def list_forms(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return FakeResponse([[], 0])

        def list_groups(self) -> FakeResponse:
            return FakeResponse([{"_id": "root", "name": "root", "root": True}])

    with (
        patch.dict("os.environ", {"ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_create_material_module(
            "Материалы",
            "mat",
            [{"name": "Наименование", "mname": "mat_name", "field_type": "text"}],
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is True
    assert result["audit"]["operation"]["kind"] == "scenario_material_module"
    assert result["audit"]["operation"]["path"] == "scenario://material-module"
    assert result["response"]["planned"]["steps"] == [
        "upsert_content_type",
        "upsert_fields",
        "upsert_view",
        "upsert_view_entity",
        "upsert_view_fields",
        "upsert_add_form",
        "upsert_edit_form",
        "upsert_list_form",
        "upsert_group",
        "readback_summary",
    ]
    assert result["response"]["planned"]["fields"][0]["view_mname"] == "name"
    assert result["plan"]["plan_id"].startswith("wp_")
    assert (tmp_path / result["plan"]["path"]).exists()


def test_create_material_module_execution_requires_plan_id_without_real_network() -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeClient:
        def list_content_types(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return FakeResponse([[], 0])

        def list_views(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return FakeResponse([[], 0])

        def list_forms(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return FakeResponse([[], 0])

        def list_groups(self) -> FakeResponse:
            return FakeResponse([{"_id": "root", "name": "root", "root": True}])

    with (
        patch.dict("os.environ", {"ALTERIOS_MCP_ALLOW_WRITE": "1"}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
        pytest.raises(ValueError, match="plan_id is required"),
    ):
        server.alterios_create_material_module(
            "Материалы",
            "mat",
            [{"name": "Наименование", "mname": "mat_name", "field_type": "text"}],
            dry_run=False,
            profile="vniimt",
            project_id="project-1",
        )


def test_create_material_module_execution_rejects_changed_plan_options_without_real_network(tmp_path) -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeClient:
        def list_content_types(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return FakeResponse([[], 0])

        def list_views(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return FakeResponse([[], 0])

        def list_forms(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return FakeResponse([[], 0])

        def list_groups(self) -> FakeResponse:
            return FakeResponse([{"_id": "root", "name": "root", "root": True}])

    fields = [{"name": "Наименование", "mname": "mat_name", "field_type": "text"}]
    with (
        patch.dict("os.environ", {"ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        dry_run = server.alterios_create_material_module(
            "Материалы",
            "mat",
            fields,
            profile="vniimt",
            project_id="project-1",
        )

    with (
        patch.dict(
            "os.environ",
            {"ALTERIOS_MCP_ALLOW_WRITE": "1", "ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)},
            clear=True,
        ),
        patch.object(server, "_client", return_value=FakeClient()),
        pytest.raises(ValueError, match="operation does not match"),
    ):
        server.alterios_create_material_module(
            "Материалы",
            "mat",
            fields,
            icon_id="folder",
            dry_run=False,
            plan_id=dry_run["plan"]["plan_id"],
            profile="vniimt",
            project_id="project-1",
        )


def test_create_material_module_execution_creates_full_surface_without_real_network(tmp_path) -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

        def as_dict(self) -> dict[str, object]:
            return {"status_code": 200, "content_type": "application/json", "body": self.body}

    class FakeMaterialClient:
        def __init__(self) -> None:
            self.content_types: dict[str, dict[str, object]] = {}
            self.fields: dict[str, dict[str, object]] = {}
            self.views: dict[str, dict[str, object]] = {}
            self.view_entities_by_view: dict[str, list[dict[str, object]]] = {}
            self.view_fields_by_view: dict[str, list[dict[str, object]]] = {}
            self.forms: dict[str, dict[str, object]] = {}
            self.groups: dict[str, dict[str, object]] = {"root": {"_id": "root", "name": "root", "root": True}}
            self.next_ids = {
                "ct": 1,
                "field": 1,
                "view": 1,
                "entity": 1,
                "view_field": 1,
                "form": 1,
                "group": 1,
            }

        def _new_id(self, kind: str) -> str:
            value = f"{kind}-{self.next_ids[kind]}"
            self.next_ids[kind] += 1
            return value

        def _listandcount(self, items: list[dict[str, object]]) -> FakeResponse:
            return FakeResponse([items, len(items)])

        def list_content_types(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return self._listandcount(list(self.content_types.values()))

        def content_type_by_id(self, content_type_id: str) -> FakeResponse:
            return FakeResponse(self.content_types[content_type_id])

        def save_content_type(self, payload: dict[str, object]) -> FakeResponse:
            item = dict(payload)
            item.setdefault("_id", self._new_id("ct"))
            self.content_types[str(item["_id"])] = item
            return FakeResponse({"_id": item["_id"], "saved": True})

        def list_fields(
            self,
            *,
            content_type_id: str | None = None,
            field_id: str | None = None,
            limit: int | None = None,
            offset: int | None = None,
        ) -> FakeResponse:
            items = list(self.fields.values())
            if field_id:
                items = [item for item in items if item.get("_id") == field_id]
            if content_type_id:
                items = [item for item in items if item.get("contentTypeId") == content_type_id]
            return FakeResponse(items)

        def field_by_id(self, field_id: str) -> FakeResponse:
            return FakeResponse(self.fields[field_id])

        def save_field(self, payload: dict[str, object]) -> FakeResponse:
            item = dict(payload)
            item.setdefault("_id", self._new_id("field"))
            if str(item.get("mname") or "").startswith("mat_"):
                item["mname"] = f"field_test__{item['mname']}"
            self.fields[str(item["_id"])] = item
            return FakeResponse({"_id": item["_id"], "saved": True})

        def list_views(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return self._listandcount(list(self.views.values()))

        def view_by_id(self, view_id: str) -> FakeResponse:
            return FakeResponse(self.views[view_id])

        def save_view(self, payload: dict[str, object]) -> FakeResponse:
            item = dict(payload)
            item.setdefault("_id", self._new_id("view"))
            self.views[str(item["_id"])] = item
            self.view_entities_by_view.setdefault(str(item["_id"]), [])
            self.view_fields_by_view.setdefault(str(item["_id"]), [])
            return FakeResponse({"_id": item["_id"], "saved": True})

        def view_entities(self, view_id: str) -> FakeResponse:
            return FakeResponse(self.view_entities_by_view.get(view_id, []))

        def save_view_entity(self, payload: dict[str, object]) -> FakeResponse:
            item = dict(payload)
            item.setdefault("_id", self._new_id("entity"))
            view_id = str(item["viewId"])
            entities = self.view_entities_by_view.setdefault(view_id, [])
            entities[:] = [existing for existing in entities if existing.get("_id") != item["_id"]]
            entities.append(item)
            return FakeResponse({"_id": item["_id"], "saved": True})

        def view_fields_populated(self, view_id: str) -> FakeResponse:
            return FakeResponse(self.view_fields_by_view.get(view_id, []))

        def add_view_entity_field(
            self,
            entity_id: str,
            *,
            attribute: str | None = None,
            content_type_field_id: str | None = None,
        ) -> FakeResponse:
            view_id = next(
                view_id
                for view_id, entities in self.view_entities_by_view.items()
                if any(entity.get("_id") == entity_id for entity in entities)
            )
            item: dict[str, object] = {"_id": self._new_id("view_field"), "entityId": entity_id}
            if attribute:
                item.update({"attribute": attribute, "mname": attribute})
            if content_type_field_id:
                field = self.fields[content_type_field_id]
                view_mname = str(field["mname"])
                if view_mname.startswith("field_"):
                    view_mname = view_mname.removeprefix("field_")
                item.update({"contentTypeFieldId": content_type_field_id, "mname": view_mname})
            self.view_fields_by_view.setdefault(view_id, []).append(item)
            return FakeResponse({"_id": item["_id"]})

        def save_view_field(self, payload: dict[str, object]) -> FakeResponse:
            view_field_id = payload["_id"]
            for fields in self.view_fields_by_view.values():
                for index, item in enumerate(fields):
                    if item.get("_id") == view_field_id:
                        fields[index] = {**item, **payload}
                        return FakeResponse({"_id": view_field_id, "saved": True})
            raise KeyError(view_field_id)

        def list_forms(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return self._listandcount(list(self.forms.values()))

        def form_by_id(self, form_id: str) -> FakeResponse:
            return FakeResponse(self.forms[form_id])

        def save_form(self, payload: dict[str, object]) -> FakeResponse:
            item = dict(payload)
            item.setdefault("_id", self._new_id("form"))
            self.forms[str(item["_id"])] = item
            return FakeResponse({"_id": item["_id"], "saved": True})

        def list_groups(self) -> FakeResponse:
            return FakeResponse(list(self.groups.values()))

        def save_group(self, payload: dict[str, object]) -> FakeResponse:
            item = dict(payload)
            item.setdefault("_id", self._new_id("group"))
            self.groups[str(item["_id"])] = item
            return FakeResponse({"_id": item["_id"], "saved": True})

        def request(
            self,
            method: str,
            path: str,
            *,
            params: dict[str, object] | None = None,
            body: object | None = None,
            requires_project: bool = True,
        ) -> FakeResponse:
            assert method == "POST"
            assert path == "/api/views/v2/get-data-simplified"
            assert body == {"viewId": "view-1", "limit": 1, "offset": 0}
            return FakeResponse({"rows": [], "count": 0})

    fields = [
        {"name": "Наименование", "mname": "mat_name", "field_type": "text"},
        {"name": "Количество", "mname": "mat_count", "field_type": "number"},
    ]

    with patch.dict("os.environ", {"ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)}, clear=True):
        dry_run_client = FakeMaterialClient()
        with patch.object(server, "_client", return_value=dry_run_client):
            dry_run = server.alterios_create_material_module(
                "Материалы",
                "mat",
                fields,
                content_name_template="{{mat_name}}",
                profile="vniimt",
                project_id="project-1",
            )

    apply_client = FakeMaterialClient()
    with (
        patch.dict(
            "os.environ",
            {"ALTERIOS_MCP_ALLOW_WRITE": "1", "ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)},
            clear=True,
        ),
        patch.object(server, "_client", return_value=apply_client),
    ):
        result = server.alterios_create_material_module(
            "Материалы",
            "mat",
            fields,
            content_name_template="{{mat_name}}",
            dry_run=False,
            plan_id=dry_run["plan"]["plan_id"],
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is False
    assert result["audit"]["operation"]["kind"] == "scenario_material_module"
    assert result["response"]["ids"]["content_type_id"] == "ct-1"
    assert result["response"]["ids"]["field_ids"] == {
        "field_test__mat_name": "field-1",
        "field_test__mat_count": "field-2",
    }
    assert result["response"]["ids"]["requested_field_ids"] == {"mat_name": "field-1", "mat_count": "field-2"}
    assert result["response"]["ids"]["view_id"] == "view-1"
    assert result["response"]["readback"]["view_data_smoke"]["body"] == {"rows": [], "count": 0}
    assert result["response"]["ids"]["add_form_id"] == "form-1"
    assert result["response"]["ids"]["edit_form_id"] == "form-2"
    assert result["response"]["ids"]["list_form_id"] == "form-3"
    assert result["response"]["ids"]["group_id"] == "group-1"
    assert apply_client.content_types["ct-1"]["contentNameTemplate"] == "{{field_test__mat_name}}"
    assert apply_client.forms["form-1"]["tabs"][0]["rows"][0]["cells"][0]["type"] == "content"
    assert (
        apply_client.forms["form-1"]["tabs"][0]["rows"][0]["cells"][0]["displaying"]["fields"][
            "field_test__mat_name"
        ]["order"]
        == 0
    )
    assert apply_client.forms["form-2"]["tabs"][0]["rows"][0]["cells"][0]["type"] == "view_data"
    assert (
        apply_client.forms["form-2"]["tabs"][0]["rows"][0]["cells"][0]["displaying"]["fields"]["test__mat_name"][
            "order"
        ]
        == 1
    )
    assert apply_client.forms["form-2"]["tabs"][0]["rows"][1]["cells"][0]["type"] == "comments_list"
    list_cell = apply_client.forms["form-3"]["tabs"][0]["rows"][0]["cells"][0]
    assert list_cell["type"] == "view_data_list"
    assert list_cell["displaying"]["fields"]["test__mat_name"]["order"] == 1
    assert list_cell["cellActionContainers"][0]["iconId"] == "add"
    assert list_cell["valueActionContainers"][0]["iconId"] == "edit"
    assert apply_client.groups["group-1"]["formId"] == "form-3"
    assert result["journal"]["event_id"].startswith("wj_")


def test_create_report_tab_dry_run_stores_plan_without_real_network(tmp_path) -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

        def as_dict(self) -> dict[str, object]:
            return {"status_code": 200, "content_type": "application/json", "body": self.body}

    class FakeClient:
        def view_by_id(self, view_id: str) -> FakeResponse:
            return FakeResponse({"_id": view_id, "name": "Материалы. Список", "description": "Codex-managed"})

        def view_fields_populated(self, view_id: str) -> FakeResponse:
            return FakeResponse([{"_id": "vf-1", "mname": "name", "alias": "Наименование", "order": 1, "type": "text"}])

        def form_by_id(self, form_id: str) -> FakeResponse:
            return FakeResponse({"_id": form_id, "name": "Материалы. Карточка", "description": "Codex-managed", "tabs": []})

        def list_reports(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return FakeResponse([[], 0])

        def view_data_simplified(self, view_id: str, *, limit: int = 20, offset: int = 0) -> FakeResponse:
            return FakeResponse({"rows": [{"_id": "content-1", "name": "A"}]})

        def view_data(
            self,
            view_id: str,
            *,
            limit: int = 20,
            offset: int = 0,
            content_id: str | None = None,
            data_id: list[str] | None = None,
            user_filters: dict[str, object] | None = None,
        ) -> FakeResponse:
            rows = [{"_id": data_id[0] if data_id else content_id}] if data_id else [{"_id": "content-1"}, {"_id": "content-2"}]
            return FakeResponse({"rows": rows})

    with (
        patch.dict("os.environ", {"ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_create_report_tab(
            "view-1",
            "form-1",
            "Материалы. Отчет",
            tab_name="Отчет",
            context_content_id="content-1",
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is True
    assert result["audit"]["operation"]["kind"] == "scenario_report_tab"
    database = result["response"]["planned"]["report"]["template"]["Dictionary"]["Databases"]["0"]
    assert database["ServiceName"] == "Project Database"
    assert result["response"]["context_readback"]["validation"]["data_id_matches_expected"] is True
    assert result["response"]["planned"]["form_tabs"][0]["rows"][0]["cells"][0]["params"]["openId"] is True
    assert result["plan"]["plan_id"].startswith("wp_")
    assert (tmp_path / result["plan"]["path"]).exists()


def test_create_report_tab_execution_rejects_changed_plan_options_without_real_network(tmp_path) -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

        def as_dict(self) -> dict[str, object]:
            return {"status_code": 200, "content_type": "application/json", "body": self.body}

    class FakeClient:
        def view_by_id(self, view_id: str) -> FakeResponse:
            return FakeResponse({"_id": view_id, "name": "Материалы. Список", "description": "Codex-managed"})

        def view_fields_populated(self, view_id: str) -> FakeResponse:
            return FakeResponse([{"_id": "vf-1", "mname": "name", "alias": "Наименование", "order": 1}])

        def form_by_id(self, form_id: str) -> FakeResponse:
            return FakeResponse({"_id": form_id, "name": "Материалы. Карточка", "description": "Codex-managed", "tabs": []})

        def list_reports(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return FakeResponse([[], 0])

        def view_data_simplified(self, view_id: str, *, limit: int = 20, offset: int = 0) -> FakeResponse:
            return FakeResponse({"rows": [{"_id": "content-1"}]})

    with (
        patch.dict("os.environ", {"ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        dry_run = server.alterios_create_report_tab(
            "view-1",
            "form-1",
            "Материалы. Отчет",
            tab_name="Отчет",
            profile="vniimt",
            project_id="project-1",
        )

    with (
        patch.dict(
            "os.environ",
            {"ALTERIOS_MCP_ALLOW_WRITE": "1", "ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)},
            clear=True,
        ),
        patch.object(server, "_client", return_value=FakeClient()),
        pytest.raises(ValueError, match="operation does not match"),
    ):
        server.alterios_create_report_tab(
            "view-1",
            "form-1",
            "Материалы. Отчет",
            tab_name="Другой отчет",
            dry_run=False,
            plan_id=dry_run["plan"]["plan_id"],
            profile="vniimt",
            project_id="project-1",
        )


def test_create_report_tab_execution_creates_report_and_form_tab_without_real_network(tmp_path) -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

        def as_dict(self) -> dict[str, object]:
            return {"status_code": 200, "content_type": "application/json", "body": self.body}

    class FakeReportTabClient:
        def __init__(self) -> None:
            self.views = {"view-1": {"_id": "view-1", "name": "Материалы. Список", "description": "Codex-managed"}}
            self.view_fields = [
                {"_id": "vf-1", "mname": "_id", "alias": "ID", "order": 0, "attribute": "_id"},
                {"_id": "vf-2", "mname": "name", "alias": "Наименование", "order": 1, "type": "text"},
                {"_id": "vf-3", "mname": "count", "alias": "Количество", "order": 2, "type": "number"},
            ]
            self.forms = {
                "form-1": {
                    "_id": "form-1",
                    "name": "Материалы. Карточка",
                    "description": "Codex-managed",
                    "tabs": [{"name": None, "rows": []}],
                    "formActionContainers": [],
                }
            }
            self.reports: dict[str, dict[str, object]] = {}

        def view_by_id(self, view_id: str) -> FakeResponse:
            return FakeResponse(self.views[view_id])

        def view_fields_populated(self, view_id: str) -> FakeResponse:
            return FakeResponse(self.view_fields)

        def view_data_simplified(self, view_id: str, *, limit: int = 20, offset: int = 0) -> FakeResponse:
            return FakeResponse({"rows": [{"_id": "content-1", "name": "A"}, {"_id": "content-2", "name": "B"}]})

        def view_data(
            self,
            view_id: str,
            *,
            limit: int = 20,
            offset: int = 0,
            content_id: str | None = None,
            data_id: list[str] | None = None,
            user_filters: dict[str, object] | None = None,
        ) -> FakeResponse:
            if data_id:
                return FakeResponse({"rows": [{"_id": data_id[0], "name": "A"}]})
            return FakeResponse({"rows": [{"_id": "content-1"}, {"_id": "content-2"}]})

        def form_by_id(self, form_id: str) -> FakeResponse:
            return FakeResponse(self.forms[form_id])

        def save_form(self, payload: dict[str, object]) -> FakeResponse:
            item = dict(payload)
            self.forms[str(item["_id"])] = item
            return FakeResponse({"_id": item["_id"], "saved": True})

        def list_reports(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return FakeResponse([list(self.reports.values()), len(self.reports)])

        def report_by_id(self, report_id: str) -> FakeResponse:
            return FakeResponse(self.reports[report_id])

        def save_report(self, payload: dict[str, object]) -> FakeResponse:
            item = dict(payload)
            item.setdefault("_id", "report-1")
            self.reports[str(item["_id"])] = item
            return FakeResponse({"_id": item["_id"], "saved": True})

    with patch.dict("os.environ", {"ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)}, clear=True):
        dry_run_client = FakeReportTabClient()
        with patch.object(server, "_client", return_value=dry_run_client):
            dry_run = server.alterios_create_report_tab(
                "view-1",
                "form-1",
                "Материалы. Отчет",
                tab_name="Отчет",
                context_content_id="content-1",
                profile="vniimt",
                project_id="project-1",
            )

    apply_client = FakeReportTabClient()
    with (
        patch.dict(
            "os.environ",
            {"ALTERIOS_MCP_ALLOW_WRITE": "1", "ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)},
            clear=True,
        ),
        patch.object(server, "_client", return_value=apply_client),
    ):
        result = server.alterios_create_report_tab(
            "view-1",
            "form-1",
            "Материалы. Отчет",
            tab_name="Отчет",
            context_content_id="content-1",
            dry_run=False,
            plan_id=dry_run["plan"]["plan_id"],
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is False
    assert result["audit"]["operation"]["kind"] == "scenario_report_tab"
    assert result["response"]["ids"] == {"report_id": "report-1", "form_id": "form-1", "source_view_id": "view-1"}
    assert apply_client.reports["report-1"]["template"]["Dictionary"]["DataSources"]["0"]["NameInSource"] == "Материалы. Список"
    tab = apply_client.forms["form-1"]["tabs"][1]
    assert tab["name"] == "Отчет"
    cell = tab["rows"][0]["cells"][0]
    assert cell["type"] == "report"
    assert cell["params"] == {"reportId": "report-1", "fullscreenMode": False, "openId": True}
    validation = result["response"]["readback"]["validation"]
    assert validation["report_project_database"]["has_project_database"] is True
    assert validation["report_project_database"]["view_name_matches"] is True
    assert validation["form_tab_open_id"] is True
    assert validation["context"]["data_id_row_count"] == 1
    assert validation["render_evidence"]["status"] == "not_collected"
    assert result["journal"]["event_id"].startswith("wj_")


def test_create_process_flow_dry_run_stores_plan_without_real_network(tmp_path) -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

        def as_dict(self) -> dict[str, object]:
            return {"status_code": 200, "content_type": "application/json", "body": self.body}

    class FakeClient:
        def list_forms(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return FakeResponse([[], 0])

        def list_diagrams(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return FakeResponse([[], 0])

        def script_by_id(self, script_id: str) -> FakeResponse:
            return FakeResponse(
                {
                    "_id": script_id,
                    "name": "РџСЂРѕРІРµСЂРєР° Р·Р°РґР°С‡Рё",
                    "type": "diagram",
                    "active": True,
                    "body": "writeLog({ message: 'ok' })",
                    "description": "Codex-managed",
                }
            )

    with (
        patch.dict("os.environ", {"ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        result = server.alterios_create_process_flow(
            "РџСЂРѕС†РµСЃСЃ РјР°С‚РµСЂРёР°Р»Р°",
            "РџСЂРѕС†РµСЃСЃ РјР°С‚РµСЂРёР°Р»Р°. Р—Р°РґР°С‡Р°",
            content_type_id="ct-1",
            script_refs=[
                {
                    "script_id": "script-1",
                    "type": "diagram",
                    "expected_body_contains": "writeLog",
                }
            ],
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is True
    assert result["audit"]["operation"]["kind"] == "scenario_process_flow"
    assert result["audit"]["operation"]["path"] == "scenario://process-flow"
    assert result["response"]["planned"]["steps"] == [
        "upsert_task_form",
        "validate_script_refs",
        "upsert_bpmn_diagram",
        "readback_form_key",
        "optional_start_process_smoke",
        "optional_complete_task",
    ]
    assert "$task_form_id" in result["response"]["planned"]["diagram"]["bpmn_xml"]
    assert result["response"]["planned"]["task_form"]["surface"]["ok"] is True
    assert result["response"]["preflight"]["scripts"][0]["_id"] == "script-1"
    assert result["plan"]["plan_id"].startswith("wp_")
    assert (tmp_path / result["plan"]["path"]).exists()


def test_create_process_flow_execution_rejects_changed_plan_options_without_real_network(tmp_path) -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

        def as_dict(self) -> dict[str, object]:
            return {"status_code": 200, "content_type": "application/json", "body": self.body}

    class FakeClient:
        def list_forms(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return FakeResponse([[], 0])

        def list_diagrams(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return FakeResponse([[], 0])

    with (
        patch.dict("os.environ", {"ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)}, clear=True),
        patch.object(server, "_client", return_value=FakeClient()),
    ):
        dry_run = server.alterios_create_process_flow(
            "РџСЂРѕС†РµСЃСЃ РјР°С‚РµСЂРёР°Р»Р°",
            "РџСЂРѕС†РµСЃСЃ РјР°С‚РµСЂРёР°Р»Р°. Р—Р°РґР°С‡Р°",
            content_type_id="ct-1",
            profile="vniimt",
            project_id="project-1",
        )

    with (
        patch.dict(
            "os.environ",
            {"ALTERIOS_MCP_ALLOW_WRITE": "1", "ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)},
            clear=True,
        ),
        patch.object(server, "_client", return_value=FakeClient()),
        pytest.raises(ValueError, match="operation does not match"),
    ):
        server.alterios_create_process_flow(
            "РџСЂРѕС†РµСЃСЃ РјР°С‚РµСЂРёР°Р»Р°",
            "РџСЂРѕС†РµСЃСЃ РјР°С‚РµСЂРёР°Р»Р°. Р—Р°РґР°С‡Р°",
            content_type_id="ct-1",
            user_task_name="Changed task",
            dry_run=False,
            plan_id=dry_run["plan"]["plan_id"],
            profile="vniimt",
            project_id="project-1",
        )


def test_create_process_flow_execution_creates_form_diagram_and_starts_process_without_real_network(tmp_path) -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

        def as_dict(self) -> dict[str, object]:
            return {"status_code": 200, "content_type": "application/json", "body": self.body}

    class FakeProcessFlowClient:
        def __init__(self) -> None:
            self.forms: dict[str, dict[str, object]] = {}
            self.diagrams: dict[str, dict[str, object]] = {}
            self.processes: dict[str, dict[str, object]] = {}
            self.tasks: dict[str, dict[str, object]] = {}
            self.content = {"content-1": {"_id": "content-1", "name": "Row", "contentTypeId": "ct-1", "fields": {}}}

        def _listandcount(self, items: list[dict[str, object]]) -> FakeResponse:
            return FakeResponse([items, len(items)])

        def list_forms(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return self._listandcount(list(self.forms.values()))

        def form_by_id(self, form_id: str) -> FakeResponse:
            return FakeResponse(self.forms[form_id])

        def save_form(self, payload: dict[str, object]) -> FakeResponse:
            item = dict(payload)
            item.setdefault("_id", "form-1")
            self.forms[str(item["_id"])] = item
            return FakeResponse({"_id": item["_id"], "saved": True})

        def list_diagrams(self, *, limit: int = 1000, offset: int = 0) -> FakeResponse:
            return self._listandcount(list(self.diagrams.values()))

        def diagram_by_id(self, diagram_id: str) -> FakeResponse:
            return FakeResponse(self.diagrams[diagram_id])

        def save_diagram(self, payload: dict[str, object]) -> FakeResponse:
            item = dict(payload)
            item.setdefault("_id", "diagram-1")
            self.diagrams[str(item["_id"])] = item
            return FakeResponse({"_id": item["_id"], "saved": True})

        def content_by_id(self, content_id: str) -> FakeResponse:
            return FakeResponse(self.content[content_id])

        def list_processes(
            self,
            *,
            diagram_id: str | None = None,
            content_id: str | None = None,
            process_id: str | None = None,
            limit: int = 20,
            offset: int = 0,
        ) -> FakeResponse:
            items = list(self.processes.values())
            if process_id:
                items = [item for item in items if item.get("_id") == process_id]
            if diagram_id:
                items = [item for item in items if item.get("diagramId") == diagram_id]
            if content_id:
                items = [item for item in items if item.get("contentId") == content_id]
            return self._listandcount(items)

        def list_tasks(
            self,
            *,
            diagram_id: str | None = None,
            content_id: str | None = None,
            process_id: str | None = None,
            task_id: str | None = None,
        ) -> FakeResponse:
            items = list(self.tasks.values())
            if task_id:
                items = [item for item in items if item.get("_id") == task_id]
            if process_id:
                items = [item for item in items if item.get("processId") == process_id]
            if diagram_id:
                items = [item for item in items if item.get("diagramId") == diagram_id]
            if content_id:
                items = [item for item in items if item.get("contentId") == content_id]
            return FakeResponse(items)

        def start_process(
            self,
            diagram_id: str,
            *,
            content_id: str | None = None,
            params: dict[str, object] | None = None,
            name: str | None = None,
            start_message_id: str | None = None,
            response_message_id: str | None = None,
            contents: list[dict[str, object]] | None = None,
        ) -> FakeResponse:
            self.processes["process-1"] = {
                "_id": "process-1",
                "diagramId": diagram_id,
                "contentId": content_id,
                "completed": False,
            }
            self.tasks["task-1"] = {
                "_id": "task-1",
                "name": "Review",
                "processId": "process-1",
                "diagramId": diagram_id,
                "contentId": content_id,
                "formId": "form-1",
            }
            return FakeResponse({"processId": "process-1"})

    with patch.dict("os.environ", {"ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)}, clear=True):
        dry_run_client = FakeProcessFlowClient()
        with patch.object(server, "_client", return_value=dry_run_client):
            dry_run = server.alterios_create_process_flow(
                "РџСЂРѕС†РµСЃСЃ РјР°С‚РµСЂРёР°Р»Р°",
                "РџСЂРѕС†РµСЃСЃ РјР°С‚РµСЂРёР°Р»Р°. Р—Р°РґР°С‡Р°",
                content_type_id="ct-1",
                user_task_name="Review",
                content_id="content-1",
                profile="vniimt",
                project_id="project-1",
            )

    apply_client = FakeProcessFlowClient()
    with (
        patch.dict(
            "os.environ",
            {"ALTERIOS_MCP_ALLOW_WRITE": "1", "ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)},
            clear=True,
        ),
        patch.object(server, "_client", return_value=apply_client),
    ):
        result = server.alterios_create_process_flow(
            "РџСЂРѕС†РµСЃСЃ РјР°С‚РµСЂРёР°Р»Р°",
            "РџСЂРѕС†РµСЃСЃ РјР°С‚РµСЂРёР°Р»Р°. Р—Р°РґР°С‡Р°",
            content_type_id="ct-1",
            user_task_name="Review",
            content_id="content-1",
            dry_run=False,
            plan_id=dry_run["plan"]["plan_id"],
            profile="vniimt",
            project_id="project-1",
        )

    assert result["dry_run"] is False
    assert result["audit"]["operation"]["kind"] == "scenario_process_flow"
    assert result["audit"]["operation"]["risk_level"] == "workflow_side_effect"
    assert result["response"]["ids"] == {
        "task_form_id": "form-1",
        "diagram_id": "diagram-1",
        "content_type_id": "ct-1",
        "content_id": "content-1",
    }
    assert apply_client.forms["form-1"]["tabs"][0]["rows"][0]["cells"][0]["type"] == "html"
    assert 'formKey="form-1"' in str(apply_client.diagrams["diagram-1"]["value"])
    assert result["response"]["process_smoke"]["status"] == "started"
    assert result["response"]["process_smoke"]["process_id"] == "process-1"
    assert result["response"]["process_smoke"]["validation"]["task_count_matches"] is True
    assert result["response"]["process_smoke"]["validation"]["task_form_matches"] is True
    assert result["journal"]["event_id"].startswith("wj_")
