from __future__ import annotations

from .._support import *

def alterios_list_write_plans(profile: str, project_id: str, limit: int = 20) -> dict[str, Any]:
    """List stored dry-run write plans for a profile/project target."""
    if limit < 1 or limit > 200:
        raise ValueError("limit must be between 1 and 200.")
    return {
        "profile": profile,
        "project_id": project_id,
        "plans": list_write_plans(profile=profile, project_id=project_id, limit=limit),
    }

def alterios_get_write_plan(plan_id: str, profile: str, project_id: str) -> dict[str, Any]:
    """Read one stored dry-run write plan by plan_id."""
    if not plan_id.strip():
        raise ValueError("plan_id must not be empty.")
    return load_write_plan(plan_id=plan_id, profile=profile, project_id=project_id)

def alterios_write_journal(profile: str, project_id: str, limit: int = 50) -> dict[str, Any]:
    """Read recent write-plan and write-execution journal entries."""
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500.")
    return {
        "profile": profile,
        "project_id": project_id,
        "entries": list_write_journal(profile=profile, project_id=project_id, limit=limit),
    }

__all__ = ['alterios_list_write_plans', 'alterios_get_write_plan', 'alterios_write_journal']
