from __future__ import annotations

from typing import Any

import pytest

from alterios_mcp import live_write


READY_PREFLIGHT = {
    "summary": {"ok": True, "status": "ready"},
    "checks": [{"name": "runtime_freshness", "fingerprint": "runtime-1"}],
}


def _base_kwargs(runner: Any) -> dict[str, Any]:
    return {
        "scenario_tool": "alterios_create_material_module",
        "scenario_args": {"module_name": "Indicators", "field_name_prefix": "indicator"},
        "profile": "primary",
        "project_id": "project-1",
        "delivery_evidence": {
            "work_item_ref": "gitea:#10",
            "agent_handoff_refs": ["gitea:#10/comment/1"],
            "ux_contract_version": "current",
        },
        "scenario_runners": {"alterios_create_material_module": runner},
    }


def test_fast_live_write_plans_scenario_after_preflight(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(live_write, "run_live_task_preflight", lambda **kwargs: READY_PREFLIGHT)

    def runner(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"dry_run": True, "plan": {"plan_id": "wp-1"}}

    result = live_write.run_fast_live_write(**_base_kwargs(runner))

    assert result["status"] == "planned"
    assert result["scenario"]["plan"]["plan_id"] == "wp-1"
    assert calls[0]["dry_run"] is True
    assert calls[0]["expected_runtime_fingerprint"] == "runtime-1"
    assert calls[0]["profile"] == "primary"


def test_fast_live_write_apply_uses_reviewed_plan(monkeypatch) -> None:
    preflight_calls: list[dict[str, Any]] = []
    scenario_calls: list[dict[str, Any]] = []

    def preflight(**kwargs: Any) -> dict[str, Any]:
        preflight_calls.append(kwargs)
        return READY_PREFLIGHT

    monkeypatch.setattr(live_write, "run_live_task_preflight", preflight)

    def runner(**kwargs: Any) -> dict[str, Any]:
        scenario_calls.append(kwargs)
        return {"dry_run": False, "response": {"readback": {"_id": "module-1"}}}

    result = live_write.run_fast_live_write(
        **_base_kwargs(runner),
        dry_run=False,
        plan_id="wp-1",
    )

    assert result["status"] == "applied"
    assert scenario_calls[0]["plan_id"] == "wp-1"
    assert scenario_calls[0]["dry_run"] is False
    assert preflight_calls[0]["verify_gitea_evidence"] is False


def test_fast_live_write_stops_on_preflight_blocker(monkeypatch) -> None:
    monkeypatch.setattr(
        live_write,
        "run_live_task_preflight",
        lambda **kwargs: {"summary": {"ok": False}, "blockers": [{"code": "project_health_errors"}]},
    )

    def runner(**kwargs: Any) -> dict[str, Any]:  # pragma: no cover - must not run.
        raise AssertionError("scenario runner must not be called")

    result = live_write.run_fast_live_write(**_base_kwargs(runner))

    assert result["status"] == "blocked"
    assert result["scenario"] is None


def test_fast_live_write_rejects_reserved_args_and_missing_apply_plan() -> None:
    runner = lambda **kwargs: {}  # noqa: E731
    kwargs = _base_kwargs(runner)
    kwargs["scenario_args"] = {"module_name": "Indicators", "profile": "secondary"}

    with pytest.raises(ValueError, match="reserved keys: profile"):
        live_write.run_fast_live_write(**kwargs)

    kwargs = _base_kwargs(runner)
    with pytest.raises(ValueError, match="plan_id is required"):
        live_write.run_fast_live_write(**kwargs, dry_run=False)


def test_fast_live_write_rejects_non_scenario_tool() -> None:
    with pytest.raises(ValueError, match="Unsupported fast-live scenario"):
        live_write.run_fast_live_write(
            scenario_tool="alterios_rest_write",
            scenario_args={},
            profile="primary",
            project_id="project-1",
            delivery_evidence={},
            scenario_runners={},
        )
