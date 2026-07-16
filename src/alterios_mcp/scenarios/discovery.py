from __future__ import annotations

from .._support import *

def alterios_list_projects(
    limit: int = 100,
    offset: int = 0,
    profile: str | None = None,
) -> dict[str, Any]:
    """List projects available on the selected Alterios instance."""
    return list_projects(_client(profile), limit=limit, offset=offset)

def alterios_service_catalog(read_only: bool = True) -> list[dict[str, Any]]:
    """Return known Alterios script-service functions."""
    return [service_to_dict(service) for service in list_services(read_only=read_only)]

def alterios_call_readonly_service(
    function: str,
    args: dict[str, Any] | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Call a known read-only Alterios script service."""
    return _client(profile, project_id).call_script_service(function, args or {}, allow_write=False).as_dict()

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

def alterios_list_objects(
    kind: str,
    limit: int = 20,
    offset: int = 0,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """List common Alterios object types via validated listandcount routes."""
    return list_objects(_client(profile, project_id), kind=kind, limit=limit, offset=offset)

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

def alterios_report_full(
    report_id: str,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read a full Alterios report by ID through the encoded report filter route."""
    return _client(profile, project_id).report_full(report_id).as_dict()

def alterios_get_view(
    view_id: str,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read a full Alterios view object by ID."""
    return _client(profile, project_id).view_full(view_id).as_dict()

def alterios_get_form(
    form_id: str,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read a full Alterios form object by ID."""
    return _client(profile, project_id).form_full(form_id).as_dict()

def alterios_view_entities(
    view_id: str,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read configured entities/joins for an Alterios view."""
    return _client(profile, project_id).view_entities(view_id).as_dict()

def alterios_view_fields_populated(
    view_id: str,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read populated field metadata for an Alterios view."""
    return _client(profile, project_id).view_fields_populated(view_id).as_dict()

def alterios_list_fields(
    content_type_id: str | None = None,
    field_id: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read Alterios content type fields, optionally filtered by content type or field ID."""
    return _client(profile, project_id).list_fields(
        content_type_id=content_type_id,
        field_id=field_id,
        limit=limit,
        offset=offset,
    ).as_dict()

def alterios_list_groups(
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read Alterios project groups."""
    return _client(profile, project_id).list_groups().as_dict()

def alterios_list_content_types(
    limit: int = 1000,
    offset: int = 0,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read Alterios content types through the typed listandcount route."""
    return _client(profile, project_id).list_content_types(limit=limit, offset=offset).as_dict()

def alterios_list_users(
    limit: int = 1000,
    offset: int = 0,
    search: str | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read Alterios users through the typed security listandcount route."""
    response = _client(profile, project_id).list_users(limit=limit, offset=offset)
    return _listandcount_tool_response(response, search=search, keys=("_id", "name", "email", "firstName", "lastName"))

def alterios_get_user(
    user_id: str,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read one Alterios user by ID through the typed security route."""
    return _client(profile, project_id).user_by_id(user_id).as_dict()

def alterios_list_user_groups(
    limit: int = 1000,
    offset: int = 0,
    search: str | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read Alterios user groups through the typed security listandcount route."""
    response = _client(profile, project_id).list_user_groups(limit=limit, offset=offset)
    return _listandcount_tool_response(response, search=search, keys=("_id", "name", "description"))

def alterios_get_user_group(
    user_group_id: str,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read one Alterios user group by ID through the typed security route."""
    return _client(profile, project_id).user_group_by_id(user_group_id).as_dict()

def alterios_list_roles(
    limit: int = 1000,
    offset: int = 0,
    search: str | None = None,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read Alterios roles through the typed security listandcount route."""
    response = _client(profile, project_id).list_roles(limit=limit, offset=offset)
    return _listandcount_tool_response(response, search=search, keys=("_id", "name", "description", "code"))

def alterios_get_role(
    role_id: str,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read one Alterios role by ID through the typed security route."""
    return _client(profile, project_id).role_by_id(role_id).as_dict()

__all__ = ['alterios_list_projects', 'alterios_service_catalog', 'alterios_call_readonly_service', 'alterios_rest_get', 'alterios_list_objects', 'alterios_view_data_simplified', 'alterios_report_full', 'alterios_get_view', 'alterios_get_form', 'alterios_view_entities', 'alterios_view_fields_populated', 'alterios_list_fields', 'alterios_list_groups', 'alterios_list_content_types', 'alterios_list_users', 'alterios_get_user', 'alterios_list_user_groups', 'alterios_get_user_group', 'alterios_list_roles', 'alterios_get_role']
