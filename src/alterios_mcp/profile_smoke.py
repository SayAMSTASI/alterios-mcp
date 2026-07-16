from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .client import (
    AlteriosClient,
    AlteriosConfig,
    AlteriosConfigError,
    AlteriosRequestError,
    configured_profiles,
    listandcount_items,
    redact_sensitive,
    safe_error,
)
from .discovery import discover_readonly, list_projects, response_shape


def run_profile_smoke(
    *,
    selected_profile: str | None = None,
    project_limit: int = 100,
    include_project_discovery: bool = True,
    include_project_ids: bool = False,
    include_project_names: bool = False,
) -> dict[str, Any]:
    """Run read-only smoke checks across configured Alterios profiles."""
    profiles_payload = configured_profiles(selected_profile=selected_profile)
    matrix: dict[str, Any] = {
        "kind": "alterios_profile_smoke_matrix",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "readonly": True,
        "write_gate_enabled": os.environ.get("ALTERIOS_MCP_ALLOW_WRITE") == "1",
        "dangerous_write_gate_enabled": os.environ.get("ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE") == "1",
        "selected_profile": profiles_payload.get("selected_profile"),
        "profile_count": profiles_payload.get("profile_count", 0),
        "project_limit": project_limit,
        "include_project_ids": include_project_ids,
        "include_project_names": include_project_names,
        "profiles": [],
    }

    for profile in profiles_payload.get("profiles", []):
        profile_result = _profile_smoke(
            profile,
            project_limit=project_limit,
            include_project_discovery=include_project_discovery,
            include_project_ids=include_project_ids,
            include_project_names=include_project_names,
        )
        matrix["profiles"].append(profile_result)

    matrix["summary"] = _matrix_summary(matrix)
    return matrix


def _profile_smoke(
    profile: dict[str, Any],
    *,
    project_limit: int,
    include_project_discovery: bool,
    include_project_ids: bool,
    include_project_names: bool,
) -> dict[str, Any]:
    profile_argument = profile.get("profile_argument")
    result: dict[str, Any] = {
        "profile": profile.get("profile"),
        "profile_argument": profile_argument,
        "selected": bool(profile.get("selected")),
        "config": _public_config(profile.get("config") or {}),
        "missing_for_instance_call": list(profile.get("missing_for_instance_call") or []),
        "missing_for_project_call": list(profile.get("missing_for_project_call") or []),
        "has_project_default": bool(profile.get("has_project_default")),
        "instance_project_list": {"ok": False, "skipped": False},
        "default_project_discovery": {"ok": False, "skipped": False},
    }

    if result["missing_for_instance_call"]:
        result["instance_project_list"] = {
            "ok": False,
            "skipped": True,
            "reason": "missing instance configuration",
        }
        result["default_project_discovery"] = {
            "ok": False,
            "skipped": True,
            "reason": "missing instance configuration",
        }
        return result

    try:
        config = AlteriosConfig.from_env(profile=profile_argument)
        client = AlteriosClient(config)
    except AlteriosConfigError as exc:
        result["instance_project_list"] = {"ok": False, "error": str(exc)}
        result["default_project_discovery"] = {
            "ok": False,
            "skipped": True,
            "reason": "profile config did not load",
        }
        return result

    result["instance_project_list"] = _project_list_smoke(
        client,
        project_limit=project_limit,
        include_project_ids=include_project_ids,
        include_project_names=include_project_names,
    )

    if not include_project_discovery:
        result["default_project_discovery"] = {
            "ok": False,
            "skipped": True,
            "reason": "project discovery disabled by caller",
        }
    elif result["missing_for_project_call"]:
        result["default_project_discovery"] = {
            "ok": False,
            "skipped": True,
            "reason": "missing default project configuration",
        }
    else:
        result["default_project_discovery"] = _default_project_discovery_smoke(client)

    return result


def _project_list_smoke(
    client: AlteriosClient,
    *,
    project_limit: int,
    include_project_ids: bool,
    include_project_names: bool,
) -> dict[str, Any]:
    try:
        response = list_projects(client, limit=project_limit, offset=0)
        body = response.get("body")
        items = _safe_items(body)
        return {
            "ok": response.get("status_code") in {200, 201},
            "skipped": False,
            "status_code": response.get("status_code"),
            "content_type": response.get("content_type"),
            "shape": response_shape(body),
            "returned_count": len(items),
            "project_count": _listandcount_total(body, default=len(items)),
            "sample_projects": _project_summaries(
                items,
                include_project_ids=include_project_ids,
                include_project_names=include_project_names,
                limit=min(project_limit, 20),
            ),
        }
    except (AlteriosConfigError, AlteriosRequestError) as exc:
        return {"ok": False, "skipped": False, "error": str(exc)}


