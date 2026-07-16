from __future__ import annotations

from .._support import *

def alterios_upsert_user(
    payload: dict[str, Any],
    user_id: str | None = None,
    lookup_email: str | None = None,
    lookup_name: str | None = None,
    expected_email: str | None = None,
    allow_create: bool = False,
    dry_run: bool = True,
    allow_destructive: bool = False,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or create/update an Alterios user. Classified as security write."""
    client = _client(profile, project_id)
    existing = _find_user(client, user_id=user_id, email=lookup_email, name=lookup_name)
    if not existing and not allow_create:
        raise ValueError("User was not found; pass allow_create=True only after security review.")
    if existing and expected_email and str(existing.get("email") or "").lower() != expected_email.strip().lower():
        raise ValueError(f"User email mismatch: expected {expected_email!r}, got {existing.get('email')!r}.")
    resource_id = user_id or (str(existing.get("_id")) if existing and existing.get("_id") else None)
    planned_payload = _security_payload(existing, payload, resource_id)
    operation = _security_resource_operation(
        collection="users",
        action="upsert",
        kind="user",
        resource_id=resource_id,
        request=planned_payload,
        summary="Create or update an Alterios user and verify through user readback.",
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    response_payload: dict[str, Any] = {
        "preflight": _security_resource_summary(existing),
        "diff": _resource_diff(existing, planned_payload, tuple(sorted(planned_payload.keys()))),
        "planned_payload": strip_alterios_metadata(planned_payload),
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    saved = client.save_user(planned_payload).as_dict()
    saved_id = _extract_response_id(saved) or planned_payload.get("_id")
    readback = client.user_by_id(str(saved_id)).as_dict() if saved_id else None
    response_payload.update({"saved": saved, "readback": readback})
    return controlled_write_result(audit=audit, response=response_payload)

def alterios_upsert_user_group(
    payload: dict[str, Any],
    user_group_id: str | None = None,
    lookup_name: str | None = None,
    expected_name: str | None = None,
    allow_create: bool = False,
    dry_run: bool = True,
    allow_destructive: bool = False,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or create/update an Alterios user group. Classified as security write."""
    client = _client(profile, project_id)
    existing = _find_user_group(client, user_group_id=user_group_id, name=lookup_name)
    if not existing and not allow_create:
        raise ValueError("User group was not found; pass allow_create=True only after security review.")
    if existing and expected_name and existing.get("name") != expected_name:
        raise ValueError(f"User group name mismatch: expected {expected_name!r}, got {existing.get('name')!r}.")
    resource_id = user_group_id or (str(existing.get("_id")) if existing and existing.get("_id") else None)
    planned_payload = _security_payload(existing, payload, resource_id)
    operation = _security_resource_operation(
        collection="user-groups",
        action="upsert",
        kind="user_group",
        resource_id=resource_id,
        request=planned_payload,
        summary="Create or update an Alterios user group and verify through user-group readback.",
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    response_payload: dict[str, Any] = {
        "preflight": _security_resource_summary(existing),
        "diff": _resource_diff(existing, planned_payload, tuple(sorted(planned_payload.keys()))),
        "planned_payload": strip_alterios_metadata(planned_payload),
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    saved = client.save_user_group(planned_payload).as_dict()
    saved_id = _extract_response_id(saved) or planned_payload.get("_id")
    readback = client.user_group_by_id(str(saved_id)).as_dict() if saved_id else None
    response_payload.update({"saved": saved, "readback": readback})
    return controlled_write_result(audit=audit, response=response_payload)

def alterios_upsert_role(
    payload: dict[str, Any],
    role_id: str | None = None,
    lookup_name: str | None = None,
    expected_name: str | None = None,
    allow_create: bool = False,
    dry_run: bool = True,
    allow_destructive: bool = False,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or create/update an Alterios role. Classified as security write."""
    client = _client(profile, project_id)
    existing = _find_role(client, role_id=role_id, name=lookup_name)
    if not existing and not allow_create:
        raise ValueError("Role was not found; pass allow_create=True only after security review.")
    if existing and expected_name and existing.get("name") != expected_name:
        raise ValueError(f"Role name mismatch: expected {expected_name!r}, got {existing.get('name')!r}.")
    resource_id = role_id or (str(existing.get("_id")) if existing and existing.get("_id") else None)
    planned_payload = _security_payload(existing, payload, resource_id)
    operation = _security_resource_operation(
        collection="roles",
        action="upsert",
        kind="role",
        resource_id=resource_id,
        request=planned_payload,
        summary="Create or update an Alterios role and verify through role readback.",
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    response_payload: dict[str, Any] = {
        "preflight": _security_resource_summary(existing),
        "diff": _resource_diff(existing, planned_payload, tuple(sorted(planned_payload.keys()))),
        "planned_payload": strip_alterios_metadata(planned_payload),
    }
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    saved = client.save_role(planned_payload).as_dict()
    saved_id = _extract_response_id(saved) or planned_payload.get("_id")
    readback = client.role_by_id(str(saved_id)).as_dict() if saved_id else None
    response_payload.update({"saved": saved, "readback": readback})
    return controlled_write_result(audit=audit, response=response_payload)

def alterios_delete_user(
    user_id: str,
    expected_email: str | None = None,
    dry_run: bool = True,
    allow_destructive: bool = False,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or delete an Alterios user. Classified as security/destructive write."""
    client = _client(profile, project_id)
    existing = _find_user(client, user_id=user_id)
    if not existing:
        raise ValueError(f"User {user_id!r} was not found.")
    if expected_email and str(existing.get("email") or "").lower() != expected_email.strip().lower():
        raise ValueError(f"User email mismatch: expected {expected_email!r}, got {existing.get('email')!r}.")
    operation = _security_resource_operation(
        collection="users",
        action="delete",
        kind="user_delete",
        resource_id=user_id,
        request={"_id": user_id, "expectedEmail": expected_email},
        summary="Delete an Alterios user and verify absence through user readback.",
        path_override="/api/users",
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    response_payload: dict[str, Any] = {"preflight": _security_resource_summary(existing)}
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    deleted = client.delete_user(user_id).as_dict()
    response_payload.update({"deleted": deleted, "delete_readback": _delete_readback(client, "user", user_id)})
    return controlled_write_result(audit=audit, response=response_payload)

def alterios_delete_user_group(
    user_group_id: str,
    expected_name: str | None = None,
    dry_run: bool = True,
    allow_destructive: bool = False,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or delete an Alterios user group. Classified as security/destructive write."""
    client = _client(profile, project_id)
    existing = _find_user_group(client, user_group_id=user_group_id)
    if not existing:
        raise ValueError(f"User group {user_group_id!r} was not found.")
    if expected_name and existing.get("name") != expected_name:
        raise ValueError(f"User group name mismatch: expected {expected_name!r}, got {existing.get('name')!r}.")
    operation = _security_resource_operation(
        collection="user-groups",
        action="delete",
        kind="user_group_delete",
        resource_id=user_group_id,
        request={"_id": user_group_id, "expectedName": expected_name},
        summary="Delete an Alterios user group and verify absence through user-group readback.",
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    response_payload: dict[str, Any] = {"preflight": _security_resource_summary(existing)}
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    deleted = client.delete_user_group(user_group_id).as_dict()
    response_payload.update(
        {"deleted": deleted, "delete_readback": _delete_readback(client, "user_group", user_group_id)}
    )
    return controlled_write_result(audit=audit, response=response_payload)

def alterios_delete_role(
    role_id: str,
    expected_name: str | None = None,
    dry_run: bool = True,
    allow_destructive: bool = False,
    profile: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Plan or delete an Alterios role. Classified as security/destructive write."""
    client = _client(profile, project_id)
    existing = _find_role(client, role_id=role_id)
    if not existing:
        raise ValueError(f"Role {role_id!r} was not found.")
    if expected_name and existing.get("name") != expected_name:
        raise ValueError(f"Role name mismatch: expected {expected_name!r}, got {existing.get('name')!r}.")
    operation = _security_resource_operation(
        collection="roles",
        action="delete",
        kind="role_delete",
        resource_id=role_id,
        request={"_id": role_id, "expectedName": expected_name},
        summary="Delete an Alterios role and verify absence through role readback.",
    )
    audit = build_write_audit(
        profile=profile,
        project_id=project_id,
        operation=operation,
        dry_run=dry_run,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    response_payload: dict[str, Any] = {"preflight": _security_resource_summary(existing)}
    if dry_run:
        return controlled_write_result(audit=audit, response=response_payload)
    assert_write_allowed(
        profile=profile,
        project_id=project_id,
        operation=operation,
        write_enabled=_write_enabled(),
        dangerous_write_enabled=_dangerous_write_enabled(),
        allow_destructive=allow_destructive,
    )
    deleted = client.delete_role(role_id).as_dict()
    response_payload.update({"deleted": deleted, "delete_readback": _delete_readback(client, "role", role_id)})
    return controlled_write_result(audit=audit, response=response_payload)

__all__ = ['alterios_upsert_user', 'alterios_upsert_user_group', 'alterios_upsert_role', 'alterios_delete_user', 'alterios_delete_user_group', 'alterios_delete_role']
