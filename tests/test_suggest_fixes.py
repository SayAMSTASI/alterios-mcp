from __future__ import annotations

from alterios_mcp.suggest_fixes import build_solution_options, render_markdown


def test_solution_options_return_multiple_actions_for_each_issue() -> None:
    result = build_solution_options(
        {
            "summary": {"ok": False, "status": "failed"},
            "checks": [
                {"name": "dotenv", "status": "fail", "summary": "dotenv missing"},
                {"name": "runtime_source", "status": "warn", "summary": "restart required"},
                {"name": "profiles", "status": "pass", "summary": "ready"},
            ],
        }
    )

    assert result["summary"]["status"] == "action_required"
    assert result["summary"]["issue_count"] == 2
    assert all(len(issue["options"]) >= 2 for issue in result["issues"])
    assert all(any(option["recommended"] for option in issue["options"]) for issue in result["issues"])
    assert "<private-env-path>" in str(result)
    assert "restart" in render_markdown(result).lower()


def test_solution_options_return_maintenance_commands_when_ready() -> None:
    result = build_solution_options(
        {
            "summary": {"ok": True, "status": "ready"},
            "checks": [{"name": "profiles", "status": "pass", "summary": "ready"}],
        }
    )

    assert result["summary"]["ok"] is True
    assert result["summary"]["issue_count"] == 0
    assert {item["id"] for item in result["maintenance_options"]} == {"verify-release", "check-for-update"}
