from __future__ import annotations

import inspect
from unittest.mock import patch

import pytest

from alterios_mcp import server
from alterios_mcp.write_control import ControlledWriteError


SCRIPT_ID = "11111111-1111-4111-8111-111111111111"
DELIVERY_EVIDENCE = {
    "work_item_ref": "gitea:#10",
    "agent_handoff_refs": ["gitea:#10/comment/1"],
    "ux_contract_version": server.UX_CONTRACT_VERSION,
}
READY_PREFLIGHT = {
    "summary": {"ok": True, "status": "ready"},
    "checks": [{"name": "runtime_freshness", "fingerprint": "runtime-1"}],
}


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def as_dict(self):
        return {"status_code": 200, "body": self.body}


class FakeClient:
    def __init__(self) -> None:
        self.deleted: set[str] = set()
        self.manual_calls: list[dict] = []
        self.process_calls: list[dict] = []
        self.script_value = "return true;"

    def script_by_id(self, script_id: str) -> FakeResponse:
        return FakeResponse(
            {
                "_id": script_id,
                "name": "Bulk script",
                "type": "manual",
                "active": True,
                "value": self.script_value,
            }
        )

    def diagram_by_id(self, diagram_id: str) -> FakeResponse:
        return FakeResponse({"_id": diagram_id, "name": "Bulk process"})

    def content_by_id(self, content_id: str) -> FakeResponse:
        return FakeResponse({"_id": content_id, "name": f"Row {content_id}", "contentTypeId": "type-1"})

    def execute_manual_script(self, script_id: str, args: dict) -> FakeResponse:
        self.manual_calls.append(args)
        return FakeResponse({"ok": True})

    def start_process(self, diagram_id: str, **kwargs) -> FakeResponse:
        self.process_calls.append(kwargs)
        return FakeResponse({"processId": f"process-{kwargs['content_id']}"})

    def list_processes(self, **kwargs) -> FakeResponse:
        return FakeResponse({"items": [{"_id": kwargs.get("process_id")}]})

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


@pytest.fixture(autouse=True)
def _fast_preflight(monkeypatch):
    monkeypatch.setattr(server, "run_live_task_preflight", lambda **kwargs: READY_PREFLIGHT)
    monkeypatch.setattr(server, "_assert_runtime_gate", lambda expected=None: {"fingerprint": expected})
    monkeypatch.setattr(
        server,
        "_assert_delivery_evidence",
        lambda evidence: {"ok": True, "work_item_ref": evidence["work_item_ref"]},
    )


def test_fast_bulk_manual_script_plan_and_apply_use_same_selected_ids(tmp_path, monkeypatch) -> None:
    client = FakeClient()
    monkeypatch.setattr(server, "_client", lambda profile, project_id: client)
    env = {
        "ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path),
        "ALTERIOS_MCP_ALLOW_WRITE": "1",
    }
    kwargs = {
        "script_id": SCRIPT_ID,
        "selected_content_ids": ["content-1", "content-2"],
        "delivery_evidence": DELIVERY_EVIDENCE,
        "profile": "primary",
        "project_id": "project-1",
        "shared_args": {"mode": "bulk"},
        "expected_count": 2,
        "expected_content_type_id": "type-1",
    }

    with patch.dict("os.environ", env, clear=False):
        planned = server.alterios_fast_live_bulk_manual_script(**kwargs)
        applied = server.alterios_fast_live_bulk_manual_script(
            **kwargs,
            dry_run=False,
            plan_id=planned["plan"]["plan_id"],
        )

    assert planned["status"] == "planned"
    assert applied["status"] == "applied"
    assert applied["response"]["execution"]["succeeded_count"] == 2
    assert [item["contentId"] for item in client.manual_calls] == ["content-1", "content-2"]


def test_fast_bulk_manual_script_rejects_changed_target_list_for_reviewed_plan(tmp_path, monkeypatch) -> None:
    client = FakeClient()
    monkeypatch.setattr(server, "_client", lambda profile, project_id: client)
    env = {
        "ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path),
        "ALTERIOS_MCP_ALLOW_WRITE": "1",
    }
    base = {
        "script_id": SCRIPT_ID,
        "selected_content_ids": ["content-1", "content-2"],
        "delivery_evidence": DELIVERY_EVIDENCE,
        "profile": "primary",
        "project_id": "project-1",
        "expected_count": 2,
        "expected_content_type_id": "type-1",
    }

    with patch.dict("os.environ", env, clear=False):
        planned = server.alterios_fast_live_bulk_manual_script(**base)
        with pytest.raises(ValueError, match="operation does not match"):
            server.alterios_fast_live_bulk_manual_script(
                **{**base, "selected_content_ids": ["content-1", "content-3"]},
                dry_run=False,
                plan_id=planned["plan"]["plan_id"],
            )

    assert client.manual_calls == []


