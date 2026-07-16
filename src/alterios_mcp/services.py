from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ArgumentSpec:
    name: str
    type_hint: str
    required: bool
    description: str
    example: Any = None


@dataclass(frozen=True)
class AlteriosService:
    name: str
    category: str
    permission: str | None
    mutates: bool
    risk_level: str
    args: tuple[str, ...]
    description: str
    arguments: tuple[ArgumentSpec, ...] = ()
    example_args: dict[str, Any] | None = None
    result_shape: str = ""
    safe_to_probe: bool = False
    notes: tuple[str, ...] = ()


def arg(
    name: str,
    type_hint: str,
    description: str,
    *,
    required: bool = True,
    example: Any = None,
) -> ArgumentSpec:
    return ArgumentSpec(
        name=name,
        type_hint=type_hint,
        required=required,
        description=description,
        example=example,
    )


SERVICES: dict[str, AlteriosService] = {
    "getContents": AlteriosService(
        name="getContents",
        category="contents",
        permission="contents:read",
        mutates=False,
        risk_level="read",
        args=("query",),
        description="Return content records by filters, sorting, and pagination.",
        arguments=(
            arg(
                "query",
                "object",
                "Content filters and pagination. Common keys are contentTypeId, limit, offset, sort, and d.",
                example={"contentTypeId": "<content-type-id>", "limit": 20, "offset": 0},
            ),
        ),
        example_args={"query": {"contentTypeId": "<content-type-id>", "limit": 20, "offset": 0}},
        result_shape="content records or listandcount-like payload",
        safe_to_probe=True,
    ),
    "getDependentContents": AlteriosService(
        name="getDependentContents",
        category="contents",
        permission="contents:read",
        mutates=False,
        risk_level="read",
        args=("query",),
        description="Return dependent content records linked to parent content.",
        arguments=(
            arg(
                "query",
                "object",
                "Parent content context plus pagination. Exact relation keys depend on the form field.",
                example={"contentId": "<parent-content-id>", "limit": 20, "offset": 0},
            ),
        ),
        example_args={"query": {"contentId": "<parent-content-id>", "limit": 20, "offset": 0}},
        result_shape="dependent content records",
        safe_to_probe=True,
        notes=("Verify the real relation field before using results as proof of child rows.",),
    ),
    "createContent": AlteriosService(
        name="createContent",
        category="contents",
        permission="contents:create",
        mutates=True,
        risk_level="write",
        args=("content",),
        description="Create a content record.",
        arguments=(
            arg(
                "content",
                "object",
                "Record payload. contentTypeId is required; fields contains fieldId/value mappings.",
                example={"contentTypeId": "<content-type-id>", "fields": {"<field-id>": "value"}},
            ),
        ),
        example_args={"content": {"contentTypeId": "<content-type-id>", "fields": {"<field-id>": "value"}}},
        result_shape="created content record",
        notes=("Write-gated. Prefer typed validators and a test project before enabling.",),
    ),
    "updateContent": AlteriosService(
        name="updateContent",
        category="contents",
        permission="contents:update",
        mutates=True,
        risk_level="write",
        args=("content",),
        description="Update an existing content record.",
        arguments=(
            arg(
                "content",
                "object",
                "Record payload with _id plus fields to update.",
                example={"_id": "<content-id>", "fields": {"<field-id>": "new value"}},
            ),
        ),
        example_args={"content": {"_id": "<content-id>", "fields": {"<field-id>": "new value"}}},
        result_shape="updated content record",
        notes=("Write-gated. Verify via API readback and UI when user-facing.",),
    ),
    "deleteManyContents": AlteriosService(
        name="deleteManyContents",
        category="contents",
        permission="contents:delete",
        mutates=True,
        risk_level="destructive",
        args=("args",),
        description="Delete one or more content records by id.",
        arguments=(
            arg(
                "args",
                "object",
                "Delete request with one or more content IDs. Exact key shape must be verified per endpoint.",
                example={"_id": ["<content-id>"]},
            ),
        ),
        example_args={"args": {"_id": ["<content-id>"]}},
        result_shape="delete result",
        notes=("Destructive. Do not expose through typed tools without dry-run and explicit target review.",),
    ),
    "createDependentContent": AlteriosService(
        name="createDependentContent",
        category="contents",
        permission="contents:create",
        mutates=True,
        risk_level="write",
        args=("content", "relatedContentId", "relatedFieldId"),
        description="Create a dependent record linked to parent content.",
        arguments=(
            arg("content", "object", "Child record payload.", example={"contentTypeId": "<child-type-id>", "fields": {}}),
            arg("relatedContentId", "string", "Parent content ID.", example="<parent-content-id>"),
            arg("relatedFieldId", "string", "Relation field ID on the parent or child context.", example="<field-id>"),
        ),
        example_args={
            "content": {"contentTypeId": "<child-type-id>", "fields": {}},
            "relatedContentId": "<parent-content-id>",
            "relatedFieldId": "<field-id>",
        },
        result_shape="created dependent content record",
        notes=("Write-gated. Verify the real relation field before creating child rows.",),
    ),
    "startProcess": AlteriosService(
        name="startProcess",
        category="processes",
        permission="processes:create",
        mutates=True,
        risk_level="workflow_side_effect",
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
        arguments=(
            arg("diagramId", "string", "Business process diagram ID.", example="<diagram-id>"),
            arg("name", "string", "Process instance name.", required=False, example="New process"),
            arg("content", "object", "Primary content payload or reference.", required=False),
            arg("startMessageId", "string", "Optional start message event ID.", required=False),
            arg("responseMessageId", "string", "Optional response message event ID.", required=False),
            arg("params", "object", "Additional process parameters.", required=False, example={}),
            arg("contents", "array", "Additional content records for process start.", required=False, example=[]),
        ),
        example_args={"diagramId": "<diagram-id>", "name": "New process", "params": {}},
        result_shape="process start result",
        notes=("Starts workflow activity and may create tasks or notifications.",),
    ),
    "getTasks": AlteriosService(
        name="getTasks",
        category="tasks",
        permission="tasks:read",
        mutates=False,
        risk_level="read",
        args=("query",),
        description="Return tasks by filters.",
        arguments=(
            arg(
                "query",
                "object",
                "Task filters and pagination. Common keys are limit, offset, assignee, status, and process IDs.",
                example={"limit": 20, "offset": 0},
            ),
        ),
        example_args={"query": {"limit": 20, "offset": 0}},
        result_shape="task records",
        safe_to_probe=True,
    ),
    "reassignTask": AlteriosService(
        name="reassignTask",
        category="tasks",
        permission="tasks:update",
        mutates=True,
        risk_level="workflow_side_effect",
        args=("query",),
        description="Reassign a task to another assignee.",
        arguments=(
            arg(
                "query",
                "object",
                "Task reassignment payload. Task ID and target assignee shape must be verified per instance.",
                example={"taskId": "<task_id>", "assigneeId": "<user-id>"},
            ),
        ),
        example_args={"query": {"taskId": "<task_id>", "assigneeId": "<user-id>"}},
        result_shape="task update result",
        notes=("Changes operator workload and should be verified in task UI.",),
    ),
    "messageToAnotherProcess": AlteriosService(
        name="messageToAnotherProcess",
        category="processes",
        permission=None,
        mutates=True,
        risk_level="workflow_side_effect",
        args=("messageEventsIds", "processesIds", "diagramsIds", "safeMode"),
        description="Send message events to active process instances.",
        arguments=(
            arg("messageEventsIds", "array", "Message event IDs to send.", example=["<message-event-id>"]),
            arg("processesIds", "array", "Target process instance IDs.", required=False, example=["<process-id>"]),
            arg("diagramsIds", "array", "Target diagram IDs.", required=False, example=["<diagram-id>"]),
            arg("safeMode", "boolean", "Whether Alterios should apply safe-mode constraints.", required=False, example=True),
        ),
        example_args={
            "messageEventsIds": ["<message-event-id>"],
            "processesIds": ["<process-id>"],
            "safeMode": True,
        },
        result_shape="message dispatch result",
        notes=("Can advance workflows. Keep write-gated and require explicit target review.",),
    ),
    "getViewData": AlteriosService(
        name="getViewData",
        category="views",
        permission="viewsData:read",
        mutates=False,
        risk_level="read",
        args=("query",),
        description="Return data from a configured view.",
        arguments=(
            arg(
                "query",
                "object",
                "View query. Common keys are viewId, limit, offset, contentId, dataId, and userFilters.",
                example={"viewId": "<view-id>", "limit": 20, "offset": 0},
            ),
        ),
        example_args={"query": {"viewId": "<view-id>", "limit": 20, "offset": 0}},
        result_shape="view rows and headers",
        safe_to_probe=True,
        notes=("Prefer REST typed tools for views when available; dataId should be an array for record context.",),
    ),
    "uploadFile": AlteriosService(
        name="uploadFile",
        category="files",
        permission="files:create",
        mutates=True,
        risk_level="write",
        args=("data", "filename", "fieldId", "signal"),
        description="Upload a file and attach it to a file field.",
        arguments=(
            arg("data", "bytes|string", "File payload or encoded data.", example="<file-bytes>"),
            arg("filename", "string", "Original filename.", example="document.pdf"),
            arg("fieldId", "string", "Target file field ID.", required=False, example="<field-id>"),
            arg("signal", "object", "Optional abort/signal context.", required=False),
        ),
        example_args={"filename": "document.pdf", "fieldId": "<field-id>"},
        result_shape="uploaded file metadata",
        notes=("Use read-only file metadata for inventory; upload remains write-gated.",),
    ),
    "notify": AlteriosService(
        name="notify",
        category="notifications",
        permission="notifications:create",
        mutates=True,
        risk_level="external_side_effect",
        args=("notification",),
        description="Send a notification to a user.",
        arguments=(
            arg(
                "notification",
                "object",
                "Notification payload. Target user/channel shape must be verified per instance.",
                example={"userId": "<user-id>", "message": "Text"},
            ),
        ),
        example_args={"notification": {"userId": "<user-id>", "message": "Text"}},
        result_shape="notification send result",
        notes=("External side effect. Keep disabled unless explicitly requested and verified.",),
    ),
    "writeLog": AlteriosService(
        name="writeLog",
        category="logs",
        permission=None,
        mutates=True,
        risk_level="audit_side_effect",
        args=("data", "severity"),
        description="Write a message to the system log from script context.",
        arguments=(
            arg("data", "object|string", "Log payload.", example={"message": "Diagnostic event"}),
            arg("severity", "string", "Log severity.", required=False, example="info"),
        ),
        example_args={"data": {"message": "Diagnostic event"}, "severity": "info"},
        result_shape="log write result",
        notes=("Write-gated because it changes operational logs.",),
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
        "risk_level": service.risk_level,
        "args": list(service.args),
        "arguments": [
            {
                "name": argument.name,
                "type": argument.type_hint,
                "required": argument.required,
                "description": argument.description,
                "example": argument.example,
            }
            for argument in service.arguments
        ],
        "example_args": service.example_args or {},
        "result_shape": service.result_shape,
        "safe_to_probe": service.safe_to_probe,
        "notes": list(service.notes),
        "description": service.description,
    }
