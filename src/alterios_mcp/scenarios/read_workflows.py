"""Public workflow entrypoints; remote operations in this module are read-only."""
from __future__ import annotations

from typing import Any

from .._support import _client
from .. import read_workflows as workflows
from ..file_export import export_files


def _target(profile: str, project_id: str):
    if not profile.strip() or not project_id.strip():
        raise ValueError("Explicit profile and project_id are required")
    return _client(profile, project_id)


def alterios_export_dataset(profile: str, project_id: str, kinds: list[str],
                            page_size: int = 200, max_pages: int = 100,
                            max_rows: int = 10000, include_details: bool = False,
                            max_detail_objects: int = 200) -> dict[str, Any]:
    """Save a redacted, bounded project snapshot with counts, errors and completeness evidence."""
    snapshot = workflows.collect_snapshot(_target(profile, project_id), kinds=kinds,
        page_size=page_size, max_pages=max_pages, max_rows=max_rows,
        include_details=include_details, max_detail_objects=max_detail_objects)
    return workflows.save_snapshot(snapshot)


def alterios_read_all_objects(profile: str, project_id: str, kind: str,
                             filters: dict[str, Any] | None = None,
                             page_size: int = 200, max_pages: int = 20,
                             max_rows: int = 2000) -> dict[str, Any]:
    """Read bounded paginated objects; partial reads always include an incomplete status."""
    return workflows.safe_payload(workflows.read_kind(_target(profile, project_id), kind,
        filters=filters, page_size=page_size, max_pages=max_pages, max_rows=max_rows))


def alterios_find_usages(profile: str, project_id: str, snapshot_id: str,
                        query: str, max_matches: int = 200) -> dict[str, Any]:
    """Find literal field/ID/marker occurrences in a previously exported project snapshot."""
    snapshot = workflows.load_snapshot(snapshot_id, profile=profile, project_id=project_id)
    return workflows.find_usages(snapshot, query, max_matches=max_matches)


def alterios_relation_graph(profile: str, project_id: str, snapshot_id: str,
                          root_id: str | None = None, max_edges: int = 5000) -> dict[str, Any]:
    """Build a static ID dependency graph, optionally connected to one root, from a snapshot."""
    snapshot = workflows.load_snapshot(snapshot_id, profile=profile, project_id=project_id)
    return workflows.relation_graph(snapshot, root_id=root_id, max_edges=max_edges)


def alterios_diagnose_view(profile: str, project_id: str, view_id: str,
                          content_id: str | None = None, limit: int = 20) -> dict[str, Any]:
    """Compare definition, joins, columns and unscoped/contentId/dataId runtime samples."""
    return workflows.diagnose_view(_target(profile, project_id), view_id, content_id=content_id, limit=limit)


def alterios_audit_log(profile: str, project_id: str, object_id: str | None = None,
                      controller: str | None = None, max_pages: int = 20,
                      page_size: int = 200, max_rows: int = 4000) -> dict[str, Any]:
    """Read the administrative log; report scan coverage and locally filter exact object IDs."""
    client = _target(profile, project_id)
    result = workflows.collect_pages(lambda limit, offset: client.request("GET", "/api/log",
        params={"limit": limit, "offset": offset}, requires_project=False).body,
        page_size=page_size, max_pages=max_pages, max_rows=max_rows)
    scanned = result.pop("rows")
    dates = sorted(str(r.get("date")) for r in scanned if r.get("date"))
    def matches(row):
        if controller and row.get("path") != controller:
            return False
        if object_id:
            values = [v for _, v in workflows.walk(row)]
            for field in ("args", "body"):
                if isinstance(row.get(field), str):
                    import json
                    try:
                        values += [v for _, v in workflows.walk(json.loads(row[field]))]
                    except ValueError:
                        pass
            if object_id not in values:
                return False
        return True
    result.update({"rows": [r for r in scanned if matches(r)], "readonly": True,
        "scope": "instance administrative log", "observed_first": dates[0] if dates else None,
        "observed_last": dates[-1] if dates else None, "retention_start_verified": False,
        "limitations": ["Observed dates cover only retrieved rows; even a complete scan does not prove no older events existed.",
                         "Structured author names and credentials are redacted; author identifiers are retained where present."]})
    return workflows.safe_payload(result)


def alterios_list_notifications(profile: str, project_id: str,
                               object_id: str | None = None, max_pages: int = 20,
                               page_size: int = 200, max_rows: int = 4000) -> dict[str, Any]:
    """Read notifications visible to the configured account; never mark read or send."""
    client = _target(profile, project_id)
    result = workflows.collect_pages(lambda limit, offset: client.request("GET", "/api/notifications",
        params={"limit": limit, "offset": offset}).body,
        page_size=page_size, max_pages=max_pages, max_rows=max_rows)
    if object_id:
        result["rows"] = [r for r in result["rows"] if any(v == object_id for _, v in workflows.walk(r))]
    result.update({"readonly": True, "visibility": "configured account only",
                   "delivery_verified": False, "read_receipt_verified": False})
    return workflows.safe_payload(result)


def alterios_list_files(profile: str, project_id: str, folder_hash: str | None = None) -> dict[str, Any]:
    """Read one elFinder folder; mutations and arbitrary file-manager commands are not exposed."""
    response = _target(profile, project_id).file_elfinder(command="open", target=folder_hash)
    return {"readonly": True, "recursive": False, "body": workflows.safe_payload(response.body)}


def alterios_download_files(profile: str, project_id: str, file_ids: list[str],
                            max_file_bytes: int = 10485760,
                            max_total_bytes: int = 52428800) -> dict[str, Any]:
    """Download selected file IDs into a new private directory with verified SHA-256 manifest."""
    return export_files(_target(profile, project_id), file_ids,
                        max_file_bytes=max_file_bytes, max_total_bytes=max_total_bytes)
