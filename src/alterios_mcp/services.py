from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AlteriosService:
    name: str
    category: str
    permission: str | None
    mutates: bool
    args: tuple[str, ...]
    description: str


SERVICES: dict[str, AlteriosService] = {
    "getContents": AlteriosService(
        name="getContents",
        category="contents",
        permission="contents:read",
        mutates=False,
        args=("query",),
        description="Return content records by filters, sorting, and pagination.",
    ),
    "getDependentContents": AlteriosService(
        name="getDependentContents",
        category="contents",
        permission="contents:read",
        mutates=False,
        args=("query",),
        description="Return dependent content records linked to parent content.",
    ),
    "createContent": AlteriosService(
        name="createContent",
        category="contents",
        permission="contents:create",
        mutates=True,
        args=("content",),
        description="Create a content record.",
    ),
    "updateContent": AlteriosService(
        name="updateContent",
        category="contents",
        permission="contents:update",
        mutates=True,
        args=("content",),
        description="Update an existing content record.",
    ),
    "deleteManyContents": AlteriosService(
        name="deleteManyContents",
        category="contents",
        permission="contents:delete",
        mutates=True,
        args=("args",),
        description="Delete one or more content records by id.",
    ),
    "createDependentContent": AlteriosService(
        name="createDependentContent",
        category="contents",
        permission="contents:create",
        mutates=True,
        args=("content", "relatedContentId", "relatedFieldId"),
        description="Create a dependent record linked to parent content.",
    ),
    "startProcess": AlteriosService(
        name="startProcess",
        category="processes",
        permission="processes:create",
        mutates=True,
        args=(
            "diagramId",
            "name",
            "content",
            "startMessageId",
            "responseMessageId",
            "params",
            "contents",
        ),
        description="Start a business process instance by diagram id.",
    ),
    "getTasks": AlteriosService(
        name="getTasks",
        category="tasks",
        permission="tasks:read",
        mutates=False,
        args=("query",),
        description="Return tasks by filters.",
    ),
    "reassignTask": AlteriosService(
        name="reassignTask",
        category="tasks",
        permission="tasks:update",
        mutates=True,
        args=("query",),
        description="Reassign a task to another assignee.",
    ),
    "messageToAnotherProcess": AlteriosService(
        name="messageToAnotherProcess",
        category="processes",
        permission=None,
        mutates=True,
        args=("messageEventsIds", "processesIds", "diagramsIds", "safeMode"),
        description="Send message events to active process instances.",
    ),
    "getViewData": AlteriosService(
        name="getViewData",
        category="views",
        permission="viewsData:read",
        mutates=False,
        args=("query",),
        description="Return data from a configured view.",
    ),
    "uploadFile": AlteriosService(
        name="uploadFile",
        category="files",
        permission="files:create",
        mutates=True,
        args=("data", "filename", "fieldId", "signal"),
        description="Upload a file and attach it to a file field.",
    ),
    "notify": AlteriosService(
        name="notify",
        category="notifications",
        permission="notifications:create",
        mutates=True,
        args=("notification",),
        description="Send a notification to a user.",
    ),
    "writeLog": AlteriosService(
        name="writeLog",
        category="logs",
        permission=None,
        mutates=True,
        args=("data", "severity"),
        description="Write a message to the system log from script context.",
    ),
}


def list_services(read_only: bool = False) -> list[AlteriosService]:
    services = SERVICES.values()
    if read_only:
        services = [service for service in services if not service.mutates]
    return sorted(services, key=lambda service: (service.category, service.name))


def get_service(name: str) -> AlteriosService:
    try:
        return SERVICES[name]
    except KeyError as exc:
        known = ", ".join(sorted(SERVICES))
        raise ValueError(f"Unknown Alterios service '{name}'. Known services: {known}") from exc


def service_to_dict(service: AlteriosService) -> dict[str, Any]:
    return {
        "name": service.name,
        "category": service.category,
        "permission": service.permission,
        "mutates": service.mutates,
        "args": list(service.args),
        "description": service.description,
    }
