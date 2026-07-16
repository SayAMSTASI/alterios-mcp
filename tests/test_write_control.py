from __future__ import annotations

import json
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


DELIVERY_EVIDENCE = {
    "work_item_ref": "gitea:#2",
    "agent_handoff_refs": ["gitea:#2/comment/analyst"],
    "ux_contract_version": server.UX_CONTRACT_VERSION,
}


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
            profile="primary",
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
                "emailConfirmationCode": "email-code",
                "clientSecret": "client-secret",
                "name": "demo",
            }
        },
    )

    audit = build_write_audit(
        profile="primary",
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
    assert audit["operation"]["request"]["body"]["emailConfirmationCode"] == "<redacted>"
    assert audit["operation"]["request"]["body"]["clientSecret"] == "<redacted>"
    assert audit["operation"]["request"]["body"]["name"] == "demo"
    assert redact_sensitive({"planned_payload": {"repassword": "secret-password"}}) == {
        "planned_payload": {"repassword": "<redacted>"}
    }
    assert redact_sensitive({"readback": {"author": {"emailConfirmationCode": "email-code"}}}) == {
        "readback": {"author": {"emailConfirmationCode": "<redacted>"}}
    }
    assert redact_sensitive(
        {
            "readback": {
                "author": {"email": "person@example.test"},
                "authorName": "Person Name",
                "contentType": {
                    "projectName": "Business Project",
                    "project": {"participantsIds": ["user-1"], "telegramSupportGroupIds": ["group-1"]},
                },
            }
        }
    ) == {
        "readback": {
            "author": {"email": "<redacted>"},
            "authorName": "<redacted>",
            "contentType": {
                "projectName": "<redacted>",
                "project": "<redacted>",
            },
        }
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
            profile="primary",
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
            profile="primary",
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
            profile="primary",
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
            profile="primary",
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
            profile="primary",
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
            profile="primary",
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
            profile="primary",
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
            profile="primary",
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
            profile="primary",
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
            profile="primary",
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
            profile="primary",
…28115 tokens truncated…,
        pytest.raises(ValueError, match="plan_id is required"),
    ):
        server.alterios_ensure_project_icons(
            icon_specs=[{"semantic": "save", "google_name": "save"}],
            include_defaults=False,
            dry_run=False,
            profile="secondary",
            project_id="project-1",
        )


def test_ensure_project_icons_execution_uploads_and_writes_registry(tmp_path) -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

        def as_dict(self) -> dict[str, object]:
            return {"status_code": 200, "content_type": "application/json", "body": self.body}

    class FakeIconClient:
        def __init__(self) -> None:
            self.uploads: list[dict[str, object]] = []

        def upload_icon(self, data: bytes, *, filename: str) -> FakeResponse:
            self.uploads.append({"data": data, "filename": filename})
            return FakeResponse({"_id": "11111111-1111-4111-8111-111111111111", "filename": filename})

        def file_metadata(self, file_ids: list[str]) -> FakeResponse:
            return FakeResponse([{"_id": file_ids[0], "filename": "icon.svg"}])

    fake_client = FakeIconClient()
    with patch.dict("os.environ", {"ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)}, clear=True):
        dry_run = server.alterios_ensure_project_icons(
            icon_specs=[{"semantic": "save", "google_name": "save"}],
            include_defaults=False,
            profile="secondary",
            project_id="project-1",
        )

    with (
        patch.dict(
            "os.environ",
            {"ALTERIOS_MCP_ALLOW_WRITE": "1", "ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)},
            clear=True,
        ),
        patch.object(server, "_client", return_value=fake_client),
        patch.object(server, "_download_google_icon_svg", return_value=b"<svg></svg>"),
    ):
        result = server.alterios_ensure_project_icons(
            icon_specs=[{"semantic": "save", "google_name": "save"}],
            include_defaults=False,
            dry_run=False,
            plan_id=dry_run["plan"]["plan_id"],
            profile="secondary",
            project_id="project-1",
        )

    assert result["dry_run"] is False
    assert result["response"]["icon_ids"]["save"] == "11111111-1111-4111-8111-111111111111"
    assert fake_client.uploads == [
        {"data": b"<svg></svg>", "filename": "codex_icon_save_save_16dp_4B77D1.svg"}
    ]
    registry_path = tmp_path / result["response"]["registry"]["path"]
    assert registry_path.exists()
    assert "11111111-1111-4111-8111-111111111111" in registry_path.read_text(encoding="utf-8")


def test_list_project_icons_reads_filesystem_and_writes_artifact(tmp_path) -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

        def as_dict(self) -> dict[str, object]:
            return {"status_code": 200, "content_type": "application/json", "body": self.body}

    class FakeIconFilesClient:
        def __init__(self, _config: object) -> None:
            pass

        def file_elfinder(self, *, command: str = "open", target: str | None = None, extra: dict[str, object] | None = None) -> FakeResponse:
            assert command == "open"
            if target == "public_root":
                return FakeResponse(
                    {
                        "files": [
                            {"hash": "icons_hash", "name": "icons", "mime": "directory", "phash": "public_root"},
                        ]
                    }
                )
            if target == "icons_hash":
                return FakeResponse(
                    {
                        "cwd": {"hash": "icons_hash", "name": "icons", "mime": "directory"},
                        "files": [
                            {
                                "hash": "add_hash",
                                "id": "file-add",
                                "name": "add_24dp_4B77D1_FILL0_wght400_GRAD0_opsz24.svg",
                                "mime": "image/svg+xml",
                                "phash": "icons_hash",
                                "size": 182,
                                "url": "/files/icons/add.svg",
                            },
                            {
                                "hash": "doc_hash",
                                "id": "file-doc",
                                "name": "description.png",
                                "mime": "image/png",
                                "phash": "icons_hash",
                                "size": 177,
                                "url": "/files/icons/description.png",
                            },
                        ],
                    }
                )
            raise AssertionError(f"Unexpected target {target!r}")

        def file_metadata(self, file_ids: list[str]) -> FakeResponse:
            return FakeResponse([{"_id": file_ids[0]}])

    env = {
        "ALTERIOS_SECONDARY_BASE_URL": "https://alterios.example",
        "ALTERIOS_SECONDARY_API_TOKEN": "secret",
        "ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path),
    }
    with patch.dict("os.environ", env, clear=True), patch.object(server, "AlteriosClient", FakeIconFilesClient):
        result = server.alterios_list_project_icons(
            folder_hash="#elf_public_root",
            icons_folder_name="icons",
            profile="secondary",
            project_id="project-1",
        )

    assert result["filesystem"]["icon_count"] == 2
    assert result["filesystem"]["catalog"][0]["semantic"] == "add"
    artifact_path = tmp_path / result["filesystem"]["artifact"]
    assert artifact_path.exists()


def test_resolve_project_icon_registers_existing_filesystem_match(tmp_path) -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeIconFilesClient:
        def __init__(self, _config: object) -> None:
            pass

        def file_elfinder(self, *, command: str = "open", target: str | None = None, extra: dict[str, object] | None = None) -> FakeResponse:
            if target == "public_root":
                return FakeResponse(
                    {"files": [{"hash": "icons_hash", "name": "icons", "mime": "directory", "phash": "public_root"}]}
                )
            if target == "icons_hash":
                return FakeResponse(
                    {
                        "files": [
                            {
                                "hash": "add_hash",
                                "id": "file-add",
                                "name": "add_24dp_4B77D1_FILL0_wght400_GRAD0_opsz24.svg",
                                "mime": "image/svg+xml",
                                "phash": "icons_hash",
                            }
                        ]
                    }
                )
            raise AssertionError(f"Unexpected target {target!r}")

        def file_metadata(self, file_ids: list[str]) -> FakeResponse:
            return FakeResponse([{"_id": file_ids[0]}])

    env = {
        "ALTERIOS_SECONDARY_BASE_URL": "https://alterios.example",
        "ALTERIOS_SECONDARY_API_TOKEN": "secret",
        "ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path),
    }
    with patch.dict("os.environ", env, clear=True), patch.object(server, "AlteriosClient", FakeIconFilesClient):
        result = server.alterios_resolve_project_icon(
            semantic="add",
            folder_hash="public_root",
            icons_folder_name="icons",
            allow_upload=False,
            profile="secondary",
            project_id="project-1",
        )

    assert result["resolved"] is True
    assert result["source"] == "filesystem"
    assert result["icon_id"] == "file-add"
    registry_path = tmp_path / "project-icons" / "secondary" / "project-1" / "registry.json"
    registry = registry_path.read_text(encoding="utf-8")
    assert "file-add" in registry
    assert "project_file_manager" in registry


def test_export_project_icons_downloads_files_and_usage_guide(tmp_path) -> None:
    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeIconFilesClient:
        def __init__(self, _config: object) -> None:
            pass

        def file_elfinder(self, *, command: str = "open", target: str | None = None, extra: dict[str, object] | None = None) -> FakeResponse:
            if target == "public_root":
                return FakeResponse(
                    {"files": [{"hash": "icons_hash", "name": "icons", "mime": "directory", "phash": "public_root"}]}
                )
            if target == "icons_hash":
                return FakeResponse(
                    {
                        "files": [
                            {
                                "hash": "print_hash",
                                "id": "file-print",
                                "name": "print_24dp_4B77D1_FILL0_wght400_GRAD0_opsz24.svg",
                                "mime": "image/svg+xml",
                                "phash": "icons_hash",
                            }
                        ]
                    }
                )
            raise AssertionError(f"Unexpected target {target!r}")

        def download_file(self, file_id: str) -> tuple[bytes, str]:
            assert file_id == "file-print"
            return b"<svg></svg>", "image/svg+xml"

    env = {
        "ALTERIOS_SECONDARY_BASE_URL": "https://alterios.example",
        "ALTERIOS_SECONDARY_API_TOKEN": "secret",
        "ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path),
    }
    with patch.dict("os.environ", env, clear=True), patch.object(server, "AlteriosClient", FakeIconFilesClient):
        result = server.alterios_export_project_icons(
            folder_hash="public_root",
            icons_folder_name="icons",
            profile="secondary",
            project_id="project-1",
        )

    assert result["icon_count"] == 1
    manifest = tmp_path / result["artifacts"]["manifest"]
    guide = tmp_path / result["artifacts"]["usage_guide"]
    assert manifest.exists()
    assert guide.exists()
    assert "Печать формы" in guide.read_text(encoding="utf-8")
    downloaded = list((tmp_path / result["artifacts"]["files_dir"]).glob("file-print_*.svg"))
    assert len(downloaded) == 1


def test_export_project_icons_defaults_to_selected_folder_only(tmp_path) -> None:
    opened_targets: list[str | None] = []

    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeIconFilesClient:
        def __init__(self, _config: object) -> None:
            pass

        def file_elfinder(self, *, command: str = "open", target: str | None = None, extra: dict[str, object] | None = None) -> FakeResponse:
            opened_targets.append(target)
            if target == "public_root":
                return FakeResponse(
                    {
                        "files": [
                            {"hash": "icons_hash", "name": "icons", "mime": "directory", "phash": "public_root"},
                            {
                                "hash": "save_hash",
                                "id": "file-save",
                                "name": "save_16dp.svg",
                                "mime": "image/svg+xml",
                                "phash": "public_root",
                            },
                        ]
                    }
                )
            if target == "icons_hash":
                return FakeResponse(
                    {
                        "files": [
                            {
                                "hash": "print_hash",
                                "id": "file-print",
                                "name": "print_16dp.svg",
                                "mime": "image/svg+xml",
                                "phash": "icons_hash",
                            }
                        ]
                    }
                )
            raise AssertionError(f"Unexpected target {target!r}")

        def download_file(self, file_id: str) -> tuple[bytes, str]:
            return b"<svg></svg>", "image/svg+xml"

    env = {
        "ALTERIOS_SECONDARY_BASE_URL": "https://alterios.example",
        "ALTERIOS_SECONDARY_API_TOKEN": "secret",
        "ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path),
    }
    with patch.dict("os.environ", env, clear=True), patch.object(server, "AlteriosClient", FakeIconFilesClient):
        result = server.alterios_export_project_icons(
            folder_hash="public_root",
            profile="secondary",
            project_id="project-1",
        )

    assert result["icon_count"] == 1
    assert opened_targets == ["public_root", "public_root"]
    manifest = tmp_path / result["artifacts"]["manifest"]
    assert "file-save" in manifest.read_text(encoding="utf-8")
    assert "file-print" not in manifest.read_text(encoding="utf-8")


def test_ensure_project_icon_library_dry_run_inventories_before_upload(tmp_path) -> None:
    library_dir = tmp_path / "library"
    library_dir.mkdir()
    (library_dir / "save_16dp.svg").write_text('<svg viewBox="0 0 16 16"></svg>', encoding="utf-8")
    (library_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "icons": [{"semantic": "save", "filename": "save_16dp.svg", "mime": "image/svg+xml"}],
            }
        ),
        encoding="utf-8",
    )

    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

    class FakeIconLibraryClient:
        def __init__(self, _config: object) -> None:
            pass

        def file_elfinder(self, *, command: str = "open", target: str | None = None, extra: dict[str, object] | None = None) -> FakeResponse:
            assert target == "public_L3B1YmxpYw"
            return FakeResponse({"cwd": {"hash": target, "name": "public", "mime": "directory"}, "files": []})

        def file_metadata(self, file_ids: list[str]) -> FakeResponse:
            return FakeResponse([])

    env = {
        "ALTERIOS_SECONDARY_BASE_URL": "https://alterios.example",
        "ALTERIOS_SECONDARY_API_TOKEN": "secret",
        "ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path / "artifacts"),
    }
    with patch.dict("os.environ", env, clear=True), patch.object(server, "AlteriosClient", FakeIconLibraryClient):
        result = server.alterios_ensure_project_icon_library(
            semantics=["save"],
            library_dir=str(library_dir),
            profile="secondary",
            project_id="project-1",
        )

    assert result["dry_run"] is True
    assert result["response"]["principle"]["analyze_project_before_upload"] is True
    assert result["response"]["inventory"]["filesystem_icon_count"] == 0
    assert result["response"]["icons"][0]["planned_action"] == "upload_library_icon"
    assert result["plan"]["plan_id"].startswith("wp_")


def test_ensure_project_icon_library_execution_uploads_missing_and_writes_registry(tmp_path) -> None:
    library_dir = tmp_path / "library"
    library_dir.mkdir()
    icon_data = b'<svg viewBox="0 0 16 16"></svg>'
    (library_dir / "save_16dp.svg").write_bytes(icon_data)
    (library_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "icons": [{"semantic": "save", "filename": "save_16dp.svg", "mime": "image/svg+xml"}],
            }
        ),
        encoding="utf-8",
    )

    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = body

        def as_dict(self) -> dict[str, object]:
            return {"status_code": 200, "content_type": "application/json", "body": self.body}

    class FakeIconLibraryClient:
        uploads: list[dict[str, object]] = []

        def __init__(self, _config: object) -> None:
            pass

        def file_elfinder(self, *, command: str = "open", target: str | None = None, extra: dict[str, object] | None = None) -> FakeResponse:
            return FakeResponse({"cwd": {"hash": target, "name": "public", "mime": "directory"}, "files": []})

        def file_metadata(self, file_ids: list[str]) -> FakeResponse:
            return FakeResponse([{"_id": file_ids[0], "filename": "save_16dp.svg"}])

        def upload_icon(self, data: bytes, *, filename: str, mime_type: str | None = None) -> FakeResponse:
            self.uploads.append({"data": data, "filename": filename, "mime_type": mime_type})
            return FakeResponse({"_id": "22222222-2222-4222-8222-222222222222", "filename": filename})

    artifacts_dir = tmp_path / "artifacts"
    env = {
        "ALTERIOS_SECONDARY_BASE_URL": "https://alterios.example",
        "ALTERIOS_SECONDARY_API_TOKEN": "secret",
        "ALTERIOS_MCP_ARTIFACTS_DIR": str(artifacts_dir),
    }
    with patch.dict("os.environ", env, clear=True), patch.object(server, "AlteriosClient", FakeIconLibraryClient):
        dry_run = server.alterios_ensure_project_icon_library(
            semantics=["save"],
            library_dir=str(library_dir),
            profile="secondary",
            project_id="project-1",
        )

    with (
        patch.dict("os.environ", {**env, "ALTERIOS_MCP_ALLOW_WRITE": "1"}, clear=True),
        patch.object(server, "AlteriosClient", FakeIconLibraryClient),
    ):
        result = server.alterios_ensure_project_icon_library(
            semantics=["save"],
            library_dir=str(library_dir),
            dry_run=False,
            plan_id=dry_run["plan"]["plan_id"],
            profile="secondary",
            project_id="project-1",
        )

    assert result["dry_run"] is False
    assert result["response"]["icon_ids"]["save"] == "22222222-2222-4222-8222-222222222222"
    assert FakeIconLibraryClient.uploads == [
        {"data": icon_data, "filename": "save_16dp.svg", "mime_type": "image/svg+xml"}
    ]
    registry_path = artifacts_dir / result["response"]["inventory"]["registry"]["path"]
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert registry["icons"]["save"]["source"] == "repo_icon_library"
    assert registry["icons"]["save"]["file_id"] == "22222222-2222-4222-8222-222222222222"
