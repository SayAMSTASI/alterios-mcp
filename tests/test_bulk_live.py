from __future__ import annotations

import pytest

from alterios_mcp.bulk_live import (
    execute_bulk_delete,
    execute_bulk_manual_script,
    execute_bulk_process_start,
    load_bulk_content_targets,
    normalize_bulk_ids,
)


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def as_dict(self):
        return {"status_code": 200, "body": self.body}


class FakeClient:
    def __init__(self) -> None:
        self.deleted: set[str] = set()
        self.manual_calls: list[tuple[str, dict]] = []
        self.process_calls: list[tuple[str, dict]] = []

    def content_by_id(self, content_id: str) -> FakeResponse:
        return FakeResponse({"_id": content_id, "name": f"Row {content_id}", "contentTypeId": "type-1"})

    def execute_manual_script(self, script_id: str, args: dict) -> FakeResponse:
        self.manual_calls.append((script_id, args))
        return FakeResponse({"ok": True, "contentId": args["contentId"]})

    def start_process(self, diagram_id: str, **kwargs) -> FakeResponse:
        self.process_calls.append((diagram_id, kwargs))
        return FakeResponse({"processId": f"process-{kwargs['content_id']}"})

    def list_processes(self, **kwargs) -> FakeResponse:
        return FakeResponse({"items": [{"_id": kwargs.get("process_id"), "contentId": kwargs.get("content_id")}]})

    def list_tasks(self, **kwargs) -> FakeResponse:
        return FakeResponse({"items": [{"_id": f"task-{kwargs.get('content_id')}"}]})

    def call_script_service(self, function: str, args: dict, *, allow_write: bool = False) -> FakeResponse:
        assert function == "deleteManyContents"
        assert allow_write is True
        self.deleted.update(args["_id"])
        return FakeResponse({"deleted": len(args["_id"])})

    def request(self, method: str, path: str, **kwargs) -> FakeResponse:
        content_id = kwargs["params"]["_id"]
        return FakeResponse({"items": [] if content_id in self.deleted else [{"_id": content_id}]})


class EmptyProcessReadbackClient(FakeClient):
    def start_process(self, diagram_id: str, **kwargs) -> FakeResponse:
        self.process_calls.append((diagram_id, kwargs))
        return FakeResponse({})

    def list_processes(self, **kwargs) -> FakeResponse:
        return FakeResponse({"items": []})

    def list_tasks(self, **kwargs) -> FakeResponse:
        return FakeResponse({"items": []})


def test_normalize_bulk_ids_enforces_count_duplicates_and_limit() -> None:
    assert normalize_bulk_ids([" a ", "b"], expected_count=2, max_count=2) == ["a", "b"]
    with pytest.raises(ValueError, match="duplicates"):
        normalize_bulk_ids(["a", "a"], expected_count=2, max_count=2)
    with pytest.raises(ValueError, match="expected_count mismatch"):
        normalize_bulk_ids(["a"], expected_count=2, max_count=2)
    with pytest.raises(ValueError, match="Refusing to process"):
        normalize_bulk_ids(["a", "b"], expected_count=2, max_count=1)


def test_bulk_helpers_execute_manual_process_and_delete_with_readback() -> None:
    client = FakeClient()
    targets = load_bulk_content_targets(client, ["a", "b"], expected_content_type_id="type-1")
    manual = execute_bulk_manual_script(
        client,
        script_id="script-1",
        content_ids=["a", "b"],
        shared_args={"mode": "bulk"},
        content_arg_name="contentId",
        readback_content=True,
        stop_on_error=True,
    )
    processes = execute_bulk_process_start(
        client,
        diagram_id="diagram-1",
        content_ids=["a", "b"],
        params={"mode": "bulk"},
        name="Bulk process",
        stop_on_error=True,
    )
    deleted = execute_bulk_delete(client, content_ids=["a", "b"])

    assert len(targets) == 2
    assert manual["ok"] is True
    assert [call[1]["contentId"] for call in client.manual_calls] == ["a", "b"]
    assert processes["ok"] is True
    assert [row["process_id"] for row in processes["rows"]] == ["process-a", "process-b"]
    assert deleted["ok"] is True
    assert deleted["deleted_count"] == 2


def test_load_bulk_targets_blocks_content_type_mismatch() -> None:
    with pytest.raises(ValueError, match="type mismatch"):
        load_bulk_content_targets(FakeClient(), ["a"], expected_content_type_id="type-2")


def test_bulk_process_rejects_empty_process_id_and_readback() -> None:
    result = execute_bulk_process_start(
        EmptyProcessReadbackClient(),
        diagram_id="diagram-1",
        content_ids=["a"],
        params={"mode": "bulk"},
        name="Bulk process",
        stop_on_error=True,
    )

    assert result["ok"] is False
    assert result["failed_count"] == 1
    assert result["rows"][0]["ok"] is False
    assert "process id" in result["rows"][0]["error"]["message"]
