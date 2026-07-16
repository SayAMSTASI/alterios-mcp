from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .client import AlteriosClient, AlteriosConfig, AlteriosConfigError, AlteriosRequestError, redact_sensitive
from .deep_inventory import build_deep_inventory
from .deep_inventory import _items as inventory_items
from .stimulsoft_layout import analyze_stimulsoft_layout
from .write_plan import ARTIFACTS_ENV

PROJECT_HEALTH_SCHEMA_VERSION = 1
PROJECT_HEALTH_DIFF_SCHEMA_VERSION = 1
HEALTH_CACHE_TTL_ENV = "ALTERIOS_MCP_HEALTH_CACHE_TTL_SECONDS"
DEFAULT_HEALTH_CACHE_TTL_SECONDS = 300


def run_project_health(
    *,
    profile: str | None = None,
    project_id: str | None = None,
    refresh: bool = False,
    use_cache: bool = True,
    write_cache: bool = True,
    cache_ttl_seconds: int | None = None,
    include_processes: bool = True,
    include_report_templates: bool = False,
    artifacts_dir: str | None = None,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a read-only project health summary for write preflight decisions."""
    old_artifacts_dir = os.environ.get(ARTIFACTS_ENV)
    if artifacts_dir:
        os.environ[ARTIFACTS_ENV] = artifacts_dir
    try:
        target_profile = (profile or "").strip()
        target_project_id = (project_id or "").strip()
        resolved_cache_ttl = resolve_cache_ttl_seconds(cache_ttl_seconds)
        previous_snapshot = load_latest_snapshot(profile=target_profile, project_id=target_project_id) if use_cache else None
        cache_status = snapshot_cache_status(
            profile=target_profile,
            project_id=target_project_id,
            ttl_seconds=resolved_cache_ttl,
            snapshot=previous_snapshot,
        )
        source = "provided"
        written: dict[str, Any] | None = None
        diff_written: dict[str, Any] | None = None

        if snapshot is None:
            if use_cache and previous_snapshot is not None and cache_status["fresh"] and not refresh:
                snapshot = previous_snapshot
                previous_snapshot = None
                source = "cache"
            else:
                snapshot = collect_live_health_inventory(
                    profile=target_profile or None,
                    project_id=target_project_id or None,
                    include_processes=include_processes,
                    include_report_templates=include_report_templates,
                )
                source = "live"
                if write_cache:
                    written = save_snapshot(snapshot)

        health = build_project_health(snapshot=snapshot, previous_snapshot=previous_snapshot)
        if source == "cache":
            cached_diff = load_latest_diff_cache(profile=target_profile, project_id=target_project_id)
            if cached_diff and cached_diff.get("current_fingerprint") == health["summary"]["fingerprint"]:
                health["diff"] = cached_diff.get("diff") or health["diff"]
                health["summary"]["previous_fingerprint"] = cached_diff.get("previous_fingerprint")
                health["summary"]["changed_since_previous"] = bool(
                    cached_diff.get("previous_fingerprint")
                    and cached_diff.get("previous_fingerprint") != cached_diff.get("current_fingerprint")
                )
                health["diff_cache"] = {
                    "hit": True,
                    "path": cached_diff.get("path"),
                    "generated_at": cached_diff.get("generated_at"),
                }
            else:
                health["diff_cache"] = {"hit": False}
        elif write_cache and source == "live":
            diff_written = save_diff_cache(
                snapshot=snapshot,
                previous_snapshot=previous_snapshot,
                diff=health["diff"],
            )
            health["diff_cache"] = {"hit": False, "write": diff_written}

        health["source"] = source
        health["cache"] = {
            **cache_status,
            "enabled": use_cache,
            "hit": source == "cache",
            "refresh_requested": refresh,
            "refresh_reason": _cache_refresh_reason(
                source=source,
                refresh=refresh,
                use_cache=use_cache,
                cache_status=cache_status,
            ),
        }
        if written:
            health["cache_write"] = written
        if diff_written:
            health["diff_cache_write"] = diff_written
        return redact_sensitive(health)
    finally:
        if artifacts_dir:
            if old_artifacts_dir is None:
                os.environ.pop(ARTIFACTS_ENV, None)
            else:
                os.environ[ARTIFACTS_ENV] = old_artifacts_dir


def collect_live_health_inventory(
    *,
    profile: str | None,
    project_id: str | None,
    include_processes: bool = True,
    include_report_templates: bool = False,
) -> dict[str, Any]:
    config = AlteriosConfig.from_env(profile=profile).with_project_id(project_id)
    client = AlteriosClient(config)
    read_errors: list[dict[str, str]] = []

    forms = _read_items(lambda: client.list_forms(limit=5000).body, read_errors, "forms")
    scripts = _read_items(lambda: client.list_scripts(limit=5000).body, read_errors, "scripts")
    diagrams = _read_items(lambda: client.list_diagrams(limit=5000).body, read_errors, "diagrams")
    groups = _read_items(lambda: client.list_groups().body, read_errors, "groups")
    views = _read_items(lambda: client.list_views(limit=5000).body, read_errors, "views")
    reports = _read_items(lambda: client.list_reports(limit=5000).body, read_errors, "reports")

    processes_by_diagram: dict[str, list[dict[str, Any]]] = {}
    tasks_by_diagram: dict[str, list[dict[str, Any]]] = {}
    if include_processes:
        for diagram in diagrams:
            diagram_id = str(diagram.get("_id") or "")
            if not diagram_id:
                continue
            processes_by_diagram[diagram_id] = _read_items(
                lambda diagram_id=diagram_id: client.list_processes(diagram_id=diagram_id, limit=5000).body,
                read_errors,
                "processes",
                diagram_id=diagram_id,
            )
            tasks_by_diagram[diagram_id] = _read_items(
                lambda diagram_id=diagram_id: client.list_tasks(diagram_id=diagram_id).body,
                read_errors,
                "tasks",
                diagram_id=diagram_id,
            )

    full_reports: list[dict[str, Any]] = []
    if include_report_templates:
        for report in reports:
            report_id = str(report.get("_id") or "")
            if not report_id:
                continue
            try:
                full_reports.append(client.report_by_id(report_id).body)
            except Exception as exc:  # pragma: no cover - network/instance dependent.
                read_errors.append({"scope": "report_full", "report_id": report_id, "error": str(exc)})

    deep_inventory = build_deep_inventory(
        forms=forms,
        scripts=scripts,
        diagrams=diagrams,
        groups=groups,
        processes_by_diagram=processes_by_diagram,
        tasks_by_diagram=tasks_by_diagram,
        profile=profile,
        project_id=project_id,
        read_errors=read_errors,
    )
    return build_health_snapshot(
        deep_inventory=deep_inventory,
        views=views,
        reports=reports,
        full_reports=full_reports,
    )


def build_health_snapshot(
    *,
    deep_inventory: dict[str, Any],
    views: list[dict[str, Any]] | None = None,
    reports: list[dict[str, Any]] | None = None,
    full_reports: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    context = dict(deep_inventory.get("context") or {})
    generated_at = context.get("generated_at") or _utc_now()
    context["generated_at"] = generated_at
    return {
        "schema_version": PROJECT_HEALTH_SCHEMA_VERSION,
        "kind": "alterios_project_health_inventory",
        "context": context,
        "deep_inventory": deep_inventory,
        "project_objects": {
            "views": [_object_summary(item) for item in views or []],
            "reports": [_object_summary(item) for item in reports or []],
            "full_reports": [_report_template_summary(item) for item in full_reports or []],
        },
    }


def build_project_health(
    *,
    snapshot: dict[str, Any],
    previous_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    deep = snapshot.get("deep_inventory") or snapshot
    context = dict(snapshot.get("context") or deep.get("context") or {})
    forms = ((deep.get("form_surface_inventory") or {}).get("forms") or [])
    linkage = deep.get("script_bpmn_linkage") or {}
    project_objects = snapshot.get("project_objects") or {}
    issues: list[dict[str, Any]] = []

    _add_read_error_issues(issues, deep.get("read_errors") or [])
    _add_form_surface_issues(issues, forms)
    _add_form_action_ref_issues(issues, (deep.get("form_surface_inventory") or {}).get("action_matrix") or [], forms)
    _add_form_data_source_ref_issues(issues, forms, project_objects)
    _add_script_bpmn_issues(issues, linkage)
    _add_report_template_issues(issues, project_objects.get("full_reports") or [])

    summary = _issue_summary(issues)
    current_fingerprint = snapshot_fingerprint(snapshot)
    previous_fingerprint = snapshot_fingerprint(previous_snapshot) if previous_snapshot else None
    diff = diff_snapshots(previous_snapshot, snapshot) if previous_snapshot else {"available": False, "reason": "no previous snapshot"}
    health = {
        "kind": "alterios_project_health",
        "schema_version": PROJECT_HEALTH_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "readonly": True,
        "context": context,
        "summary": {
            "ok": not any(issue["severity"] == "error" for issue in issues),
            "issue_count": len(issues),
            "issues_by_severity": summary["by_severity"],
            "issues_by_area": summary["by_area"],
            "issues_by_code": summary["by_code"],
            "counts": _object_counts(snapshot),
            "fingerprint": current_fingerprint,
            "previous_fingerprint": previous_fingerprint,
            "changed_since_previous": bool(previous_fingerprint and previous_fingerprint != current_fingerprint),
        },
        "issues": issues,
        "diff": diff,
    }
    return health


def save_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    context = snapshot.get("context") or {}
    profile = str(context.get("profile") or "default")
    project_id = str(context.get("project_id") or "default")
    generated_at = str(context.get("generated_at") or _utc_now())
    directory = inventory_cache_dir(profile=profile, project_id=project_id)
    snapshot_dir = directory / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    name = _safe_component(generated_at.replace("+00:00", "Z")) + ".json"
    path = snapshot_dir / name
    _write_json(path, snapshot)
    latest_path = directory / "latest.json"
    _write_json(latest_path, snapshot)
    return {
        "path": _relative_artifact_path(path),
        "latest_path": _relative_artifact_path(latest_path),
        "fingerprint": snapshot_fingerprint(snapshot),
    }


def load_latest_snapshot(*, profile: str, project_id: str) -> dict[str, Any] | None:
    path = inventory_cache_dir(profile=profile or "default", project_id=project_id or "default") / "latest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_cache_ttl_seconds(value: int | None = None) -> int:
    raw_value: Any = value if value is not None else os.environ.get(HEALTH_CACHE_TTL_ENV, DEFAULT_HEALTH_CACHE_TTL_SECONDS)
    try:
        ttl_seconds = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{HEALTH_CACHE_TTL_ENV} must be a non-negative integer.") from exc
    if ttl_seconds < 0:
        raise ValueError("cache_ttl_seconds must be non-negative.")
    return ttl_seconds


def snapshot_cache_status(
    *,
    profile: str,
    project_id: str,
    ttl_seconds: int,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = inventory_cache_dir(profile=profile or "default", project_id=project_id or "default") / "latest.json"
    if snapshot is None or not path.exists():
        return {
            "available": False,
            "fresh": False,
            "ttl_seconds": ttl_seconds,
            "age_seconds": None,
            "path": _relative_artifact_path(path),
            "fingerprint": None,
        }
    age_seconds = max(0.0, datetime.now(timezone.utc).timestamp() - path.stat().st_mtime)
    return {
        "available": True,
        "fresh": age_seconds <= ttl_seconds,
        "ttl_seconds": ttl_seconds,
        "age_seconds": round(age_seconds, 3),
        "path": _relative_artifact_path(path),
        "fingerprint": snapshot_fingerprint(snapshot),
    }


def save_diff_cache(
    *,
    snapshot: dict[str, Any],
    previous_snapshot: dict[str, Any] | None,
    diff: dict[str, Any],
) -> dict[str, Any]:
    context = snapshot.get("context") or {}
    profile = str(context.get("profile") or "default")
    project_id = str(context.get("project_id") or "default")
    generated_at = _utc_now()
    directory = inventory_cache_dir(profile=profile, project_id=project_id)
    diff_dir = directory / "diffs"
    diff_dir.mkdir(parents=True, exist_ok=True)
    path = diff_dir / f"{_safe_component(generated_at)}.json"
    latest_path = directory / "latest-diff.json"
    payload = {
        "schema_version": PROJECT_HEALTH_DIFF_SCHEMA_VERSION,
        "kind": "alterios_project_health_diff",
        "generated_at": generated_at,
        "profile": profile,
        "project_id": project_id,
        "current_fingerprint": snapshot_fingerprint(snapshot),
        "previous_fingerprint": snapshot_fingerprint(previous_snapshot),
        "diff": diff,
    }
    _write_json(path, payload)
    _write_json(latest_path, payload)
    return {
        "path": _relative_artifact_path(path),
        "latest_path": _relative_artifact_path(latest_path),
        "current_fingerprint": payload["current_fingerprint"],
        "previous_fingerprint": payload["previous_fingerprint"],
    }


def load_latest_diff_cache(*, profile: str, project_id: str) -> dict[str, Any] | None:
    path = inventory_cache_dir(profile=profile or "default", project_id=project_id or "default") / "latest-diff.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["path"] = _relative_artifact_path(path)
    return payload


def inventory_cache_dir(*, profile: str, project_id: str) -> Path:
    return artifact_root() / "inventories" / _safe_component(profile or "default") / _safe_component(project_id or "default")


def artifact_root() -> Path:
    return Path(os.environ.get(ARTIFACTS_ENV, "artifacts")).resolve()


def snapshot_fingerprint(snapshot: dict[str, Any] | None) -> str | None:
    if not snapshot:
        return None
    payload = _fingerprint_payload(snapshot)
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def diff_snapshots(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    if not previous:
        return {"available": False, "reason": "no previous snapshot"}
    result: dict[str, Any] = {"available": True, "changed": False, "entities": {}}
    for key in ("forms", "scripts", "diagrams", "views", "reports"):
        before = _entity_fingerprints(previous, key)
        after = _entity_fingerprints(current, key)
        added = sorted(set(after) - set(before))
        removed = sorted(set(before) - set(after))
        changed = sorted(item for item in set(before) & set(after) if before[item] != after[item])
        result["entities"][key] = {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "added_ids": added[:20],
            "removed_ids": removed[:20],
            "changed_ids": changed[:20],
        }
        if added or removed or changed:
            result["changed"] = True
    return result


def render_markdown(health: dict[str, Any]) -> str:
    summary = health.get("summary") or {}
    status = "OK" if summary.get("ok") else "ISSUES"
    lines = [
        "# Alterios Project Health",
        "",
        f"- status: {status}",
        f"- generated_at: `{health.get('generated_at')}`",
        f"- source: `{health.get('source', 'unknown')}`",
        f"- issue_count: `{summary.get('issue_count', 0)}`",
    ]
    counts = summary.get("counts") or {}
    if counts:
        lines.append(
            "- counts: "
            + ", ".join(f"{key}={value}" for key, value in counts.items())
        )
    if health.get("diff", {}).get("available"):
        lines.append(f"- changed_since_previous: `{summary.get('changed_since_previous')}`")
    lines.extend(["", "| Severity | Area | Code | Path |", "|---|---|---|---|"])
    for issue in health.get("issues", [])[:50]:
        lines.append(f"| `{issue['severity']}` | `{issue['area']}` | `{issue['code']}` | `{issue.get('path', '')}` |")
    if not health.get("issues"):
        lines.append("| ok | - | - | - |")
    return "\n".join(lines) + "\n"


def _read_items(
    reader: Any,
    read_errors: list[dict[str, str]],
    scope: str,
    **extra: str,
) -> list[dict[str, Any]]:
    try:
        return inventory_items(reader())
    except Exception as exc:  # pragma: no cover - network/instance dependent.
        read_errors.append({"scope": scope, **extra, "error": str(exc)})
        return []


def _add_read_error_issues(issues: list[dict[str, Any]], read_errors: list[dict[str, Any]]) -> None:
    for error in read_errors:
        _add_issue(
            issues,
            "error",
            "inventory_read_error",
            "inventory",
            f"Read failed for {error.get('scope')}.",
            path=str(error.get("diagram_id") or error.get("report_id") or error.get("scope") or ""),
            details=error,
        )


def _add_form_surface_issues(issues: list[dict[str, Any]], forms: list[dict[str, Any]]) -> None:
    for form in forms:
        check = form.get("surface_check") or {}
        if not check.get("issue_count"):
            continue
        severity = "error" if (check.get("issues_by_severity") or {}).get("error") else "warning"
        _add_issue(
            issues,
            severity,
            "form_surface_static_issues",
            "forms",
            "Form has static surface issues before write.",
            path=f"forms[{form.get('form_id')}]",
            details={
                "form_id": form.get("form_id"),
                "name": form.get("name"),
                "issues_by_code": check.get("issues_by_code"),
                "issues_by_severity": check.get("issues_by_severity"),
            },
        )


def _add_form_action_ref_issues(issues: list[dict[str, Any]], actions: list[dict[str, Any]], forms: list[dict[str, Any]]) -> None:
    form_ids = {str(form.get("form_id")) for form in forms if form.get("form_id")}
    for action in actions:
        if action.get("category") == "open_form" and action.get("target_form_id") and str(action.get("target_form_id")) not in form_ids:
            _add_issue(
                issues,
                "error",
                "missing_form_action_target",
                "forms",
                "Form action points to a missing form.",
                path=str(action.get("path") or ""),
                details={"target_form_id": action.get("target_form_id"), "form_id": action.get("form_id")},
            )


def _add_form_data_source_ref_issues(issues: list[dict[str, Any]], forms: list[dict[str, Any]], project_objects: dict[str, Any]) -> None:
    view_ids = {str(item.get("_id")) for item in project_objects.get("views") or [] if item.get("_id")}
    report_ids = {str(item.get("_id")) for item in project_objects.get("reports") or [] if item.get("_id")}
    for form in forms:
        for cell in form.get("cells") or []:
            view_id = cell.get("viewId")
            if view_id and view_ids and str(view_id) not in view_ids:
                _add_issue(
                    issues,
                    "error",
                    "missing_view_ref",
                    "views",
                    "Form cell references a missing view.",
                    path=str(cell.get("path") or ""),
                    details={"form_id": form.get("form_id"), "view_id": view_id},
                )
            report_id = cell.get("reportId")
            if report_id and report_ids and str(report_id) not in report_ids:
                _add_issue(
                    issues,
                    "error",
                    "missing_report_ref",
                    "reports",
                    "Form cell references a missing report.",
                    path=str(cell.get("path") or ""),
                    details={"form_id": form.get("form_id"), "report_id": report_id},
                )


def _add_script_bpmn_issues(issues: list[dict[str, Any]], linkage: dict[str, Any]) -> None:
    for link in linkage.get("form_script_links") or []:
        if not link.get("script_match"):
            _add_issue(
                issues,
                "error",
                "missing_form_script_ref",
                "scripts",
                "Form action points to a missing script.",
                path=str(link.get("path") or ""),
                details={"target_script_id": link.get("target_script_id"), "target_script_name": link.get("target_script_name")},
            )
    for link in linkage.get("user_task_form_links") or []:
        if not link.get("form_match"):
            _add_issue(
                issues,
                "error",
                "missing_bpmn_form_key",
                "bpmn",
                "BPMN userTask formKey points to a missing form.",
                path=f"diagrams[{link.get('diagram_id')}].nodes[{link.get('node_id')}]",
                details={"form_key": link.get("form_key")},
            )
    for ref in linkage.get("diagram_script_refs") or []:
        if not ref.get("script_match"):
            _add_issue(
                issues,
                "error",
                "missing_bpmn_script_ref",
                "bpmn",
                "BPMN node/listener points to a missing script.",
                path=f"diagrams[{ref.get('diagram_id')}]",
                details={"ref": ref.get("ref")},
            )
    for diagram in linkage.get("diagrams") or []:
        if diagram.get("parse_error"):
            _add_issue(
                issues,
                "error",
                "bpmn_parse_error",
                "bpmn",
                "BPMN XML cannot be parsed.",
                path=f"diagrams[{diagram.get('diagram_id')}]",
                details={"parse_error": diagram.get("parse_error"), "name": diagram.get("name")},
            )


def _add_report_template_issues(issues: list[dict[str, Any]], reports: list[dict[str, Any]]) -> None:
    for report in reports:
        template = report.get("template")
        if template is None:
            continue
        try:
            layout = analyze_stimulsoft_layout(report)
        except Exception as exc:
            _add_issue(
                issues,
                "error",
                "report_template_parse_error",
                "reports",
                "Report template cannot be parsed for layout validation.",
                path=f"reports[{report.get('_id')}]",
                details={"error": str(exc), "name": report.get("name")},
            )
            continue
        if not layout.get("ok"):
            _add_issue(
                issues,
                "error",
                "report_layout_issues",
                "reports",
                "Report has blocking static Stimulsoft layout issues.",
                path=f"reports[{report.get('_id')}]",
                details={"name": report.get("name"), "issues_by_code": layout.get("issues_by_code")},
            )


def _add_issue(
    issues: list[dict[str, Any]],
    severity: str,
    code: str,
    area: str,
    message: str,
    *,
    path: str,
    details: dict[str, Any] | None = None,
) -> None:
    issue: dict[str, Any] = {"severity": severity, "area": area, "code": code, "message": message, "path": path}
    if details:
        issue["details"] = details
    issues.append(issue)


def _issue_summary(issues: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    return {
        "by_severity": dict(sorted(Counter(issue["severity"] for issue in issues).items())),
        "by_area": dict(sorted(Counter(issue["area"] for issue in issues).items())),
        "by_code": dict(sorted(Counter(issue["code"] for issue in issues).items())),
    }


def _object_counts(snapshot: dict[str, Any]) -> dict[str, int]:
    deep = snapshot.get("deep_inventory") or snapshot
    form_totals = (deep.get("form_surface_inventory") or {}).get("totals") or {}
    linkage_totals = (deep.get("script_bpmn_linkage") or {}).get("totals") or {}
    project_objects = snapshot.get("project_objects") or {}
    return {
        "forms": int(form_totals.get("forms") or 0),
        "scripts": int(linkage_totals.get("scripts") or 0),
        "diagrams": int(linkage_totals.get("diagrams") or 0),
        "views": len(project_objects.get("views") or []),
        "reports": len(project_objects.get("reports") or []),
    }


def _fingerprint_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {key: _entity_fingerprints(snapshot, key) for key in ("forms", "scripts", "diagrams", "views", "reports")}


def _entity_fingerprints(snapshot: dict[str, Any], entity: str) -> dict[str, str]:
    deep = snapshot.get("deep_inventory") or snapshot
    project_objects = snapshot.get("project_objects") or {}
    if entity == "forms":
        rows = (deep.get("form_surface_inventory") or {}).get("forms") or []
        return {
            str(row.get("form_id")): _digest(
                {
                    "name": row.get("name"),
                    "version": row.get("version"),
                    "cell_count": row.get("cell_count"),
                    "action_count": row.get("action_count"),
                    "surface_check": row.get("surface_check"),
                }
            )
            for row in rows
            if row.get("form_id")
        }
    if entity == "scripts":
        rows = (deep.get("script_bpmn_linkage") or {}).get("scripts") or []
        return {
            str(row.get("script_id")): _digest(
                {"name": row.get("name"), "type": row.get("type"), "version": row.get("version"), "body_sha256": row.get("body_sha256")}
            )
            for row in rows
            if row.get("script_id")
        }
    if entity == "diagrams":
        rows = (deep.get("script_bpmn_linkage") or {}).get("diagrams") or []
        return {
            str(row.get("diagram_id")): _digest(
                {"name": row.get("name"), "version": row.get("version"), "xml_sha256": row.get("xml_sha256"), "parse_error": row.get("parse_error")}
            )
            for row in rows
            if row.get("diagram_id")
        }
    if entity in {"views", "reports"}:
        return {
            str(row.get("_id")): _digest({"name": row.get("name"), "version": row.get("version"), "updatedAt": row.get("updatedAt")})
            for row in project_objects.get(entity) or []
            if row.get("_id")
        }
    return {}


def _object_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "_id": item.get("_id"),
        "name": item.get("name") or item.get("title"),
        "version": item.get("version"),
        "updatedAt": item.get("updatedAt") or item.get("updated_at"),
        "contentTypeId": item.get("contentTypeId"),
    }


def _report_template_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "_id": report.get("_id"),
        "name": report.get("name") or report.get("title"),
        "version": report.get("version"),
        "template": report.get("template"),
    }


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact_sensitive(payload), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _relative_artifact_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(artifact_root()))
    except ValueError:
        return str(path)


def _safe_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned[:120] or "default"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _cache_refresh_reason(
    *,
    source: str,
    refresh: bool,
    use_cache: bool,
    cache_status: dict[str, Any],
) -> str | None:
    if source != "live":
        return None
    if refresh:
        return "refresh_requested"
    if not use_cache:
        return "cache_disabled"
    if not cache_status.get("available"):
        return "cache_miss"
    if not cache_status.get("fresh"):
        return "cache_expired"
    return "live_required"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a read-only Alterios project health summary.")
    parser.add_argument("--profile", default=None, help="Alterios profile.")
    parser.add_argument("--project-id", default=None, help="Alterios project/workspace id.")
    parser.add_argument("--refresh", action="store_true", help="Read live project state instead of using latest cache.")
    parser.add_argument("--no-cache", action="store_true", help="Do not read an existing cache snapshot.")
    parser.add_argument("--no-write-cache", action="store_true", help="Do not write a new local cache snapshot after live read.")
    parser.add_argument(
        "--cache-ttl-seconds",
        type=int,
        default=None,
        help=f"Maximum cache age; defaults to {HEALTH_CACHE_TTL_ENV} or {DEFAULT_HEALTH_CACHE_TTL_SECONDS} seconds.",
    )
    parser.add_argument("--include-processes", action=argparse.BooleanOptionalAction, default=True, help="Include process/task readback per diagram.")
    parser.add_argument("--include-report-templates", action="store_true", help="Fetch full report templates for static layout health.")
    parser.add_argument("--artifacts-dir", default=None, help="Override local artifacts root.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of markdown.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    args = parser.parse_args(argv)

    try:
        result = run_project_health(
            profile=args.profile,
            project_id=args.project_id,
            refresh=args.refresh,
            use_cache=not args.no_cache,
            write_cache=not args.no_write_cache,
            cache_ttl_seconds=args.cache_ttl_seconds,
            include_processes=args.include_processes,
            include_report_templates=args.include_report_templates,
            artifacts_dir=args.artifacts_dir,
    )
    except (AlteriosConfigError, AlteriosRequestError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    else:
        print(render_markdown(result), end="")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
