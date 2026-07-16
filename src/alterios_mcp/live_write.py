from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .client import redact_sensitive
from .live_task_preflight import run_live_task_preflight


FAST_LIVE_SCENARIO_TOOLS = frozenset(
    {
        "alterios_create_material_module",
        "alterios_create_report_tab",
        "alterios_create_process_flow",
    }
)

RESERVED_SCENARIO_ARGUMENTS = frozenset(
    {
        "profile",
        "project_id",
        "delivery_evidence",
        "expected_runtime_fingerprint",
        "dry_run",
        "plan_id",
    }
)


def run_fast_live_write(
    *,
    scenario_tool: str,
    scenario_args: dict[str, Any],
    profile: str,
    project_id: str,
    delivery_evidence: dict[str, Any],
    scenario_runners: Mapping[str, Callable[..., dict[str, Any]]],
    expected_runtime_fingerprint: str | None = None,
    dry_run: bool = True,
    plan_id: str | None = None,
    refresh_health: bool = False,
    health_cache_ttl_seconds: int | None = None,
    allow_cached_health: bool = True,
    require_clean_health: bool = True,
    include_replay_smoke: bool = False,
    artifacts_dir: str | None = None,
) -> dict[str, Any]:
    """Plan or apply one approved scenario through the fast live-write gate."""
    tool = scenario_tool.strip()
    target_profile = profile.strip()
    target_project_id = project_id.strip()
    if tool not in FAST_LIVE_SCENARIO_TOOLS:
        allowed = ", ".join(sorted(FAST_LIVE_SCENARIO_TOOLS))
        raise ValueError(f"Unsupported fast-live scenario {tool!r}; expected one of: {allowed}.")
    if tool not in scenario_runners:
        raise ValueError(f"Fast-live scenario runner {tool!r} is not registered.")
    if not target_profile:
        raise ValueError("profile is required for fast live writes.")
    if not target_project_id:
        raise ValueError("project_id is required for fast live writes.")
    if not isinstance(scenario_args, dict):
        raise ValueError("scenario_args must be a JSON object.")
    collisions = sorted(set(scenario_args) & RESERVED_SCENARIO_ARGUMENTS)
    if collisions:
        raise ValueError(f"scenario_args contains reserved keys: {', '.join(collisions)}.")
    if not dry_run and not str(plan_id or "").strip():
        raise ValueError("plan_id is required when dry_run=false for fast live writes.")

    # Scenario apply performs the authoritative Gitea verification immediately
    # before mutation, so the apply preflight only checks evidence shape.
    preflight_verifies_gitea = dry_run
    preflight = run_live_task_preflight(
        profile=target_profile,
        project_id=target_project_id,
        scenario_tool=tool,
        delivery_evidence=delivery_evidence,
        expected_fingerprint=expected_runtime_fingerprint,
        include_project_health=True,
        refresh_health=refresh_health,
        health_cache_ttl_seconds=health_cache_ttl_seconds,
        allow_cached_health=allow_cached_health,
        require_clean_health=require_clean_health,
        include_replay_smoke=include_replay_smoke,
        include_live_replay=False,
        require_delivery_evidence=True,
        verify_gitea_evidence=preflight_verifies_gitea,
        required_agent_roles=None,
        allow_closed_work_item=False,
        gitea_dotenv_path=None,
        artifacts_dir=artifacts_dir,
    )
    if not bool((preflight.get("summary") or {}).get("ok")):
        return redact_sensitive(
            {
                "kind": "alterios_fast_live_write",
                "mode": "plan" if dry_run else "apply",
                "status": "blocked",
                "scenario_tool": tool,
                "target": {"profile": target_profile, "project_id": target_project_id},
                "preflight": preflight,
                "scenario": None,
            }
        )

    runtime_check = next(
        (item for item in preflight.get("checks", []) if item.get("name") == "runtime_freshness"),
        {},
    )
    runtime_fingerprint = str(runtime_check.get("fingerprint") or expected_runtime_fingerprint or "").strip()
    call_args = dict(scenario_args)
    call_args.update(
        {
            "profile": target_profile,
            "project_id": target_project_id,
            "delivery_evidence": delivery_evidence,
            "expected_runtime_fingerprint": runtime_fingerprint or None,
            "dry_run": dry_run,
            "plan_id": plan_id,
        }
    )
    scenario_result = scenario_runners[tool](**call_args)
    return redact_sensitive(
        {
            "kind": "alterios_fast_live_write",
            "mode": "plan" if dry_run else "apply",
            "status": "planned" if dry_run else "applied",
            "scenario_tool": tool,
            "target": {"profile": target_profile, "project_id": target_project_id},
            "preflight": preflight,
            "scenario": scenario_result,
            "next_actions": _next_actions(dry_run=dry_run, scenario_result=scenario_result),
        }
    )


def _next_actions(*, dry_run: bool, scenario_result: dict[str, Any]) -> list[str]:
    if not dry_run:
        return ["Review scenario readback and record UI evidence for user-facing changes."]
    plan_id = str(((scenario_result.get("plan") or {}).get("plan_id")) or "").strip()
    if not plan_id:
        return ["The scenario did not return plan_id; do not apply until the plan is stored."]
    return [
        f"Review plan {plan_id}.",
        "Call alterios_fast_live_write with dry_run=false, the same scenario_args, delivery_evidence, and plan_id.",
    ]
