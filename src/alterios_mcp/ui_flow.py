from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from .write_control import collect_target_ids


READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH"})
DESTRUCTIVE_METHODS = frozenset({"DELETE"})

SENSITIVE_HEADER_NAMES = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "proxy-authorization",
    }
)
SENSITIVE_KEY_NAMES = frozenset(
    {
        "apikey",
        "api_key",
        "api-token",
        "api_token",
        "apitoken",
        "authorization",
        "cookie",
        "password",
        "secret",
        "token",
    }
)
CONTENT_VALUE_KEYS = frozenset(
    {
        "body",
        "comment",
        "comments",
        "data",
        "fields",
        "file",
        "filename",
        "files",
        "html",
        "name",
        "originalname",
        "phone",
        "richtext",
        "text",
        "title",
        "value",
        "values",
    }
)
ID_KEY_NAMES = frozenset({"_id", "id", "contentid", "dataid", "entityid", "fieldid", "scriptid", "taskid", "viewid"})
READ_POST_PATHS = frozenset({"/api/views/v2/get-data", "/api/views/v2/get-data-simplified"})
ADMIN_WRITE_PREFIXES = (
    "/api/forms",
    "/api/views",
    "/api/scripts",
    "/api/reports",
    "/api/helps",
    "/api/view-fields",
    "/api/view-entities",
)
WORKFLOW_PREFIXES = ("/api/tasks", "/api/processes", "/api/diagrams")


@dataclass
class RedactionReport:
    redacted_headers: int = 0
    redacted_fields: int = 0
    redacted_query_values: int = 0
    omitted_bodies: int = 0
    dropped_non_api_events: int = 0
    stable_ids: dict[str, str] = field(default_factory=dict)

    def alias_id(self, value: Any) -> str:
        normalized = str(value).strip()
        if not normalized:
            return "<id:empty>"
        if normalized not in self.stable_ids:
            self.stable_ids[normalized] = f"<id:{len(self.stable_ids) + 1}>"
        return self.stable_ids[normalized]

    def as_dict(self) -> dict[str, Any]:
        return {
            "redacted_headers": self.redacted_headers,
            "redacted_fields": self.redacted_fields,
            "redacted_query_values": self.redacted_query_values,
            "omitted_bodies": self.omitted_bodies,
            "dropped_non_api_events": self.dropped_non_api_events,
            "stable_id_count": len(self.stable_ids),
        }


