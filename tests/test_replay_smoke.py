from __future__ import annotations

import json

from alterios_mcp import server
from alterios_mcp.replay_smoke import render_markdown, run_replay_smoke


def test_replay_smoke_runs_local_contract_checks_without_live_network(tmp_path) -> None:
    result = run_replay_smoke(
        profile="primary",
        project_id="project-1",
        artifacts_dir=str(tmp_path),
    )

    checks = {check["name"]: check for check in result["checks"]}
    assert result["summary"]["ok"] is True
    assert checks["mcp_tool_registry"]["tool_count"] >= 75
    assert checks["write_gate_and_plan"]["gate_blocked_without_env"] is True
    assert checks["write_gate_and_plan"]["plan_mismatch_blocked"] is True
    assert checks["write_gate_and_plan"]["sensitive_values_are_redacted"] is True
    assert checks["form_surface_validator"]["ok"] is True
    assert checks["stimulsoft_layout_validator"]["render_evidence"]["status"] == "not_collected"
    assert "alterios_validate_printable_render" in checks["stimulsoft_layout_validator"]["render_evidence"]["note"]
    assert checks["live_readonly_discovery"]["skipped"] is True
    assert "secret-token" not in json.dumps(result, ensure_ascii=False, sort_keys=True)


def test_replay_smoke_markdown_summarizes_checks(tmp_path) -> None:
    result = run_replay_smoke(
        profile="primary",
        project_id="project-1",
        artifacts_dir=str(tmp_path),
    )
    markdown = render_markdown(result)

    assert "Alterios MCP replay smoke" in markdown
    assert "| `write_gate_and_plan` | ok |" in markdown
    assert "status: OK" in markdown


def test_server_replay_smoke_tool_uses_safe_defaults() -> None:
    result = server.alterios_replay_smoke(
        profile="primary",
        project_id="project-1",
        include_live=False,
    )

    assert result["summary"]["ok"] is True
    assert result["readonly"] is True
    assert result["checks"][-1]["name"] == "live_readonly_discovery"
    assert result["checks"][-1]["skipped"] is True


def test_replay_smoke_include_live_skips_when_config_is_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ALTERIOS_SECONDARY_API_TOKEN", raising=False)
    monkeypatch.delenv("ALTERIOS_SECONDARY_BASE_URL", raising=False)
    monkeypatch.setenv("ALTERIOS_DOTENV_PATH", str(tmp_path / "missing.env"))

    result = run_replay_smoke(
        profile="secondary",
        project_id="project-1",
        include_live=True,
        artifacts_dir=str(tmp_path),
    )

    live_check = result["checks"][-1]
    assert result["summary"]["ok"] is True
    assert live_check["name"] == "live_readonly_discovery"
    assert live_check["skipped"] is True
    assert live_check["reason"] == "missing live configuration"
