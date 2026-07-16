from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .client import redact_sensitive


WRITE_PLAN_SCHEMA_VERSION = 1
ARTIFACTS_ENV = "ALTERIOS_MCP_ARTIFACTS_DIR"


def save_write_plan(*, audit: dict[str, Any], response: Any = None) -> dict[str, Any]:
    """Persist a dry-run write plan and return stable metadata for later review."""
    if not audit.get("dry_run"):
        raise ValueError("Only dry-run audits can be stored as write plans.")
    target = _target_from_audit(audit)
    now = _utc_now()
    plan_id = _build_plan_id(audit=audit, response=response, created_at=now)
    payload = {
        "schema_version": WRITE_PLAN_SCHEMA_VERSION,
        "plan_id": plan_id,
        "created_at": now,
        "status": "planned",
        "target": target,
        "audit": redact_sensitive(audit),
        "response": redact_sensitive(response),
    }
    path = write_plan_path(plan_id=plan_id, profile=target["profile"], project_id=target["project_id"])
    _write_json(path, payload)
    append_write_journal(
        profile=target["profile"],
        project_id=target["project_id"],
        event="plan_created",
        payload={"plan_id": plan_id, "operation": audit.get("operation"), "plan_path": str(path)},
    )
    return {
        "plan_id": plan_id,
        "path": _relative_artifact_path(path),
        "created_at": now,
        "status": "planned",
    }


def append_execution_journal(*, audit: dict[str, Any], response: Any = None, plan_id: str | None = None) -> dict[str, Any]:
    target = _target_from_audit(audit)
    entry = append_write_journal(
        profile=target["profile"],
        project_id=target["project_id"],
        event="write_executed",
        payload={
            "plan_id": plan_id,
            "operation": audit.get("operation"),
            "response": redact_sensitive(response),
        },
    )
    return {"journal_path": entry["journal_path"], "event_id": entry["event_id"]}


def load_write_plan(*, plan_id: str, profile: str, project_id: str) -> dict[str, Any]:
    path = write_plan_path(plan_id=plan_id, profile=profile, project_id=project_id)
    if not path.exists():
        raise FileNotFoundError(f"Write plan {plan_id!r} was not found for profile/project.")
    return json.loads(path.read_text(encoding="utf-8"))


def list_write_plans(*, profile: str, project_id: str, limit: int = 20) -> list[dict[str, Any]]:
    directory = write_plan_dir(profile=profile, project_id=project_id)
    if not directory.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        if len(items) >= limit:
            break
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        items.append(
            {
                "plan_id": payload.get("plan_id") or path.stem,
                "created_at": payload.get("created_at"),
                "status": payload.get("status"),
                "operation": (payload.get("audit") or {}).get("operation"),
                "path": _relative_artifact_path(path),
            }
        )
    return items


def list_write_journal(*, profile: str, project_id: str, limit: int = 50) -> list[dict[str, Any]]:
    directory = write_journal_dir(profile=profile, project_id=project_id)
    if not directory.exists():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.jsonl"), key=lambda item: item.name, reverse=True):
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            if len(entries) >= limit:
                return entries
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            entry["journal_path"] = _relative_artifact_path(path)
            entries.append(entry)
    return entries


def assert_plan_matches_audit(*, plan_id: str, audit: dict[str, Any]) -> dict[str, Any]:
    target = _target_from_audit(audit)
    plan = load_write_plan(plan_id=plan_id, profile=target["profile"], project_id=target["project_id"])
    planned_audit = plan.get("audit") or {}
    if planned_audit.get("target") != audit.get("target"):
        raise ValueError("Write plan target does not match current execution target.")
    if planned_audit.get("operation") != audit.get("operation"):
        raise ValueError("Write plan operation does not match current execution operation.")
    return plan


def append_write_journal(*, profile: str, project_id: str, event: str, payload: dict[str, Any]) -> dict[str, Any]:
    now = _utc_now()
    event_id = _event_id(now=now, event=event, payload=payload)
    entry = {
        "schema_version": WRITE_PLAN_SCHEMA_VERSION,
        "event_id": event_id,
        "created_at": now,
        "event": event,
        "profile": profile,
        "project_id": project_id,
        "payload": redact_sensitive(payload),
    }
    path = write_journal_dir(profile=profile, project_id=project_id) / f"{now[:10]}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return {"event_id": event_id, "journal_path": _relative_artifact_path(path)}


def write_plan_path(*, plan_id: str, profile: str, project_id: str) -> Path:
    return write_plan_dir(profile=profile, project_id=project_id) / f"{_safe_component(plan_id)}.json"


def write_plan_dir(*, profile: str, project_id: str) -> Path:
    return artifact_root() / "write-plans" / _safe_component(profile) / _safe_component(project_id)


def write_journal_dir(*, profile: str, project_id: str) -> Path:
    return artifact_root() / "write-journal" / _safe_component(profile) / _safe_component(project_id)


def artifact_root() -> Path:
    return Path(os.environ.get(ARTIFACTS_ENV, "artifacts")).resolve()


def _target_from_audit(audit: dict[str, Any]) -> dict[str, str]:
    target = audit.get("target")
    if not isinstance(target, dict):
        raise ValueError("Write audit target is missing.")
    profile = str(target.get("profile") or "").strip()
    project_id = str(target.get("project_id") or "").strip()
    if not profile or not project_id:
        raise ValueError("Write audit target must contain profile and project_id.")
    return {"profile": profile, "project_id": project_id}


def _build_plan_id(*, audit: dict[str, Any], response: Any, created_at: str) -> str:
    payload = {
        "created_at": created_at,
        "target": audit.get("target"),
        "operation": audit.get("operation"),
        "response": response,
    }
    digest = hashlib.sha256(
        json.dumps(redact_sensitive(payload), ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    timestamp = created_at.replace("-", "").replace(":", "").replace("+", "").replace("Z", "")
    return f"wp_{timestamp}_{digest}"


def _event_id(*, now: str, event: str, payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        json.dumps(redact_sensitive({"now": now, "event": event, "payload": payload}), sort_keys=True, default=str).encode(
            "utf-8"
        )
    ).hexdigest()[:16]
    return f"wj_{now.replace('-', '').replace(':', '').replace('+', '').replace('Z', '')}_{digest}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _safe_component(value: str) -> str:
    normalized = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in str(value).strip())
    return normalized or "_"


def _relative_artifact_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(artifact_root()))
    except ValueError:
        return str(path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
