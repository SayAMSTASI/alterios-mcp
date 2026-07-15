from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .client import load_config_values
from .gitea_workboard import agent_report_body


LOCAL_STATUSES = {"backlog", "ready", "in_progress", "review", "verify", "done", "blocked"}
LOCAL_KINDS = {"brief", "feature", "bug", "research", "verification", "docs", "chore", "task"}


@dataclass(frozen=True)
class LocalWorkboardConfig:
    base_dir: Path

    @classmethod
    def from_env(
        cls,
        dotenv_path: str | Path | None = ".env",
        base_dir: str | Path | None = None,
    ) -> "LocalWorkboardConfig":
        if base_dir:
            return cls(base_dir=Path(base_dir).expanduser())
        effective_dotenv_path = dotenv_path
        if dotenv_path == ".env":
            effective_dotenv_path = (
                os.environ.get("LOCAL_WORKBOARD_DOTENV_PATH")
                or os.environ.get("ALTERIOS_DOTENV_PATH")
                or ".env"
            )
        values = load_config_values(effective_dotenv_path)
        configured = (
            values.get("LOCAL_WORKBOARD_DIR")
            or values.get("ALTERIOS_LOCAL_WORKBOARD_DIR")
            or os.environ.get("LOCAL_WORKBOARD_DIR")
            or os.environ.get("ALTERIOS_LOCAL_WORKBOARD_DIR")
        )
        if configured:
            return cls(base_dir=Path(configured).expanduser())
        return cls(base_dir=Path.home() / "Documents" / "AlteriosCodex" / "workboard")

    def redacted(self) -> dict[str, str]:
        return {"base_dir": str(self.base_dir)}


def planned_local_workboard_result(
    *,
    operation: str,
    config: LocalWorkboardConfig,
    dry_run: bool,
    payload: dict[str, Any],
    response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "dry_run": dry_run,
        "operation": operation,
        "target": config.redacted(),
        "payload": payload,
        "response": response,
        "required_execution_gates": ["dry_run=false"],
        "will_execute": not dry_run,
    }


def create_local_work_item(
    *,
    title: str,
    body: str,
    status: str = "backlog",
    kind: str = "task",
    sprint: str | None = None,
    labels: list[str] | None = None,
    assignee: str | None = None,
    base_dir: str | Path | None = None,
    dotenv_path: str | Path | None = ".env",
    dry_run: bool = True,
) -> dict[str, Any]:
    config = LocalWorkboardConfig.from_env(dotenv_path=dotenv_path, base_dir=base_dir)
    normalized_title = title.strip()
    if not normalized_title:
        raise ValueError("title must not be empty.")
    _validate_status(status)
    _validate_kind(kind)
    item_id = _next_item_id(config.base_dir, normalized_title)
    payload = {
        "item_id": item_id,
        "title": normalized_title,
        "status": status,
        "kind": kind,
        "sprint": sprint,
        "labels": labels or [],
        "assignee": assignee,
        "files": _item_files(config.base_dir, item_id, sprint=sprint),
    }
    if dry_run:
        return planned_local_workboard_result(
            operation="local_workboard_create_item",
            config=config,
            dry_run=True,
            payload=payload,
            response={"will_create_private_files": True},
        )

    item_dir = config.base_dir / "issues" / item_id
    item_dir.mkdir(parents=True, exist_ok=False)
    (item_dir / "evidence").mkdir()
    created_at = _now_iso()
    (item_dir / "brief.md").write_text(
        _brief_markdown(
            item_id=item_id,
            title=normalized_title,
            status=status,
            kind=kind,
            sprint=sprint,
            labels=labels or [],
            assignee=assignee,
            body=body,
            created_at=created_at,
        ),
        encoding="utf-8",
    )
    (item_dir / "agent-reports.md").write_text(
        f"# Отчеты агентов\n\nЗадача: {normalized_title}\n\n",
        encoding="utf-8",
    )
    _ensure_index(config.base_dir)
    _append_index_row(config.base_dir / "index.md", item_id, normalized_title, status, kind, sprint, assignee)
    if sprint:
        sprint_file = config.base_dir / "sprints" / _safe_slug(sprint) / "board.md"
        _ensure_sprint_board(sprint_file, sprint)
        _append_index_row(sprint_file, item_id, normalized_title, status, kind, sprint, assignee)
    return planned_local_workboard_result(
        operation="local_workboard_create_item",
        config=config,
        dry_run=False,
        payload=payload,
        response={"created": True, "item_dir": str(item_dir), "created_at": created_at},
    )


def list_local_work_items(
    *,
    status: str | None = None,
    sprint: str | None = None,
    base_dir: str | Path | None = None,
    dotenv_path: str | Path | None = ".env",
    limit: int = 50,
) -> dict[str, Any]:
    if status:
        _validate_status(status)
    if limit < 1 or limit > 200:
        raise ValueError("limit must be between 1 and 200.")
    config = LocalWorkboardConfig.from_env(dotenv_path=dotenv_path, base_dir=base_dir)
    issues_dir = config.base_dir / "issues"
    items: list[dict[str, Any]] = []
    if issues_dir.exists():
        for brief_path in sorted(issues_dir.glob("*/brief.md"), reverse=True):
            item = _read_brief_summary(brief_path)
            if status and item.get("status") != status:
                continue
            if sprint and item.get("sprint") != sprint:
                continue
            items.append(item)
            if len(items) >= limit:
                break
    return {
        "target": config.redacted(),
        "status": status,
        "sprint": sprint,
        "items": items,
    }


