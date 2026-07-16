from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any

from .client import (
    AlteriosClient,
    AlteriosConfig,
    AlteriosConfigError,
    AlteriosRequestError,
    configured_profiles,
    encode_filter,
)


@dataclass(frozen=True)
class ReadonlyRoute:
    name: str
    method: str
    path: str
    params: dict[str, Any] | None = None
    body: Any | None = None
    description: str = ""
    requires_project: bool = True


READONLY_ROUTES: tuple[ReadonlyRoute, ...] = (
    ReadonlyRoute("projects", "GET", "/api/projects/listandcount", {"limit": 1, "offset": 0}, requires_project=False),
    ReadonlyRoute("content_types", "GET", "/api/content-types/listandcount", {"limit": 1, "offset": 0}),
    ReadonlyRoute("fields", "GET", "/api/fields", {"limit": 1, "offset": 0}),
    ReadonlyRoute("views", "GET", "/api/views/listandcount", {"limit": 1, "offset": 0}),
    ReadonlyRoute("forms", "GET", "/api/forms/listandcount", {"limit": 1, "offset": 0}),
    ReadonlyRoute("scripts", "GET", "/api/scripts/listandcount", {"limit": 1, "offset": 0}),
    ReadonlyRoute("diagrams", "GET", "/api/diagrams/listandcount", {"limit": 1, "offset": 0}),
    ReadonlyRoute("contents", "GET", "/api/contents/listandcount", {"limit": 1, "offset": 0}),
    ReadonlyRoute("tasks", "GET", "/api/tasks/listandcount", {"limit": 1, "offset": 0}),
    ReadonlyRoute("processes", "GET", "/api/processes/listandcount", {"limit": 1, "offset": 0}),
    ReadonlyRoute("reports", "GET", "/api/reports/listandcount/" + encode_filter({}), {"limit": 1, "offset": 0}),
    ReadonlyRoute("user_groups", "GET", "/api/user-groups/listandcount", {"limit": 1, "offset": 0}),
    ReadonlyRoute("users", "GET", "/api/users/listandcount", {"limit": 1, "offset": 0}),
    ReadonlyRoute("groups", "GET", "/api/groups", {"limit": 1, "offset": 0}),
    ReadonlyRoute("helps", "GET", "/api/helps", {"limit": 1, "offset": 0}),
)

OBJECT_ROUTES: dict[str, ReadonlyRoute] = {route.name: route for route in READONLY_ROUTES}


def discover_readonly(client: AlteriosClient) -> dict[str, Any]:
    results = []
    for route in READONLY_ROUTES:
        result: dict[str, Any] = {
            "name": route.name,
            "method": route.method,
            "path": route.path,
            "readonly": True,
        }
        try:
            response = client.request(
                route.method,
                route.path,
                params=route.params,
                body=route.body,
                requires_project=route.requires_project,
            )
            result.update(
                {
                    "ok": True,
                    "status_code": response.status_code,
                    "content_type": response.content_type,
                    "shape": response_shape(response.body),
                }
            )
        except (AlteriosConfigError, AlteriosRequestError) as exc:
            result.update({"ok": False, "error": str(exc)})
        results.append(result)

    return {"profile": client.config.profile or "<default>", "routes": results}


def list_objects(client: AlteriosClient, kind: str, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    route = OBJECT_ROUTES.get(kind)
    if route is None:
        known = ", ".join(sorted(OBJECT_ROUTES))
        raise ValueError(f"Unknown object kind '{kind}'. Known kinds: {known}")

    params = dict(route.params or {})
    params["limit"] = limit
    params["offset"] = offset
    response = client.request(
        route.method,
        route.path,
        params=params,
        body=route.body,
        requires_project=route.requires_project,
    )
    return response.as_dict()


def list_projects(client: AlteriosClient, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    response = client.request(
        "GET",
        "/api/projects/listandcount",
        params={"limit": limit, "offset": offset},
        requires_project=False,
    )
    return response.as_dict()


def response_shape(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        return {"type": "list", "length": len(value), "first": response_shape(value[0]) if value else None}
    if isinstance(value, dict):
        return {"type": "dict", "keys": sorted(str(key) for key in value.keys())[:30]}
    return {"type": type(value).__name__}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run read-only Alterios endpoint discovery.")
    parser.add_argument("--profile", help="Alterios profile, e.g. primary or secondary.")
    parser.add_argument("--project-id", help="Explicit Alterios project id for project-scoped probes.")
    parser.add_argument("--profiles", action="store_true", help="List configured Alterios instance profiles only.")
    parser.add_argument("--projects", action="store_true", help="List projects only.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args(argv)

    try:
        if args.profiles:
            payload = configured_profiles(selected_profile=args.profile)
        else:
            client = AlteriosClient(AlteriosConfig.from_env(profile=args.profile).with_project_id(args.project_id))
            payload = list_projects(client) if args.projects else discover_readonly(client)
    except AlteriosConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.profiles:
        for profile in payload["profiles"]:
            selected = "*" if profile["selected"] else " "
            missing = len(profile["missing_for_instance_call"])
            print(f"{selected} {profile['profile']}: instance_missing={missing} base_url={profile['config']['base_url']}")
    elif args.projects:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for route in payload["routes"]:
            status = "ok" if route["ok"] else "failed"
            print(f"{route['name']}: {status} {route.get('status_code', '')} {route['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
