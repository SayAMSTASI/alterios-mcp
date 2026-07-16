from __future__ import annotations

from unittest.mock import patch

from alterios_mcp import live_task_preflight, server
from alterios_mcp.ux_contract import UX_CONTRACT_VERSION


ENV = {
    "ALTERIOS_PROFILE": "primary",
    "ALTERIOS_PRIMARY_BASE_URL": "https://primary.example",
    "ALTERIOS_PRIMARY_API_TOKEN": "token",
    "ALTERIOS_PRIMARY_PROJECT_ID": "project-default",
}
DELIVERY_EVIDENCE = {
    "work_item_ref": "gitea:#10",
    "agent_handoff_refs": ["gitea:#10/comment/pm"],
    "ux_contract_version": UX_CONTRACT_VERSION,
}


def _runtime(*, stale: bool = False) -> dict[str, object]:
    return {
        "fingerprint": "fp-1",
        "stale": stale,
        "git": {"available": True, "commit": "commit-1", "dirty": False},
        "tool_schema_version": "test-tools",
        "ux_contract_version": UX_CONTRACT_VERSION,
    }


def _health(*, ok: bool = True, source: str = "cache") -> dict[str, object]:
    return {
        "readonly": True,
        "source": source,
        "summary": {
            "ok": ok,
            "issue_count": 0 if ok else 1,
            "issues_by_severity": {} if ok else {"error": 1},
            "fingerprint": "health-1",
        },
    }


def _smoke(*, ok: bool = True) -> dict[str, object]:
    return {
        "readonly": True,
        "summary": {
            "ok": ok,
            "check_count": 6,
            "failed_count": 0 if ok else 1,
            "failed_checks": [] if ok else ["write_gate_and_plan"],
        },
    }


def test_live_task_preflight_ready_with_cache_warning(monkeypatch) -> None:
    monkeypatch.setattr(live_task_preflight, "build_runtime_fingerprint", lambda tool_count=None: _runtime())
    monkeypatch.setattr(live_task_preflight, "collect_alterios_mcp_processes", lambda: [])
    monkeypatch.setattr(live_task_preflight, "run_project_health", lambda **kwargs: _health(ok=True, source="cache"))
    monkeypatch.setattr(live_task_preflight, "run_replay_smoke", lambda **kwargs: _smoke(ok=True))

    with patch.dict("os.environ", ENV, clear=True):
        result = live_task_preflight.run_live_task_preflight(
            profile="primary",
            project_id="project-1",
            scenario_tool="alterios_create_material_module",
            delivery_evidence=DELIVERY_EVIDENCE,
        )

    assert result["summary"]["ok"] is True
    assert result["summary"]["status"] == "ready"
    assert result["checks"][1]["name"] == "runtime_freshness"
    assert result["checks"][4]["name"] == "project_health"
    assert result["warnings"][0]["code"] == "project_health_cache"
    assert "alterios_create_material_module" in result["next_actions"][0]


def test_live_task_preflight_blocks_missing_delivery_evidence(monkeypatch) -> None:
    monkeypatch.setattr(live_task_preflight, "build_runtime_fingerprint", lambda tool_count=None: _runtime())
    monkeypatch.setattr(live_task_preflight, "collect_alterios_mcp_processes", lambda: [])

    with patch.dict("os.environ", {}, clear=True):
        result = live_task_preflight.run_live_task_preflight(
            profile="primary",
            project_id="project-1",
            include_project_health=False,
            include_replay_smoke=False,
        )

    assert result["summary"]["ok"] is False
    assert {item["code"] for item in result["blockers"]} == {"delivery_evidence_missing"}
    assert result["checks"][2]["missing"] == ["work_item_ref", "agent_handoff_refs", "ux_contract_version"]


def test_live_task_preflight_blocks_project_health_errors(monkeypatch) -> None:
    monkeypatch.setattr(live_task_preflight, "build_runtime_fingerprint", lambda tool_count=None: _runtime())
    monkeypatch.setattr(live_task_preflight, "collect_alterios_mcp_processes", lambda: [])
    monkeypatch.setattr(live_task_preflight, "run_project_health", lambda **kwargs: _health(ok=False, source="live"))

    with patch.dict("os.environ", ENV, clear=True):
        result = live_task_preflight.run_live_task_preflight(
            profile="primary",
            project_id="project-1",
            delivery_evidence=DELIVERY_EVIDENCE,
            include_replay_smoke=False,
        )

    assert result["summary"]["ok"] is False
    assert "project_health_errors" in {item["code"] for item in result["blockers"]}


def test_live_task_preflight_blocks_duplicate_mcp_processes(monkeypatch) -> None:
    monkeypatch.setattr(live_task_preflight, "build_runtime_fingerprint", lambda tool_count=None: _runtime())
    monkeypatch.setattr(
        live_task_preflight,
        "collect_alterios_mcp_processes",
        lambda: [{"pid": 1}, {"pid": 2}],
    )

    with patch.dict("os.environ", ENV, clear=True):
        result = live_task_preflight.run_live_task_preflight(
            profile="primary",
            project_id="project-1",
            delivery_evidence=DELIVERY_EVIDENCE,
            include_project_health=False,
            include_replay_smoke=False,
        )

    assert result["summary"]["ok"] is False
    assert "duplicate_mcp_processes" in {item["code"] for item in result["blockers"]}
    assert result["checks"][1]["process_hygiene"]["duplicate_process_count"] == 1
    assert result["checks"][1]["process_hygiene"]["duplicate_instance_count"] == 1


def test_live_task_preflight_cli_and_server_tool_use_safe_readonly_defaults(monkeypatch, capsys) -> None:
    monkeypatch.setattr(live_task_preflight, "build_runtime_fingerprint", lambda tool_count=None: _runtime())
    monkeypatch.setattr(live_task_preflight, "collect_alterios_mcp_processes", lambda: [])

    with patch.dict("os.environ", ENV, clear=True):
        exit_code = live_task_preflight.main(
            [
                "--profile",
                "primary",
                "--project-id",
                "project-1",
                "--scenario-tool",
                "alterios_create_report_tab",
                "--work-item-ref",
                "gitea:#10",
                "--agent-handoff-ref",
                "gitea:#10/comment/report",
                "--no-project-health",
                "--no-replay-smoke",
            ]
        )
        server_result = server.alterios_live_task_preflight(
            profile="primary",
            project_id="project-1",
            scenario_tool="alterios_create_report_tab",
            delivery_evidence=DELIVERY_EVIDENCE,
            include_project_health=False,
            include_replay_smoke=False,
        )

    assert exit_code == 0
    assert "alterios_live_task_preflight" in capsys.readouterr().out
    assert server_result["readonly"] is True
    assert server_result["summary"]["ok"] is True