def _default_project_discovery_smoke(client: AlteriosClient) -> dict[str, Any]:
    try:
        discovery = discover_readonly(client)
    except (AlteriosConfigError, AlteriosRequestError) as exc:
        return {"ok": False, "skipped": False, "error": str(exc)}

    routes = discovery.get("routes") if isinstance(discovery, dict) else []
    route_summaries = [_route_summary(route) for route in routes if isinstance(route, dict)]
    ok_count = sum(1 for route in route_summaries if route.get("ok"))
    failed_routes = [route for route in route_summaries if not route.get("ok")]
    return {
        "ok": ok_count == len(route_summaries) and bool(route_summaries),
        "skipped": False,
        "project_id": _presence(getattr(getattr(client, "config", None), "project_id", "")),
        "route_count": len(route_summaries),
        "ok_route_count": ok_count,
        "failed_route_count": len(failed_routes),
        "failed_routes": failed_routes,
        "routes": route_summaries,
    }


def _route_summary(route: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "name": route.get("name"),
        "method": route.get("method"),
        "path": route.get("path"),
        "ok": bool(route.get("ok")),
        "status_code": route.get("status_code"),
        "shape": route.get("shape"),
    }
    if route.get("error"):
        summary["error"] = safe_error(redact_sensitive(route.get("error")))
    return summary


def _matrix_summary(matrix: dict[str, Any]) -> dict[str, Any]:
    profiles = matrix.get("profiles") or []
    instance_ok = sum(1 for profile in profiles if (profile.get("instance_project_list") or {}).get("ok"))
    default_ok = sum(1 for profile in profiles if (profile.get("default_project_discovery") or {}).get("ok"))
    skipped_default = sum(
        1 for profile in profiles if (profile.get("default_project_discovery") or {}).get("skipped")
    )
    project_total = sum(
        int((profile.get("instance_project_list") or {}).get("project_count") or 0)
        for profile in profiles
        if (profile.get("instance_project_list") or {}).get("ok")
    )
    return {
        "profiles_total": len(profiles),
        "instance_project_list_ok": instance_ok,
        "default_project_discovery_ok": default_ok,
        "default_project_discovery_skipped": skipped_default,
        "project_count_total": project_total,
        "all_instance_project_lists_ok": instance_ok == len(profiles) if profiles else False,
        "all_default_project_discovery_ok_or_skipped": all(
            (profile.get("default_project_discovery") or {}).get("ok")
            or (profile.get("default_project_discovery") or {}).get("skipped")
            for profile in profiles
        )
        if profiles
        else False,
    }


def _public_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile": config.get("profile"),
        "base_url": _presence(config.get("base_url")),
        "api_token": config.get("api_token", "<missing>"),
        "project_id": _presence(config.get("project_id")),
        "endpoint_template": _presence(config.get("endpoint_template")),
        "body_style": config.get("body_style"),
        "auth_header": config.get("auth_header"),
        "auth_scheme": config.get("auth_scheme"),
        "timeout_seconds": config.get("timeout_seconds"),
    }


def _presence(value: Any) -> str:
    return "<set>" if str(value or "").strip() else "<missing>"


def _safe_items(payload: Any) -> list[dict[str, Any]]:
    try:
        return listandcount_items(payload)
    except AlteriosRequestError:
        return []


def _listandcount_total(payload: Any, *, default: int) -> int:
    if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], int):
        return payload[1]
    if isinstance(payload, dict):
        for key in ("total", "count", "totalCount"):
            value = payload.get(key)
            if isinstance(value, int):
                return value
    return default


def _project_summaries(
    projects: list[dict[str, Any]],
    *,
    include_project_ids: bool,
    include_project_names: bool,
    limit: int,
) -> list[dict[str, Any]]:
    if not include_project_ids and not include_project_names:
        return []
    summaries = []
    for project in projects[:limit]:
        summary = {"_id": project.get("_id")} if include_project_ids or include_project_names else {}
        if include_project_names:
            summary["name"] = project.get("name")
        summaries.append(summary)
    return summaries


