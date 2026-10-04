"""Bounded previews with the complete redacted result in a private artifact."""
from __future__ import annotations

from .performance import json_bytes
from .read_workflows import safe_payload
from .read_evidence import persist_result, evidence

DEFAULT_FIELDS = ("_id", "id", "name", "mname", "kind", "type", "key", "source", "target",
                  "path", "object_id", "match_type", "ok", "code", "error_type", "date", "hash", "mime", "size")
COLLECTIONS = {"rows", "matches", "nodes", "edges", "files"}


def validate_output(response_mode="compact", fields=None, preview_rows=20, max_response_bytes=16384):
    if response_mode not in {"compact", "full", "artifact"}:
        raise ValueError("response_mode must be compact, full or artifact")
    if not 0 <= preview_rows <= 100 or not 4096 <= max_response_bytes <= 262144:
        raise ValueError("Output budget outside bounds")
    if fields is not None and (not isinstance(fields, list) or len(fields) > 32 or
            any(not isinstance(f, str) or not f or len(f) > 100 for f in fields)):
        raise ValueError("fields must contain at most 32 literal top-level field names")


def present(payload, *, response_mode="compact", fields=None, preview_rows=20, max_response_bytes=16384,
            target=None, source=None, guard=None):
    validate_output(response_mode, fields, preview_rows, max_response_bytes)
    safe = safe_payload(payload)
    raw = json_bytes(safe)
    # Reserve space for final per-call telemetry added by the scenario decorator.
    budget = max_response_bytes - 512
    artifact, metadata = persist_result(safe, target=target, source=source, guard=guard)
    full = {**safe, "presentation": {"mode": "full", "truncated": False,
             "source_bytes": len(raw), "max_response_bytes": max_response_bytes, "artifact": artifact},
            "evidence": evidence(safe, safe, metadata, truncated=False)}
    if response_mode == "full" and len(json_bytes(full)) <= budget:
        return full
    changed = False

    def preview(value, key="", depth=0):
        nonlocal changed
        if depth > 8:
            changed = True
            return "<details in artifact>"
        if isinstance(value, str):
            if len(value) > 400:
                changed = True
                return value[:400] + "…"
            return value
        if isinstance(value, list):
            count = 0 if response_mode == "artifact" else preview_rows
            changed |= len(value) > count
            items = value[:count]
            if key in COLLECTIONS:
                selected = DEFAULT_FIELDS if fields is None else fields
                projected = []
                for item in items:
                    if isinstance(item, dict):
                        subset = {k: v for k, v in item.items() if k in selected}
                        changed |= len(subset) != len(item)
                        projected.append(subset)
                    else:
                        projected.append(item)
                items = projected
            return [preview(item, depth=depth + 1) for item in items]
        if isinstance(value, dict):
            keys = list(value)[:100]
            changed |= len(keys) != len(value)
            return {k: preview(value[k], k, depth + 1) for k in keys}
        return value

    result = preview(safe)
    presentation = {"mode": response_mode, "truncated": changed, "source_bytes": len(raw),
                    "max_response_bytes": max_response_bytes, "artifact": artifact,
                    "collection_counts": {k: len(v) for k, v in safe.items() if isinstance(v, list)}}
    if response_mode == "full":
        presentation["mode"] = "compact"
        presentation["requested_mode"] = "full"
        presentation["reason"] = "full_response_exceeds_byte_budget"
    if isinstance(safe.get("cache"), dict):
        presentation["cache_hit"] = safe["cache"].get("hit") is True
    result["presentation"] = presentation
    result["evidence"] = evidence(safe, result, metadata, truncated=changed)
    if len(json_bytes(result)) > budget:
        # Keep source completeness distinct from omitted presentation details.
        result = {k: safe[k] for k in ("complete", "complete_within_snapshot", "readonly", "loaded", "total",
                    "truncated", "delivery_verified", "retention_start_verified") if k in safe}
        presentation["truncated"] = True
        presentation["preview_omitted"] = True
        result["presentation"] = presentation
        result["evidence"] = evidence(safe, result, metadata, truncated=True)
    if len(json_bytes(result)) > budget:
        raise ValueError("Artifact receipt exceeds output budget")
    return result