def analyze_ui_flow(
    payload: Any,
    *,
    profile: str | None = None,
    project_id: str | None = None,
    scenario: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    report = RedactionReport()
    events, source_type = _iter_events(payload)
    flows: list[dict[str, Any]] = []
    context = _context(profile=profile, project_id=project_id, scenario=scenario, source=source)

    for event in events:
        flow = _event_to_flow(event, len(flows) + 1, report)
        if flow is None:
            report.dropped_non_api_events += 1
            continue
        flows.append(flow)

    return {
        "schema_version": 1,
        "source_type": source_type,
        "context": context,
        "summary": summarize_flows(flows),
        "flows": flows,
        "redaction_report": report.as_dict(),
    }


def summarize_flows(flows: list[dict[str, Any]]) -> dict[str, Any]:
    labels: dict[str, int] = {}
    risk_levels: dict[str, int] = {}
    write_routes: list[dict[str, Any]] = []
    read_routes: list[dict[str, Any]] = []
    unknown_write_routes: list[dict[str, Any]] = []
    successful_write_like_routes: list[dict[str, Any]] = []

    for flow in flows:
        for label in flow["labels"]:
            labels[label] = labels.get(label, 0) + 1
        risk_level = flow["risk_level"]
        risk_levels[risk_level] = risk_levels.get(risk_level, 0) + 1
        route = {"method": flow["method"], "path": flow["path"], "status_code": flow["status_code"]}
        if flow["requires_write_gate"]:
            write_routes.append(route)
            if flow["classification_source"] == "method_fallback":
                unknown_write_routes.append(route)
            if _is_success_status(flow["status_code"]):
                successful_write_like_routes.append(route)
        else:
            read_routes.append(route)

    return {
        "total_events": len(flows),
        "labels": dict(sorted(labels.items())),
        "risk_levels": dict(sorted(risk_levels.items())),
        "read_route_count": len(read_routes),
        "write_gate_route_count": len(write_routes),
        "unknown_write_route_count": len(unknown_write_routes),
        "successful_write_like_route_count": len(successful_write_like_routes),
        "read_routes": read_routes,
        "write_gate_routes": write_routes,
        "unknown_write_routes": unknown_write_routes,
        "successful_write_like_routes": successful_write_like_routes,
    }


def classify_api_call(method: str, path: str) -> dict[str, Any]:
    normalized_method = method.upper()
    normalized_path = _normalize_path(path)
    labels: set[str] = set()
    source = "known_route"

    if normalized_path.startswith("/api/file/"):
        labels.add("file")
    if normalized_path.startswith("/api/v1/comments"):
        labels.add("comment")

    if normalized_path in READ_POST_PATHS and normalized_method == "POST":
        labels.add("read")
    elif normalized_path.endswith("/listandcount") and normalized_method in READ_METHODS | {"POST"}:
        labels.add("read")
    elif normalized_path.startswith("/api/file/list") and normalized_method in READ_METHODS:
        labels.add("read")
    elif normalized_path.startswith("/api/v1/comments") and normalized_method in READ_METHODS:
        labels.add("read")
    elif normalized_path.startswith("/api/contents") and normalized_method in READ_METHODS:
        labels.add("read")
    elif normalized_method in READ_METHODS:
        labels.add("read")
        if normalized_path.startswith(WORKFLOW_PREFIXES):
            labels.add("workflow")
    elif normalized_path == "/api/contents/save" and normalized_method in WRITE_METHODS:
        labels.add("write")
    elif normalized_path.startswith("/api/file/upload") and normalized_method in WRITE_METHODS:
        labels.update({"file", "write"})
    elif normalized_path.startswith("/api/v1/comments") and normalized_method in WRITE_METHODS:
        labels.update({"comment", "write"})
    elif normalized_path.startswith("/api/v1/comments") and normalized_method in DESTRUCTIVE_METHODS:
        labels.update({"comment", "destructive"})
    elif normalized_path == "/api/scripts/execute-manual" and normalized_method in WRITE_METHODS:
        labels.update({"manual_script", "workflow", "write"})
    elif normalized_path == "/api/tasks/complete":
        labels.update({"workflow", "write"})
    elif normalized_path.startswith(WORKFLOW_PREFIXES):
        labels.add("workflow")
        if normalized_method in DESTRUCTIVE_METHODS:
            labels.update({"destructive", "write"})
        elif normalized_method in WRITE_METHODS:
            labels.add("write")
        else:
            labels.add("read")
    elif normalized_path.startswith(ADMIN_WRITE_PREFIXES):
        if normalized_method in DESTRUCTIVE_METHODS:
            labels.add("destructive")
        elif normalized_method in WRITE_METHODS:
            labels.add("write")
        else:
            labels.add("read")
    elif normalized_method in DESTRUCTIVE_METHODS:
        labels.add("destructive")
        source = "method_fallback"
    elif normalized_method in WRITE_METHODS:
        labels.add("write")
        source = "method_fallback"
    else:
        labels.add("unknown")
        source = "method_fallback"

    risk_level = _risk_level(labels)
    return {
        "labels": sorted(labels),
        "risk_level": risk_level,
        "requires_write_gate": risk_level != "read",
        "classification_source": source,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze and sanitize Alterios UI network flows from HAR or JSON events.")
    parser.add_argument("input", help="Path to a HAR file or JSON event dump.")
    parser.add_argument("--profile", help="Alterios MCP profile used for the capture.")
    parser.add_argument("--project-id", help="Alterios project id used for the capture.")
    parser.add_argument("--scenario", help="Human-readable UI scenario name.")
    parser.add_argument("--json", action="store_true", help="Print full machine-readable JSON.")
    args = parser.parse_args(argv)

    try:
        input_path = Path(args.input)
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        analysis = analyze_ui_flow(
            payload,
            profile=args.profile,
            project_id=args.project_id,
            scenario=args.scenario,
            source=str(input_path),
        )
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(analysis, ensure_ascii=False, indent=2))
    else:
        summary = analysis["summary"]
        print(f"source: {analysis['context'].get('source') or '<stdin>'}")
        print(f"events: {summary['total_events']}")
        print(f"read routes: {summary['read_route_count']}")
        print(f"write-gated routes: {summary['write_gate_route_count']}")
        print(f"unknown write-like routes: {summary['unknown_write_route_count']}")
        print(f"successful write-like routes: {summary['successful_write_like_route_count']}")
    return 0


def _iter_events(payload: Any) -> tuple[list[Any], str]:
    if isinstance(payload, dict) and isinstance(payload.get("log"), dict):
        entries = payload["log"].get("entries")
        if isinstance(entries, list):
            return entries, "har"
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return payload["events"], "events"
    if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
        return payload["entries"], "events"
    if isinstance(payload, list):
        return payload, "events"
    if isinstance(payload, dict):
        return [payload], "event"
    raise TypeError("input must be a HAR object, JSON event object, or event list")


def _event_to_flow(event: Any, sequence: int, report: RedactionReport) -> dict[str, Any] | None:
    if not isinstance(event, dict):
        return None
    parsed = _parse_har_event(event, report) if "request" in event and isinstance(event.get("request"), dict) else _parse_simple_event(event, report)
    if parsed is None:
        return None

    method = parsed["method"]
    url = parsed["url"]
    split = urlsplit(url)
    path = split.path or parsed.get("path") or ""
    if not path.startswith("/api/"):
        return None

    query_pairs = parse_qsl(split.query, keep_blank_values=True)
    query = _query_from_pairs(query_pairs, report)
    query_keys = sorted({key for key, _value in query_pairs})
    request_body = parsed.get("request_body")
    response_body = parsed.get("response_body")
    target_ids = _aliased_target_ids(report, path, query, request_body, response_body)
    classification = classify_api_call(method, path)

    return {
        "sequence": sequence,
        "method": method.upper(),
        "path": path,
        "query_keys": query_keys,
        "sanitized_url": _sanitized_url(split, query_pairs, report),
        "status_code": parsed.get("status_code"),
        "content_type": parsed.get("content_type") or "",
        "labels": classification["labels"],
        "risk_level": classification["risk_level"],
        "requires_write_gate": classification["requires_write_gate"],
        "classification_source": classification["classification_source"],
        "target_ids": target_ids,
        "request": {
            "headers": parsed.get("request_headers", {}),
            "query": query,
            "body_shape": _shape(request_body),
            "body": _redact_body(request_body, report),
        },
        "response": {
            "headers": parsed.get("response_headers", {}),
            "body_shape": _shape(response_body),
        },
    }


def _parse_har_event(event: dict[str, Any], report: RedactionReport) -> dict[str, Any] | None:
    request = event.get("request") or {}
    response = event.get("response") or {}
    method = str(request.get("method") or "").upper()
    url = str(request.get("url") or "")
    if not method or not url:
        return None

    post_data = request.get("postData") if isinstance(request.get("postData"), dict) else {}
    request_body = _body_from_har_post_data(post_data, report)
    response_content = response.get("content") if isinstance(response.get("content"), dict) else {}

    return {
        "method": method,
        "url": url,
        "status_code": response.get("status"),
        "content_type": str(response_content.get("mimeType") or _headers_to_dict(response.get("headers"), report).get("content-type", "")),
        "request_headers": _headers_to_dict(request.get("headers"), report),
        "response_headers": _headers_to_dict(response.get("headers"), report),
        "request_body": request_body,
        "response_body": _maybe_parse_json(response_content.get("text")),
    }


def _parse_simple_event(event: dict[str, Any], report: RedactionReport) -> dict[str, Any] | None:
    method = str(event.get("method") or event.get("request_method") or "").upper()
    url = str(event.get("url") or event.get("request_url") or event.get("path") or "")
    if url.startswith("/"):
        url = "https://alterios.local" + url
    if not method or not url:
        return None

    request_body = event.get("request_body", event.get("body"))
    response_body = event.get("response_body")
    return {
        "method": method,
        "url": url,
        "status_code": event.get("status_code", event.get("status")),
        "content_type": str(event.get("content_type") or ""),
        "request_headers": _headers_to_dict(event.get("request_headers", event.get("headers")), report),
        "response_headers": _headers_to_dict(event.get("response_headers"), report),
        "request_body": request_body,
        "response_body": response_body,
    }


def _headers_to_dict(headers: Any, report: RedactionReport) -> dict[str, Any]:
    if headers is None:
        return {}
    pairs: list[tuple[str, Any]] = []
    if isinstance(headers, dict):
        pairs = [(str(key), value) for key, value in headers.items()]
    elif isinstance(headers, list):
        for item in headers:
            if isinstance(item, dict) and "name" in item:
                pairs.append((str(item.get("name")), item.get("value")))
    result: dict[str, Any] = {}
    for key, value in pairs:
        normalized = key.lower()
        if normalized in SENSITIVE_HEADER_NAMES:
            report.redacted_headers += 1
            result[normalized] = "<redacted>"
        elif _is_id_key(normalized):
            result[normalized] = report.alias_id(value)
        elif normalized in {"accept", "content-type", "lang", "ngsw-bypass"}:
            result[normalized] = value
        else:
            result[normalized] = _safe_scalar(key, value, report)
    return result


def _body_from_har_post_data(post_data: dict[str, Any], report: RedactionReport) -> Any:
    if not post_data:
        return None
    mime_type = str(post_data.get("mimeType") or "").lower()
    if "multipart/" in mime_type:
        report.omitted_bodies += 1
        params = post_data.get("params")
        field_names = [str(item.get("name")) for item in params if isinstance(item, dict) and item.get("name")] if isinstance(params, list) else []
        return {"_omitted": "multipart", "field_names": sorted(field_names)}
    if isinstance(post_data.get("params"), list) and "json" not in mime_type:
        return {str(item.get("name")): item.get("value") for item in post_data["params"] if isinstance(item, dict) and item.get("name")}
    return _maybe_parse_json(post_data.get("text"))


def _maybe_parse_json(value: Any) -> Any:
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return stripped


def _query_from_pairs(pairs: list[tuple[str, str]], report: RedactionReport) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        normalized = key.lower()
        safe_value = "<redacted>" if _is_sensitive_key(normalized) else _safe_scalar(key, value, report)
        if safe_value == "<redacted>":
            report.redacted_query_values += 1
        if key in result:
            if not isinstance(result[key], list):
                result[key] = [result[key]]
            result[key].append(safe_value)
        else:
            result[key] = safe_value
    return result


def _redact_body(value: Any, report: RedactionReport, key: str | None = None, redact_values: bool = False) -> Any:
    if value is None:
        return None
    redact_children = redact_values or bool(key and _is_content_value_key(key) and not _is_id_key(key))
    if isinstance(value, dict):
        return {
            str(child_key): _redact_body(child_value, report, str(child_key), redact_children)
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_body(item, report, key, redact_children) for item in value]
    if isinstance(value, tuple):
        return [_redact_body(item, report, key, redact_children) for item in value]
    if redact_values or (key and (_is_sensitive_key(key) or _is_content_value_key(key))):
        report.redacted_fields += 1
        if _is_id_key(key):
            return report.alias_id(value)
        return "<redacted>"
    return _safe_scalar(key, value, report)


def _safe_scalar(key: str | None, value: Any, report: RedactionReport) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value
    if key and _is_id_key(key):
        return report.alias_id(value)
    if isinstance(value, str):
        if value.startswith("<") and value.endswith(">"):
            return value
        if len(value) > 80:
            report.redacted_fields += 1
            return "<redacted-text>"
        if _looks_like_id(value):
            return report.alias_id(value)
        return "<string>"
    return f"<{type(value).__name__}>"


def _shape(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(key): _shape(child) for key, child in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return [_shape(value[0])] if value else []
    if isinstance(value, tuple):
        return [_shape(value[0])] if value else []
    return type(value).__name__


def _aliased_target_ids(report: RedactionReport, *values: Any) -> list[str]:
    found: list[str] = []
    for value in values:
        for target_id in collect_target_ids(value):
            found.append(report.alias_id(target_id))
    return list(dict.fromkeys(found))


def _sanitized_url(split: Any, pairs: list[tuple[str, str]], report: RedactionReport) -> str:
    safe_pairs = []
    for key, value in pairs:
        safe_pairs.append((key, "<redacted>" if _is_sensitive_key(key) else str(_safe_scalar(key, value, report))))
    query = "&".join(f"{key}={value}" for key, value in safe_pairs)
    return urlunsplit(("", "", split.path, query, ""))


def _context(*, profile: str | None, project_id: str | None, scenario: str | None, source: str | None) -> dict[str, Any]:
    return {
        "profile": profile,
        "project_id": project_id,
        "scenario": scenario,
        "source": source,
    }


def _risk_level(labels: set[str]) -> str:
    if "destructive" in labels:
        return "destructive"
    if "manual_script" in labels:
        return "manual_script"
    if "workflow" in labels and "write" in labels:
        return "workflow_side_effect"
    if "write" in labels:
        return "write"
    if labels <= {"read", "file", "comment", "workflow"} and "read" in labels:
        return "read"
    return "unknown"


def _is_success_status(status_code: Any) -> bool:
    try:
        numeric = int(status_code)
    except (TypeError, ValueError):
        return False
    return 200 <= numeric < 400


def _normalize_path(path: str) -> str:
    return "/" + path.strip().split("?", 1)[0].strip("/").lower()


def _is_sensitive_key(key: str | None) -> bool:
    if not key:
        return False
    normalized = key.lower().replace("-", "_")
    return normalized in SENSITIVE_KEY_NAMES or normalized.endswith("_token") or normalized.endswith("_password")


def _is_content_value_key(key: str | None) -> bool:
    return bool(key and key.lower() in CONTENT_VALUE_KEYS)


def _is_id_key(key: str | None) -> bool:
    if not key:
        return False
    normalized = key.lower()
    return normalized in ID_KEY_NAMES or normalized.endswith("id") or normalized.endswith("ids")


def _looks_like_id(value: str) -> bool:
    normalized = value.strip()
    if len(normalized) < 12:
        return False
    has_hex_dash = all(char.isalnum() or char in {"-", "_"} for char in normalized)
    return has_hex_dash and any(char.isdigit() for char in normalized)


if __name__ == "__main__":
    raise SystemExit(main())