def test_fast_bulk_manual_script_rejects_script_changed_after_plan(tmp_path, monkeypatch) -> None:
    client = FakeClient()
    monkeypatch.setattr(server, "_client", lambda profile, project_id: client)
    env = {
        "ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path),
        "ALTERIOS_MCP_ALLOW_WRITE": "1",
    }
    kwargs = {
        "script_id": SCRIPT_ID,
        "selected_content_ids": ["content-1"],
        "delivery_evidence": DELIVERY_EVIDENCE,
        "profile": "primary",
        "project_id": "project-1",
        "expected_count": 1,
        "expected_content_type_id": "type-1",
    }

    with patch.dict("os.environ", env, clear=False):
        planned = server.alterios_fast_live_bulk_manual_script(**kwargs)
        client.script_value = "return false;"
        with pytest.raises(ValueError, match="operation does not match"):
            server.alterios_fast_live_bulk_manual_script(
                **kwargs,
                dry_run=False,
                plan_id=planned["plan"]["plan_id"],
            )

    assert client.manual_calls == []


def test_fast_bulk_process_plan_contains_diagram_and_targets(tmp_path, monkeypatch) -> None:
    client = FakeClient()
    monkeypatch.setattr(server, "_client", lambda profile, project_id: client)
    with patch.dict("os.environ", {"ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path)}, clear=False):
        result = server.alterios_fast_live_bulk_process(
            diagram_id="diagram-1",
            selected_content_ids=["content-1", "content-2"],
            delivery_evidence=DELIVERY_EVIDENCE,
            profile="primary",
            project_id="project-1",
            expected_count=2,
            expected_content_type_id="type-1",
        )

    assert result["status"] == "planned"
    assert result["response"]["diagram"]["_id"] == "diagram-1"
    assert result["response"]["selected_count"] == 2


def test_fast_bulk_manual_and_process_require_expected_count_and_content_type() -> None:
    for tool in (
        server.alterios_fast_live_bulk_manual_script,
        server.alterios_fast_live_bulk_process,
    ):
        parameters = inspect.signature(tool).parameters
        assert parameters["expected_count"].default is inspect.Parameter.empty
        assert parameters["expected_content_type_id"].default is inspect.Parameter.empty


def test_fast_bulk_delete_requires_dangerous_gate_and_verifies_absence(tmp_path, monkeypatch) -> None:
    client = FakeClient()
    monkeypatch.setattr(server, "_client", lambda profile, project_id: client)
    kwargs = {
        "selected_content_ids": ["content-1", "content-2"],
        "expected_count": 2,
        "expected_content_type_id": "type-1",
        "delivery_evidence": DELIVERY_EVIDENCE,
        "profile": "primary",
        "project_id": "project-1",
    }
    base_env = {
        "ALTERIOS_MCP_ARTIFACTS_DIR": str(tmp_path),
        "ALTERIOS_MCP_ALLOW_WRITE": "1",
    }

    with patch.dict("os.environ", base_env, clear=False):
        planned = server.alterios_fast_live_bulk_delete(**kwargs)
        with pytest.raises(ControlledWriteError, match="ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE"):
            server.alterios_fast_live_bulk_delete(
                **kwargs,
                dry_run=False,
                plan_id=planned["plan"]["plan_id"],
                allow_destructive=True,
            )

    dangerous_env = {**base_env, "ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE": "1"}
    with patch.dict("os.environ", dangerous_env, clear=False):
        applied = server.alterios_fast_live_bulk_delete(
            **kwargs,
            dry_run=False,
            plan_id=planned["plan"]["plan_id"],
            allow_destructive=True,
        )

    assert applied["status"] == "applied"
    assert applied["response"]["execution"]["deleted_count"] == 2
    assert all(item["deleted"] for item in applied["response"]["execution"]["readback"])
