from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import AlteriosClient, AlteriosConfig
from .discovery import discover_readonly, list_objects, list_projects
from .services import list_services, service_to_dict

mcp = FastMCP("alterios")


def _client(profile: str | None = None, project_id: str | None = None) -> AlteriosClient:
    return AlteriosClient(AlteriosConfig.from_env(profile=profile).with_project_id(project_id))


def _write_enabled() -> bool:
    return os.environ.get("ALTERIOS_MCP_ALLOW_WRITE") == "1"


@mcp.tool()
def alterios_config(profile: str | None = None) -> dict[str, Any]:
    """Return redacted Alterios configuration and missing required values."""
    config = AlteriosConfig.from_env(profile=profile)
    return {
        "config": config.redacted(),
        "missing_for_instance_call": config.missing_for_instance_call(),
        "missing_for_project_call": config.missing_for_project_call(),
        "missing_for_script_call": config.missing_for_script_call(),
        "write_enabled": _write_enabled(),
    }


@mcp.tool()
def alterios_list_projects(
    limit: int = 100,
    offset: int = 0,
    profile: str | None = None,
) -> dict[str, Any]:
    """List projects available on the selected Alterios instance."""
    return list_projects(_client(profile), limit=limit, offset=offset)


@mcp.tool()
def alterios_service_catalog(read_only: bool = True) -> list[dict[str, Any]]:
    """Return known Alterios script-service functions."""
    return [service_to_dict(service) for service in list_services(read_only=read_only)]


@mcp.tool()
def alterios_call_readonly_service(
    function: str,
    args: dict[str, Any] | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Call a known read-only Alterios script service."""
    return _client(profile, project_id).call_script_service(function, args or {}, allow_write=False).as_dict()


@mcp.tool()
def alterios_rest_get(
    path: str,
    params: dict[str, Any] | None = None,
    profile: str | None = None,
    project_id: str | None = None,
    requires_project: bool = True,
) -> dict[str, Any]:
    """Run a read-only GET request against an Alterios REST API path."""
    return _client(profile, project_id).request(
        "GET",
        path,
        params=params or {},
        requires_project=requires_project,
    ).as_dict()


@mcp.tool()
def alterios_list_objects(
    kind: str,
    limit: int = 20,
    offset: int = 0,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """List common Alterios object types via validated listandcount routes."""
    return list_objects(_client(profile, project_id), kind=kind, limit=limit, offset=offset)


@mcp.tool()
def alterios_view_data_simplified(
    view_id: str,
    limit: int = 20,
    offset: int = 0,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read a view as Stimulsoft usually sees it through get-data-simplified."""
    body = {"viewId": view_id, "limit": limit, "offset": offset}
    return _client(profile, project_id).request("POST", "/api/views/v2/get-data-simplified", body=body).as_dict()


@mcp.tool()
def alterios_discover_readonly(
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Probe the known safe read-only Alterios REST routes."""
    return discover_readonly(_client(profile, project_id))


@mcp.tool()
def alterios_call_write_service(
    function: str,
    args: dict[str, Any],
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Call a mutating Alterios script service. Requires ALTERIOS_MCP_ALLOW_WRITE=1."""
    if not _write_enabled():
        raise RuntimeError("Write calls are disabled. Set ALTERIOS_MCP_ALLOW_WRITE=1 explicitly.")
    return _client(profile, project_id).call_script_service(function, args, allow_write=True).as_dict()


@mcp.tool()
def alterios_execute_manual_script(
    script_id: str,
    args: dict[str, Any],
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Execute a manual Alterios script by UUID. Requires ALTERIOS_MCP_ALLOW_WRITE=1."""
    if not _write_enabled():
        raise RuntimeError("Manual script execution is disabled. Set ALTERIOS_MCP_ALLOW_WRITE=1 explicitly.")
    return _client(profile, project_id).call_script_service(
        script_id,
        args,
        body_style="manual_script",
        allow_write=True,
    ).as_dict()


@mcp.tool()
def alterios_rest_write(
    method: str,
    path: str,
    body: dict[str, Any],
    params: dict[str, Any] | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Run a mutating REST request. Requires ALTERIOS_MCP_ALLOW_WRITE=1."""
    method = method.upper()
    if method not in {"POST", "PUT", "DELETE"}:
        raise ValueError("alterios_rest_write supports only POST, PUT, and DELETE")
    if not _write_enabled():
        raise RuntimeError("Write calls are disabled. Set ALTERIOS_MCP_ALLOW_WRITE=1 explicitly.")
    return _client(profile, project_id).request(method, path, params=params or {}, body=body).as_dict()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