def render_markdown(matrix: dict[str, Any]) -> str:
    summary = matrix.get("summary") or {}
    lines = [
        "# Profile Smoke Matrix",
        "",
        f"- Generated at: `{matrix.get('generated_at')}`",
        f"- Read-only run: `{matrix.get('readonly')}`",
        f"- Write gate enabled in environment: `{matrix.get('write_gate_enabled')}`",
        f"- Dangerous write gate enabled in environment: `{matrix.get('dangerous_write_gate_enabled')}`",
        f"- Project IDs included: `{matrix.get('include_project_ids')}`",
        f"- Project names included: `{matrix.get('include_project_names')}`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Profiles total | {summary.get('profiles_total', 0)} |",
        f"| Instance project lists OK | {summary.get('instance_project_list_ok', 0)} |",
        f"| Default project discovery OK | {summary.get('default_project_discovery_ok', 0)} |",
        f"| Default project discovery skipped | {summary.get('default_project_discovery_skipped', 0)} |",
        f"| Projects discovered total | {summary.get('project_count_total', 0)} |",
        "",
        "## Profiles",
        "",
        "| Profile | Token | Base URL | Default project | Projects | Default route smoke |",
        "|---|---|---|---|---:|---|",
    ]

    for profile in matrix.get("profiles") or []:
        config = profile.get("config") or {}
        projects = profile.get("instance_project_list") or {}
        discovery = profile.get("default_project_discovery") or {}
        route_smoke = _route_smoke_cell(discovery)
        lines.append(
            "| {profile} | {token_status} | {base_url} | {project_id} | {projects} | {routes} |".format(
                profile=profile.get("profile"),
                token_status=config.get("api_token"),
                base_url=config.get("base_url"),
                project_id=config.get("project_id") or "-",
                projects=projects.get("project_count", "-") if projects.get("ok") else projects.get("reason", "failed"),
                routes=route_smoke,
            )
        )

    failures = _profile_failures(matrix)
    lines.extend(["", "## Failures And Skips", ""])
    if failures:
        for failure in failures:
            lines.append(f"- `{failure['profile']}`: {failure['area']} - {failure['message']}")
    else:
        lines.append("- No failed checks. Some project-scoped discovery may still be skipped when a profile has no default project id.")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This runner calls only read-only inventory routes.",
            "- Tokens, auth headers, private dotenv contents, and base URLs are not written to this artifact.",
            "- Project IDs and names are omitted unless the runner is called with `--include-project-ids` or `--include-project-names`.",
        ]
    )
    return "\n".join(lines) + "\n"


def _route_smoke_cell(discovery: dict[str, Any]) -> str:
    if discovery.get("skipped"):
        return "skipped"
    if not discovery.get("ok"):
        return "failed"
    return f"{discovery.get('ok_route_count', 0)}/{discovery.get('route_count', 0)} OK"


def _profile_failures(matrix: dict[str, Any]) -> list[dict[str, str]]:
    failures = []
    for profile in matrix.get("profiles") or []:
        profile_name = str(profile.get("profile"))
        projects = profile.get("instance_project_list") or {}
        discovery = profile.get("default_project_discovery") or {}
        if not projects.get("ok"):
            failures.append(
                {
                    "profile": profile_name,
                    "area": "project list",
                    "message": str(projects.get("reason") or projects.get("error") or "failed"),
                }
            )
        if discovery.get("skipped"):
            failures.append(
                {
                    "profile": profile_name,
                    "area": "default project discovery",
                    "message": str(discovery.get("reason") or "skipped"),
                }
            )
        elif not discovery.get("ok"):
            failures.append(
                {
                    "profile": profile_name,
                    "area": "default project discovery",
                    "message": str(discovery.get("error") or "failed"),
                }
            )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run read-only smoke checks across configured Alterios profiles.")
    parser.add_argument("--profile", help="Profile to mark as selected while preserving full profile inventory.")
    parser.add_argument("--project-limit", type=int, default=100, help="Maximum projects to request per profile.")
    parser.add_argument("--skip-project-discovery", action="store_true", help="Skip default project route discovery.")
    parser.add_argument("--include-project-ids", action="store_true", help="Include project ids in JSON output.")
    parser.add_argument("--include-project-names", action="store_true", help="Include project names in JSON output.")
    parser.add_argument("--out-json", help="Write JSON matrix to this path.")
    parser.add_argument("--out-md", help="Write Markdown summary to this path.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    args = parser.parse_args(argv)

    if args.project_limit < 1:
        print("error: --project-limit must be positive", file=sys.stderr)
        return 2

    matrix = run_profile_smoke(
        selected_profile=args.profile,
        project_limit=args.project_limit,
        include_project_discovery=not args.skip_project_discovery,
        include_project_ids=args.include_project_ids,
        include_project_names=args.include_project_names,
    )

    if args.out_json:
        _write_text(args.out_json, json.dumps(matrix, ensure_ascii=False, indent=2) + "\n")
    if args.out_md:
        _write_text(args.out_md, render_markdown(matrix))

    if args.json:
        print(json.dumps(matrix, ensure_ascii=False, indent=2))
    elif not args.out_md:
        print(render_markdown(matrix))
    return 0


def _write_text(path: str, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
