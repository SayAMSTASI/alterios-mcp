"""Bounded, read-only inventories with explicit evidence of completeness."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context

from .client import AlteriosRequestError, listandcount_items, redact_sensitive
from .discovery import OBJECT_ROUTES
from .write_plan import artifact_root


MAX_ROWS = 100000
MAX_PAGES = 1000
SNAPSHOT_KINDS = frozenset(OBJECT_ROUTES) - {"projects", "users", "user_groups"}
FILTERS = {"_id", "contentTypeId", "diagramId", "processId", "contentId"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def safe_payload(value: Any) -> Any:
    """Redact structured secrets, including structured JSON inside log strings."""
    return _safe_text(redact_sensitive(value))


def _safe_text(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _safe_text(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_text(item) for item in value]
    if isinstance(value, str):
        if value.lstrip().startswith(("{", "[")):
            try:
                return json.dumps(safe_payload(json.loads(value)), ensure_ascii=False)
            except (ValueError, RecursionError):
                pass
        if "bearer" in value.casefold():
            value = re.sub(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1<redacted>", value)
        if re.search(r"(?i)token|password|secret|api[_-]?key|cookie|authorization", value):
            # Start only at a key boundary; do not consume ordinary assignments,
            # which may contain credential assignments inside their string values.
            value = re.sub(r'''(?i)(?<![\w-])(?=[\w-]*(?:token|password|secret|api[_-]?key|cookie|authorization))([\w-]+["']?\s*[:=]\s*)("[^"]*"|'[^']*'|[^\s,;}]+)''', r"\1<redacted>", value)
        if "@" in value:
            value = re.sub(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "<redacted>", value)
    return value


def page_rows(body: Any) -> tuple[list[dict[str, Any]], int | None]:
    rows = listandcount_items(body)
    raw_rows = body[0] if isinstance(body, list) and body and isinstance(body[0], list) else body
    if isinstance(body, dict):
        raw_rows = next((body[key] for key in ("items", "rows", "data", "results", "values")
                         if isinstance(body.get(key), list)), None)
    if not isinstance(raw_rows, list) or any(not isinstance(row, dict) for row in raw_rows):
        raise AlteriosRequestError("Invalid pagination row shape")
    total = None
    if isinstance(body, list) and len(body) == 2 and isinstance(body[0], list):
        total = body[1]
    elif isinstance(body, dict):
        total = next((body[key] for key in ("count", "total", "totalCount") if key in body), None)
    if total is not None:
        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            raise AlteriosRequestError("Invalid pagination total")
    return rows, total


def collect_pages(fetch: Callable[[int, int], Any], *, page_size: int = 200,
                  max_pages: int = 100, max_rows: int = 10000) -> dict[str, Any]:
    if not 1 <= page_size <= 1000 or not 1 <= max_pages <= MAX_PAGES or not 1 <= max_rows <= MAX_ROWS:
        raise ValueError("Invalid page_size, max_pages or max_rows bounds")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    errors: list[dict[str, Any]] = []
    total = None
    terminal = False
    offset = 0
    pages = 0
    duplicates = 0
    for _ in range(max_pages):
        try:
            batch, reported = page_rows(fetch(min(page_size, max_rows - len(rows)), offset))
            pages += 1
        except (OSError, ValueError, AlteriosRequestError) as exc:
            errors.append({"code": "page_read_failed", "offset": offset, "error_type": type(exc).__name__})
            break
        if reported is not None:
            if total is not None and reported != total:
                errors.append({"code": "total_changed", "before": total, "after": reported})
            total = reported
        if not batch:
            terminal = True
            break
        added = 0
        for row in batch:
            identity = str(row.get("_id") or row.get("id") or fingerprint(row))
            if identity in seen:
                duplicates += 1
                continue
            seen.add(identity)
            if len(rows) >= max_rows:
                errors.append({"code": "row_limit"})
                break
            rows.append(row)
            added += 1
        offset += len(batch)
        if duplicates:
            errors.append({"code": "duplicate_rows", "count": duplicates})
            break
        if total is not None and offset >= total:
            terminal = True
            break
        if not added or len(rows) >= max_rows:
            errors.append({"code": "row_limit"})
            break
    if not terminal and not errors:
        errors.append({"code": "page_limit"})
    if total is not None and total != len(rows):
        errors.append({"code": "count_mismatch", "expected": total, "loaded": len(rows)})
    return {"rows": rows, "total": total, "loaded": len(rows), "pages": pages,
            "complete": terminal and not errors, "errors": errors,
            "consistency": "bounded scan; no server-side snapshot isolation"}


def read_kind(client: Any, kind: str, *, filters: dict[str, Any] | None = None,
              page_size: int = 200, max_pages: int = 100, max_rows: int = 10000) -> dict[str, Any]:
    if kind not in SNAPSHOT_KINDS:
        raise ValueError("Unsupported project inventory kind")
    if not 1 <= page_size <= 1000 or not 1 <= max_pages <= MAX_PAGES or not 1 <= max_rows <= MAX_ROWS:
        raise ValueError("Invalid pagination budget")
    filters = dict(filters or {})
    if set(filters) - FILTERS or any(not isinstance(v, str) or not v.strip() for v in filters.values()):
        raise ValueError("Filters must be nonempty strings with supported keys")
    route = OBJECT_ROUTES[kind]
    if kind in {"fields", "groups", "helps"}:
        # These API routes return a whole plain array and ignore pagination on
        # supported servers. Repeating offset requests would duplicate all rows.
        if not 1 <= max_rows <= MAX_ROWS:
            raise ValueError("Invalid row budget")
        try:
            body = client.request(route.method, route.path, params=filters, requires_project=True).body
            all_rows, reported = page_rows(body)
        except (OSError, ValueError, AlteriosRequestError) as exc:
            return {"kind": kind, "filters": filters, "rows": [], "total": None, "loaded": 0,
                    "pages": 0, "complete": False,
                    "errors": [{"code": "page_read_failed", "error_type": type(exc).__name__}]}
        if reported is None and isinstance(body, list):
            ids = [str(r.get("_id") or r.get("id") or fingerprint(r)) for r in all_rows]
            errors = []
            if len(ids) != len(set(ids)):
                errors.append({"code": "duplicate_rows"})
            if len(all_rows) > max_rows:
                errors.append({"code": "row_limit"})
            return {"kind": kind, "filters": filters, "rows": all_rows[:max_rows],
                    "total": len(all_rows), "loaded": min(len(all_rows), max_rows), "pages": 1,
                    "complete": not errors, "errors": errors,
                    "consistency": "single unpaginated endpoint response"}
        # A server with an explicit total is handled using normal pagination.
    result = collect_pages(lambda limit, offset: client.request(route.method, route.path,
        params={**filters, "limit": limit, "offset": offset}, requires_project=True).body,
        page_size=page_size, max_pages=max_pages, max_rows=max_rows)
    result.update({"kind": kind, "filters": filters})
    return result


def collect_snapshot(client: Any, *, kinds: list[str], page_size: int = 200,
                     max_pages: int = 100, max_rows: int = 10000,
                     include_details: bool = False, max_detail_objects: int = 200,
                     detail_workers: int = 4) -> dict[str, Any]:
    if not kinds or len(kinds) != len(set(kinds)) or set(kinds) - SNAPSHOT_KINDS:
        raise ValueError("Choose distinct supported project kinds")
    if not 1 <= max_detail_objects <= 2000 or not 1 <= max_rows <= MAX_ROWS:
        raise ValueError("Invalid detail/row budget")
    if not 1 <= detail_workers <= 8:
        raise ValueError("detail_workers must be between 1 and 8")
    result = {"schema_version": 1, "snapshot_id": "scan_" + uuid.uuid4().hex,
              "readonly": True, "started_at": utc_now(),
              "target": {"profile": client.config.profile, "project_id": client.config.project_id},
              "objects": {}}
    remaining = max_rows
    detailed = 0
    detail_methods = {"forms": "form_full", "views": "view_full", "reports": "report_by_id",
                      "scripts": "script_by_id", "diagrams": "diagram_by_id"}
    for kind in kinds:
        if remaining <= 0:
            result["objects"][kind] = {"rows": [], "loaded": 0, "complete": False,
                                       "errors": [{"code": "snapshot_row_limit"}]}
            continue
        batch = read_kind(client, kind, page_size=page_size, max_pages=max_pages, max_rows=remaining)
        if include_details and kind in detail_methods:
            selected = batch["rows"][:max_detail_objects - detailed]
            if len(selected) < len(batch["rows"]):
                batch["errors"].append({"code": "detail_limit"})
            detailed += len(selected)

            def hydrate(row):
                identity = row.get("_id")
                try:
                    if not identity:
                        raise ValueError("Missing object ID")
                    row["_snapshot_detail"] = getattr(client, detail_methods[kind])(identity).body
                    if kind == "views":
                        row["_snapshot_entities"] = client.view_entities(identity).body
                        row["_snapshot_fields"] = client.view_fields_populated(identity).body
                except (OSError, ValueError, AlteriosRequestError) as exc:
                    return {"code": "detail_read_failed", "id": identity, "error_type": type(exc).__name__}
                return None

            # Only independent detail reads are concurrent. Pagination and the
            # shared row/detail budgets remain sequential and deterministic.
            with ThreadPoolExecutor(max_workers=detail_workers) as pool:
                futures = [pool.submit(copy_context().run, hydrate, row) for row in selected]
                for future in futures:
                    error = future.result()
                    if error:
                        batch["errors"].append(error)
            batch["complete"] = batch["complete"] and not batch["errors"]
        result["objects"][kind] = batch
        remaining -= batch["loaded"]
    result["finished_at"] = utc_now()
    result["complete"] = all(x["complete"] for x in result["objects"].values())
    result["include_details"] = include_details
    result["detail_objects_read"] = detailed
    result["detail_workers"] = detail_workers
    result["limitations"] = ["Only selected kinds; linked content/fragments must be included explicitly.",
                              "Detail hydration enabled." if include_details else "List-route fields only; full reports and joined view metadata may be omitted.",
                              "Concurrent remote edits may change data without changing row counts."]
    return safe_payload(result)


def save_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    directory = artifact_root() / "read-snapshots"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (snapshot["snapshot_id"] + ".json")
    raw = json.dumps(safe_payload(snapshot), ensure_ascii=False, indent=2).encode("utf-8")
    if len(raw) > 100 * 1024 * 1024:
        raise ValueError("Snapshot exceeds 100 MiB storage/read budget; reduce selected kinds or rows")
    with path.open("xb") as stream:
        stream.write(raw)
    return {"snapshot_id": snapshot["snapshot_id"], "path": str(path),
            "sha256": hashlib.sha256(raw).hexdigest(), "complete": snapshot["complete"],
            "target": snapshot["target"],
            "objects": {k: {a: b for a, b in v.items() if a != "rows"} for k, v in snapshot["objects"].items()}}


def load_snapshot(snapshot_id: str, *, profile: str, project_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"scan_[0-9a-f]{32}", snapshot_id):
        raise ValueError("Invalid snapshot ID")
    root = (artifact_root() / "read-snapshots").resolve()
    path = (root / (snapshot_id + ".json")).resolve()
    if not path.is_relative_to(root) or path.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("Invalid snapshot path or size")
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    if snapshot.get("target") != {"profile": profile, "project_id": project_id}:
        raise ValueError("Snapshot target does not match explicit profile/project")
    return snapshot


def walk(value: Any, path: str = ""):
    if isinstance(value, dict):
        for key, item in value.items():
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            yield from walk(item, path + "/" + escaped)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk(item, path + "/" + str(index))
    else:
        yield path, value


def snapshot_records(snapshot: dict[str, Any]):
    for kind, batch in snapshot["objects"].items():
        for index, row in enumerate(batch["rows"]):
            yield kind, str(row.get("_id") or row.get("id") or f"row:{index}"), row


def find_usages(snapshot: dict[str, Any], query: str, *, max_matches: int = 200) -> dict[str, Any]:
    if not query.strip() or len(query) > 256 or not 1 <= max_matches <= 5000:
        raise ValueError("Query or max_matches outside bounds")
    matches = []
    truncated = False
    for kind, identity, row in snapshot_records(snapshot):
        for path, value in walk(row):
            if isinstance(value, str) and query.casefold() in value.casefold():
                if len(matches) == max_matches:
                    truncated = True
                    break
                matches.append({"kind": kind, "object_id": identity, "name": row.get("name"),
                                "path": path, "match_type": "literal"})
        if truncated:
            break
    return {"snapshot_id": snapshot["snapshot_id"], "source_time": snapshot["finished_at"],
            "matches": matches, "truncated": truncated,
            "complete_within_snapshot": bool(snapshot["complete"]) and not truncated,
            "limitations": [*snapshot.get("limitations", []), "Literal search; computed references and omitted payloads remain unverified."]}


def relation_graph(snapshot: dict[str, Any], *, root_id: str | None = None,
                   max_edges: int = 5000) -> dict[str, Any]:
    if not 1 <= max_edges <= 20000:
        raise ValueError("max_edges outside bounds")
    records = list(snapshot_records(snapshot))
    by_id: dict[str, list[str]] = {}
    nodes = []
    for kind, identity, row in records:
        key = kind + ":" + identity
        by_id.setdefault(identity, []).append(key)
        nodes.append({"key": key, "kind": kind, "id": identity, "name": row.get("name"), "mname": row.get("mname")})
    edges = []
    for kind, identity, row in records:
        source_key = kind + ":" + identity
        for path, value in walk(row):
            if path in {"/_id", "/id"} or not isinstance(value, str):
                continue
            for target in by_id.get(value, []):
                edges.append({"source": source_key, "target": target, "path": path,
                              "evidence": "exact scalar ID match"})
                if len(edges) > max_edges:
                    break
            if len(edges) > max_edges:
                break
        if len(edges) > max_edges:
            break
    truncated = len(edges) > max_edges
    edges = edges[:max_edges]
    if root_id:
        selected = set(by_id.get(root_id, []))
        if not selected:
            raise ValueError("Root not present in snapshot")
        changed = True
        while changed:
            old = len(selected)
            for edge in edges:
                if edge["source"] in selected or edge["target"] in selected:
                    selected.update((edge["source"], edge["target"]))
            changed = len(selected) != old
        nodes = [node for node in nodes if node["key"] in selected]
        edges = [edge for edge in edges if edge["source"] in selected]
    return {"nodes": nodes, "edges": edges, "truncated": truncated,
            "complete_within_snapshot": bool(snapshot["complete"]) and not truncated,
            "limitations": ["Static ID links only; inferred edges are not proof of business ownership or dynamic script dependencies.",
                             *snapshot.get("limitations", [])]}


def diagnose_view(client: Any, view_id: str, *, content_id: str | None = None,
                  limit: int = 20) -> dict[str, Any]:
    if not view_id.strip() or not 1 <= limit <= 100:
        raise ValueError("view_id and limit are required within bounds")
    checks = []
    requests = [("definition", lambda: client.view_full(view_id)),
                ("entities", lambda: client.view_entities(view_id)),
                ("fields", lambda: client.view_fields_populated(view_id)),
                ("unscoped", lambda: client.view_data(view_id, limit=limit, offset=0)),
                ("simplified", lambda: client.request("POST", "/api/views/v2/get-data-simplified",
                                                     body={"viewId": view_id, "limit": limit, "offset": 0}))]
    if content_id:
        requests += [("contentId", lambda: client.view_data(view_id, limit=limit, offset=0, content_id=content_id)),
                     ("dataId", lambda: client.view_data(view_id, limit=limit, offset=0, data_id=[content_id]))]
    import time
    for name, action in requests:
        started = time.monotonic()
        try:
            body = action().body
            check = {"name": name, "ok": True, "body": safe_payload(body)}
            if name not in {"definition", "entities", "fields"}:
                rows, total = page_rows(body)
                check.update({"sample_count": len(rows), "total": total, "sample_hash": fingerprint(rows)})
        except (ValueError, OSError, AlteriosRequestError) as exc:
            check = {"name": name, "ok": False, "error_type": type(exc).__name__,
                     "message": safe_payload(str(exc))[:500]}
        check["duration_ms"] = round((time.monotonic() - started) * 1000, 1)
        checks.append(check)
    indexed = {x["name"]: x for x in checks}
    findings = []
    if any(not x["ok"] for x in checks):
        findings.append("Some layers failed; an empty UI must not be interpreted as absence of records.")
    if content_id and all(indexed[k].get("sample_hash") for k in ("unscoped", "contentId", "dataId")):
        if indexed["contentId"]["sample_hash"] == indexed["unscoped"]["sample_hash"] != indexed["dataId"]["sample_hash"]:
            findings.append("contentId matches the unscoped sample while dataId differs; verify embedded-list binding.")
    return {"readonly": True, "view_id": view_id, "checks": checks, "findings": findings,
            "limitations": ["Bounded samples, not a complete data or user-permission audit. Same samples do not prove equivalent filters."]}
