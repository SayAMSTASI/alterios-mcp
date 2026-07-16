from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .client import redact_sensitive
from .write_plan import append_execution_journal, save_write_plan


class ControlledWriteError(RuntimeError):
    pass


DESTRUCTIVE_RISK_LEVELS = frozenset({"destructive"})
DANGEROUS_RISK_LEVELS = frozenset({"destructive", "security"})
WRITE_RISK_LEVELS = frozenset(
    {
        "write",
        "destructive",
        "security",
        "workflow_side_effect",
        "external_side_effect",
        "audit_side_effect",
        "manual_script",
    }
)
SECURITY_REST_PREFIXES = (
    "/api/roles",
    "/api/security",
    "/api/permissions",
    "/api/users",
    "/api/user-groups",
    "/api/usergroups",
)

TARGET_ID_KEYS = frozenset({"_id", "id", "contentId", "taskId", "scriptId", "diagramId", "fieldId", "entityId"})
TARGET_ID_SUFFIXES = ("Id", "Ids")


@dataclass(frozen=True)
class WriteTarget:
    profile: str
    project_id: str

    def as_dict(self) -> dict[str, str]:
        return {"profile": self.profile, "project_id": self.project_id}


@dataclass(frozen=True)
class WriteOperation:
    name: str
    kind: str
    risk_level: str
    summary: str
    method: str | None = None
    path: str | None = None
    target_ids: tuple[str, ...] = ()
    request: Any = None
    requires_readback: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "risk_level": self.risk_level,
            "summary": self.summary,
            "method": self.method,
            "path": self.path,
            "target_ids": list(self.target_ids),
            "request": redact_sensitive(self.request),
            "requires_readback": self.requires_readback,
        }


@dataclass(frozen=True)
class WriteAudit:
    target: WriteTarget
    operation: WriteOperation
    dry_run: bool
    write_enabled: bool
    dangerous_write_enabled: bool
    allow_destructive: bool
    required_checks: tuple[str, ...]
    status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "dry_run": self.dry_run,
            "write_enabled": self.write_enabled,
            "dangerous_write_enabled": self.dangerous_write_enabled,
            "allow_destructive": self.allow_destructive,
            "target": self.target.as_dict(),
            "operation": self.operation.as_dict(),
            "required_checks": list(self.required_checks),
        }


def build_write_target(profile: str | None, project_id: str | None) -> WriteTarget:
    normalized_profile = (profile or "").strip()
    normalized_project_id = (project_id or "").strip()
    missing = []
    if not normalized_profile:
        missing.append("explicit profile")
    if not normalized_project_id:
        missing.append("explicit project_id")
    if missing:
        raise ControlledWriteError("Controlled writes require " + " and ".join(missing) + ".")
    return WriteTarget(profile=normalized_profile, project_id=normalized_project_id)


def assert_write_allowed(
    *,
    profile: str | None,
    project_id: str | None,
    operation: WriteOperation,
    write_enabled: bool,
    dangerous_write_enabled: bool = False,
    allow_destructive: bool = False,
) -> WriteTarget:
    target = build_write_target(profile, project_id)
    if operation.risk_level not in WRITE_RISK_LEVELS:
        raise ControlledWriteError(f"Unsupported write risk level: {operation.risk_level}")
    if not write_enabled:
        raise ControlledWriteError("Write calls are disabled. Set ALTERIOS_MCP_ALLOW_WRITE=1 explicitly.")
    if operation.risk_level in DANGEROUS_RISK_LEVELS and not dangerous_write_enabled:
        raise ControlledWriteError(
            "Dangerous writes require ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE=1 explicitly."
        )
    if operation.risk_level in DANGEROUS_RISK_LEVELS and not allow_destructive:
        raise ControlledWriteError("Dangerous writes require allow_destructive=True.")
    return target


def build_write_audit(
    *,
    profile: str | None,
    project_id: str | None,
    operation: WriteOperation,
    dry_run: bool,
    write_enabled: bool,
    dangerous_write_enabled: bool = False,
    allow_destructive: bool = False,
) -> WriteAudit:
    target = build_write_target(profile, project_id)
    if operation.risk_level not in WRITE_RISK_LEVELS:
        raise ControlledWriteError(f"Unsupported write risk level: {operation.risk_level}")
    required_checks = [
        "Run alterios_config for the same profile before execution.",
        "Pass explicit project_id; do not rely on ALTERIOS_<PROFILE>_PROJECT_ID for writes.",
        "Keep ALTERIOS_MCP_ALLOW_WRITE unset unless an execution is intentional.",
    ]
    if operation.requires_readback:
        required_checks.append("Verify the write through a readback route after execution.")
    if operation.risk_level in DANGEROUS_RISK_LEVELS:
        required_checks.append("Review every target ID and pass allow_destructive=True only after explicit approval.")
        required_checks.append(
            "Set ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE=1 only for a dedicated security/destructive sandbox run."
        )
    status = "dry_run" if dry_run else "ready_to_execute"
    return WriteAudit(
        target=target,
        operation=operation,
        dry_run=dry_run,
        write_enabled=write_enabled,
        dangerous_write_enabled=dangerous_write_enabled,
        allow_destructive=allow_destructive,
        required_checks=tuple(required_checks),
        status=status,
    )


def controlled_write_result(
    *,
    audit: WriteAudit,
    response: dict[str, Any] | None = None,
    plan_id: str | None = None,
) -> dict[str, Any]:
    audit_dict = audit.as_dict()
    redacted_response = redact_sensitive(response)
    result: dict[str, Any] = {"dry_run": audit.dry_run, "audit": audit_dict, "response": redacted_response}
    if audit.dry_run:
        result["plan"] = save_write_plan(audit=audit_dict, response=redacted_response)
    else:
        result["journal"] = append_execution_journal(audit=audit_dict, response=redacted_response, plan_id=plan_id)
    return result


def collect_target_ids(value: Any) -> tuple[str, ...]:
    found: list[str] = []

    def visit(item: Any, key: str | None = None) -> None:
        if isinstance(item, dict):
            for child_key, child_value in item.items():
                visit(child_value, str(child_key))
            return
        if isinstance(item, list):
            for child in item:
                visit(child, key)
            return
        if isinstance(item, tuple):
            for child in item:
                visit(child, key)
            return
        if not key or item is None:
            return
        if key in TARGET_ID_KEYS or key.endswith(TARGET_ID_SUFFIXES):
            normalized = str(item).strip()
            if normalized:
                found.append(normalized)

    visit(value)
    return tuple(dict.fromkeys(found))


def classify_rest_write_risk(method: str, path: str) -> str:
    normalized_method = method.upper().strip()
    normalized_path = _normalized_rest_path(path)
    if any(
        normalized_path == prefix or normalized_path.startswith(prefix + "/")
        for prefix in SECURITY_REST_PREFIXES
    ):
        return "security"
    if normalized_method == "DELETE":
        return "destructive"
    return "write"


def is_dangerous_write_risk(risk_level: str) -> bool:
    return risk_level in DANGEROUS_RISK_LEVELS


def _normalized_rest_path(path: str) -> str:
    path_only = (path or "").split("?", 1)[0].strip()
    if not path_only.startswith("/"):
        path_only = "/" + path_only
    return path_only.rstrip("/") or "/"
