from __future__ import annotations

from typing import Any, Protocol

from .client import listandcount_items, redact_sensitive


class BulkClient(Protocol):
    def content_by_id(self, content_id: str) -> Any: ...

    def execute_manual_script(self, script_id: str, args: Any = None) -> Any: ...

    def start_process(self, diagram_id: str, **kwargs: Any) -> Any: ...

    def list_processes(self, **kwargs: Any) -> Any: ...

    def list_tasks(self, **kwargs: Any) -> Any: ...

    def call_script_service(self, function: str, args: Any = None, *, allow_write: bool = False) -> Any: ...

    def request(self, method: str, path: str, **kwargs: Any) -> Any: ...


def normalize_bulk_ids(
    selected_content_ids: list[str],
    *,
    expected_count: int | None,
    max_count: int,
) -> list[str]:
    normalized = [str(item).strip() for item in selected_content_ids if str(item).strip()]
    if not normalized:
        raise ValueError("selected_content_ids must contain at least one content id.")
    if len(set(normalized)) != len(normalized):
        raise ValueError("selected_content_ids must not contain duplicates.")
    if expected_count is not None and expected_count != len(normalized):
        raise ValueError(f"expected_count mismatch: expected {expected_count}, got {len(normalized)}.")
    if max_count < 1:
        raise ValueError("max_count must be positive.")
    if len(normalized) > max_count:
        raise ValueError(f"Refusing to process {len(normalized)} rows; max_count is {max_count}.")
    return normalized


def load_bulk_content_targets(
    client: BulkClient,
    content_ids: list[str],
    *,
    expected_content_type_id: str | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for content_id in content_ids:
        body = client.content_by_id(content_id).body
        if not isinstance(body, dict):
            raise ValueError(f"Content {content_id!r} preflight returned an unexpected payload.")
        content_type_id = body.get("contentTypeId") or body.get("content_type_id")
        if expected_content_type_id and content_type_id != expected_content_type_id:
            raise ValueError(
                f"Content {content_id!r} type mismatch: expected {expected_content_type_id!r}, "
                f"got {content_type_id!r}."
            )
        rows.append(
            {
                "_id": body.get("_id") or content_id,
                "name": body.get("name") or body.get("title"),
                "contentTypeId": content_type_id,
                "groupsIds": body.get("groupsIds") or body.get("groupIds") or [],
            }
        )
    return rows


def execute_bulk_manual_script(
    client: BulkClient,
    *,
    script_id: str,
    content_ids: list[str],
    shared_args: dict[str, Any],
    content_arg_name: str,
    readback_content: bool,
    stop_on_error: bool,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for content_id in content_ids:
        args = dict(shared_args)
        args[content_arg_name] = content_id
        try:
            execution = client.execute_manual_script(script_id, args).as_dict()
            row: dict[str, Any] = {
                "content_id": content_id,
                "ok": True,
                "args": args,
                "execution": execution,
            }
            if readback_content:
                row["content_readback"] = client.content_by_id(content_id).as_dict()
        except Exception as exc:  # The batch must journal partial execution instead of losing it.
            row = {
                "content_id": content_id,
                "ok": False,
                "args": args,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
        rows.append(redact_sensitive(row))
        if not row["ok"] and stop_on_error:
            break
    return _batch_result(rows, requested_count=len(content_ids))


def execute_bulk_process_start(
    client: BulkClient,
    *,
    diagram_id: str,
    content_ids: list[str],
    params: dict[str, Any] | None,
    name: str | None,
    stop_on_error: bool,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for content_id in content_ids:
        try:
            started_response = client.start_process(
                diagram_id,
                content_id=content_id,
                params=params,
                name=name,
            )
            started = started_response.as_dict()
            body = started_response.body if isinstance(started_response.body, dict) else {}
            process_id = body.get("processId") or body.get("_id") or body.get("id")
            processes = listandcount_items(
                client.list_processes(
                    process_id=str(process_id) if process_id else None,
                    diagram_id=diagram_id,
                    content_id=content_id,
                    limit=20,
                    offset=0,
                ).body
            )
            if not process_id and processes:
                process_id = processes[0].get("_id") or processes[0].get("id")
            if not process_id:
                raise ValueError("Process start did not return a process id and process readback was empty.")
            matching_processes = [
                process
                for process in processes
                if str(process.get("_id") or process.get("id") or process.get("processId") or "")
                == str(process_id)
            ]
            if not matching_processes:
                raise ValueError(f"Process {process_id!r} was not confirmed by process readback.")
            task_payload = client.list_tasks(
                process_id=str(process_id),
                diagram_id=diagram_id,
                content_id=content_id,
            ).body
            tasks = _response_items(task_payload)
            row = {
                "content_id": content_id,
                "ok": True,
                "process_id": process_id,
                "started": started,
                "readback_processes": processes,
                "readback_tasks": tasks,
            }
        except Exception as exc:  # Preserve evidence for already-started rows.
            row = {
                "content_id": content_id,
                "ok": False,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
        rows.append(redact_sensitive(row))
        if not row["ok"] and stop_on_error:
            break
    return _batch_result(rows, requested_count=len(content_ids))


def execute_bulk_delete(client: BulkClient, *, content_ids: list[str]) -> dict[str, Any]:
    deletion: dict[str, Any]
    try:
        deletion = client.call_script_service(
            "deleteManyContents",
            {"_id": content_ids},
            allow_write=True,
        ).as_dict()
    except Exception as exc:  # Readback still runs because the service may have partially mutated data.
        deletion = {
            "ok": False,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
    readback: list[dict[str, Any]] = []
    for content_id in content_ids:
        try:
            response = client.request(
                "GET",
                "/api/contents/listandcount",
                params={"_id": content_id, "limit": 1, "offset": 0},
            )
            remaining = listandcount_items(response.body)
            readback.append(
                {
                    "content_id": content_id,
                    "deleted": not remaining,
                    "remaining_count": len(remaining),
                }
            )
        except Exception as exc:
            readback.append(
                {
                    "content_id": content_id,
                    "deleted": None,
                    "readback_error": {"type": type(exc).__name__, "message": str(exc)},
                }
            )
    deleted_count = sum(1 for item in readback if item["deleted"])
    return redact_sensitive(
        {
            "ok": deleted_count == len(content_ids),
            "requested_count": len(content_ids),
            "deleted_count": deleted_count,
            "deletion": deletion,
            "readback": readback,
        }
    )


def _response_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "rows", "data", "results", "values"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return listandcount_items(payload)


def _batch_result(rows: list[dict[str, Any]], *, requested_count: int) -> dict[str, Any]:
    succeeded = sum(1 for item in rows if item.get("ok"))
    failed = sum(1 for item in rows if not item.get("ok"))
    return {
        "ok": failed == 0 and len(rows) == requested_count,
        "requested_count": requested_count,
        "processed_count": len(rows),
        "succeeded_count": succeeded,
        "failed_count": failed,
        "stopped_early": len(rows) < requested_count,
        "rows": rows,
    }