def add_local_agent_report(
    *,
    item_id: str,
    role: str,
    scope: str,
    findings: str,
    artifacts: str = "",
    verification: str = "",
    risks: str = "",
    next_step: str = "",
    body: str | None = None,
    base_dir: str | Path | None = None,
    dotenv_path: str | Path | None = ".env",
    dry_run: bool = True,
) -> dict[str, Any]:
    if not item_id.strip():
        raise ValueError("item_id must not be empty.")
    config = LocalWorkboardConfig.from_env(dotenv_path=dotenv_path, base_dir=base_dir)
    report_body = body or agent_report_body(
        role=role,
        scope=scope,
        findings=findings,
        artifacts=artifacts,
        verification=verification,
        risks=risks,
        next_step=next_step,
    )
    payload = {"item_id": item_id, "body": report_body}
    report_path = config.base_dir / "issues" / item_id / "agent-reports.md"
    if dry_run:
        return planned_local_workboard_result(
            operation="local_workboard_add_agent_report",
            config=config,
            dry_run=True,
            payload={**payload, "file": str(report_path)},
        )
    if not report_path.exists():
        raise FileNotFoundError(f"Local work item was not found: {item_id}")
    entry = f"## {_now_iso()} - {role}\n\n{report_body.strip()}\n\n"
    with report_path.open("a", encoding="utf-8") as handle:
        handle.write(entry)
    return planned_local_workboard_result(
        operation="local_workboard_add_agent_report",
        config=config,
        dry_run=False,
        payload={**payload, "file": str(report_path)},
        response={"appended": True, "file": str(report_path)},
    )


def ensure_local_workboard(
    *,
    base_dir: str | Path | None = None,
    dotenv_path: str | Path | None = ".env",
) -> dict[str, Any]:
    config = LocalWorkboardConfig.from_env(dotenv_path=dotenv_path, base_dir=base_dir)
    _ensure_index(config.base_dir)
    return {"target": config.redacted(), "created": True}


def _item_files(base_dir: Path, item_id: str, *, sprint: str | None) -> dict[str, str | None]:
    item_dir = base_dir / "issues" / item_id
    return {
        "brief": str(item_dir / "brief.md"),
        "agent_reports": str(item_dir / "agent-reports.md"),
        "evidence_dir": str(item_dir / "evidence"),
        "index": str(base_dir / "index.md"),
        "sprint_board": str(base_dir / "sprints" / _safe_slug(sprint) / "board.md") if sprint else None,
    }


def _brief_markdown(
    *,
    item_id: str,
    title: str,
    status: str,
    kind: str,
    sprint: str | None,
    labels: list[str],
    assignee: str | None,
    body: str,
    created_at: str,
) -> str:
    meta = {
        "id": item_id,
        "title": title,
        "status": status,
        "kind": kind,
        "sprint": sprint,
        "labels": labels,
        "assignee": assignee,
        "created_at": created_at,
        "private": True,
    }
    return "\n".join(
        [
            "---",
            json.dumps(meta, ensure_ascii=False, indent=2),
            "---",
            "",
            f"# {title}",
            "",
            body.strip(),
            "",
        ]
    )


def _ensure_index(base_dir: Path) -> None:
    (base_dir / "issues").mkdir(parents=True, exist_ok=True)
    (base_dir / "sprints").mkdir(parents=True, exist_ok=True)
    index_path = base_dir / "index.md"
    if not index_path.exists():
        index_path.write_text(
            "# Local private workboard\n\n"
            "Этот каталог хранит рабочий процесс вне публичного Git.\n\n"
            "| ID | Title | Status | Kind | Sprint | Assignee |\n"
            "|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )


def _ensure_sprint_board(path: Path, sprint: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            f"# Sprint {sprint}\n\n"
            "| ID | Title | Status | Kind | Sprint | Assignee |\n"
            "|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )


def _append_index_row(
    path: Path,
    item_id: str,
    title: str,
    status: str,
    kind: str,
    sprint: str | None,
    assignee: str | None,
) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            f"| `{item_id}` | {title} | `{status}` | `{kind}` | {sprint or ''} | {assignee or ''} |\n"
        )


def _read_brief_summary(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    meta: dict[str, Any] = {"id": path.parent.name}
    if text.startswith("---\n"):
        try:
            _, raw_meta, _rest = text.split("---", 2)
            parsed = json.loads(raw_meta.strip())
            if isinstance(parsed, dict):
                meta.update(parsed)
        except (ValueError, json.JSONDecodeError):
            pass
    meta["path"] = str(path)
    return meta


def _next_item_id(base_dir: Path, title: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    stem = f"{timestamp}-{_safe_slug(title)}"
    item_id = stem
    counter = 2
    while (base_dir / "issues" / item_id).exists():
        item_id = f"{stem}-{counter}"
        counter += 1
    return item_id


def _safe_slug(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    slug = re.sub(r"[^a-z0-9_-]+", "-", normalized).strip("-")
    return slug[:60] or "work-item"


def _validate_status(status: str) -> None:
    if status not in LOCAL_STATUSES:
        raise ValueError("status must be one of: " + ", ".join(sorted(LOCAL_STATUSES)))


def _validate_kind(kind: str) -> None:
    if kind not in LOCAL_KINDS:
        raise ValueError("kind must be one of: " + ", ".join(sorted(LOCAL_KINDS)))


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
