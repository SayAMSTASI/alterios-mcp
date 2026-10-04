"""Target-bound result receipts, explicit coverage and bounded JSON-pointer reads."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone

from .performance import json_bytes
from .read_workflows import safe_payload
from .write_plan import artifact_root

MAX_RESULT_BYTES = 100 * 1024 * 1024
EVIDENCE_VERSION = 1


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def persist_result(payload, *, target=None, source=None, guard=None):
    raw = json_bytes(payload)
    if len(raw) > MAX_RESULT_BYTES:
        raise ValueError("Result exceeds 100 MiB; narrow the read scope")
    result_id = "result_" + uuid.uuid4().hex
    root = artifact_root() / "read-results"
    root.mkdir(parents=True, exist_ok=True)
    path = root / (result_id + ".json")
    digest = hashlib.sha256(raw).hexdigest()
    meta = {"schema_version": EVIDENCE_VERSION, "result_id": result_id, "created_at": now(),
            "target": target, "source": safe_payload(source) if source else {"mode": "unknown", "observed_at": None},
            "sha256": digest, "bytes": len(raw), "guard": guard}
    meta_raw = json_bytes(meta)
    if len(meta_raw) > 65536:
        raise ValueError("Result metadata exceeds budget; narrow the read scope")
    with path.open("xb") as stream:
        stream.write(raw)
    with path.with_suffix(".meta.json").open("xb") as stream:
        stream.write(meta_raw)
    return {"result_id": result_id, "path": str(path), "sha256": digest, "bytes": len(raw)}, meta


def load_result(result_id, *, profile, project_id):
    if not profile or not project_id or not re.fullmatch(r"result_[0-9a-f]{32}", result_id):
        raise ValueError("A valid result_id and explicit target are required")
    root = (artifact_root() / "read-results").resolve()
    data_path = root / (result_id + ".json")
    meta_path = root / (result_id + ".meta.json")
    for path in (data_path, meta_path):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("Result path escapes the private result store")
    with meta_path.open("rb") as stream:
        meta_raw = stream.read(65537)
    if len(meta_raw) > 65536:
        raise ValueError("Result metadata exceeds budget")
    meta = json.loads(meta_raw)
    if meta.get("result_id") != result_id or meta.get("target") != {"profile": profile, "project_id": project_id}:
        raise ValueError("Result does not belong to the explicit profile/project")
    with data_path.open("rb") as stream:
        raw = stream.read(MAX_RESULT_BYTES + 1)
    if len(raw) > MAX_RESULT_BYTES or len(raw) != meta.get("bytes") or hashlib.sha256(raw).hexdigest() != meta.get("sha256"):
        raise ValueError("Result integrity check failed")
    return json.loads(raw), meta


def pointer_tokens(pointer):
    if pointer == "":
        return []
    if len(pointer) > 2048 or not pointer.startswith("/") or re.search(r"~(?![01])", pointer):
        raise ValueError("Use a valid RFC 6901 JSON pointer")
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]


def escape(value):
    return str(value).replace("~", "~0").replace("/", "~1")


def locate(value, pointer):
    found, value, _ = locate_state(value, pointer)
    return found, value


def locate_state(value, pointer):
    for token in pointer_tokens(pointer):
        if isinstance(value, dict) and token in value:
            value = value[token]
        elif isinstance(value, list) and re.fullmatch(r"0|[1-9][0-9]*", token) and int(token) < len(value):
            value = value[int(token)]
        else:
            if isinstance(value, str) and "<redacted>" in value:
                return False, None, "redacted_ancestor"
            if value is None:
                return False, None, "null_ancestor"
            return False, None, "path_absent_in_result" if isinstance(value, (dict, list)) else "non_container_ancestor"
    return True, value, "present"


def completeness(payload):
    for name in ("complete", "complete_within_snapshot", "complete_within_supported_scope"):
        if payload.get(name) is True:
            return "complete_within_scope"
        if payload.get(name) is False:
            return "incomplete"
    return "unknown"


def evidence(payload, preview, meta, *, truncated):
    collections = []
    def visit(value, pointer="", depth=0):
        if len(collections) >= 16 or depth > 2:
            return
        if isinstance(value, list):
            found, shown = locate(preview, pointer)
            count = len(shown) if found and isinstance(shown, list) else 0
            collections.append({"path": pointer, "available": len(value), "shown": count,
                                "omitted": max(0, len(value) - count)})
        elif isinstance(value, dict):
            for key, item in value.items():
                visit(item, pointer + "/" + escape(key), depth + 1)
    visit(payload)
    status = completeness(payload)
    return {"schema_version": EVIDENCE_VERSION, "result_id": meta["result_id"],
            "source": meta["source"], "target": meta["target"], "created_at": meta["created_at"],
            "coverage": {"status": status, "preview_reduced": truncated, "collections": collections,
                         "scanned_rows": payload.get("loaded"), "reported_total": payload.get("total"),
                         "global_absence_proven": False},
            "summary": {"basis": "deterministic_counts", "error_count": len(payload["errors"]) if isinstance(payload.get("errors"), list) else 0,
                        "failed_checks": sum(1 for check in payload.get("checks", []) if isinstance(check, dict) and check.get("ok") is False),
                        "claim_scope": "saved_result_only"},
            "read_back": {"tool": "alterios_read_result", "requires_explicit_target": True},
            "interpretation": "Preview omission is not absence. Counts describe this bounded result, not uninspected server data."}


def _state(value):
    if value is None:
        return "null"
    if isinstance(value, str) and "<redacted>" in value:
        return "redacted"
    if isinstance(value, (str, list, dict)) and not value:
        return "empty"
    return "present"


def read_result(result_id, *, profile, project_id, json_pointer="/rows", offset=0, limit=20, text_limit=4096,
                fields=None, object_ids=None, max_response_bytes=16384):
    if not 0 <= offset <= 100000000 or not 1 <= limit <= 100 or not 4096 <= max_response_bytes <= 262144:
        raise ValueError("Read-back limits outside bounds")
    if not 1 <= text_limit <= 8192:
        raise ValueError("text_limit must be between 1 and 8192")
    if fields is not None and (not isinstance(fields, list) or len(fields) > 32 or
            any(not isinstance(f, str) or not f or len(f) > 100 for f in fields)):
        raise ValueError("fields must be at most 32 literal names")
    if object_ids is not None and (not isinstance(object_ids, list) or not object_ids or len(object_ids) > 20 or
            any(not isinstance(i, str) or not i or len(i) > 256 for i in object_ids)):
        raise ValueError("object_ids must be 1..20 exact IDs")
    payload, meta = load_result(result_id, profile=profile, project_id=project_id)
    found, selected, selection_state = locate_state(payload, json_pointer)
    result = {"readonly": True, "result_id": result_id, "source": meta["source"], "target": meta["target"],
              "retrieval": "saved_result", "live_rechecked": False,
              "source_coverage": completeness(payload), "artifact_sha256": meta["sha256"], "items": [],
              "selection": {"path": json_pointer, "offset": offset, "status": selection_state,
                            "next_offset": None, "has_more": False, "global_absence_proven": False}}
    if not found:
        if len(json_bytes(result)) > max_response_bytes - 512:
            raise ValueError("Evidence envelope exceeds response budget")
        return result
    result["selection"]["value_state"] = _state(selected)
    if object_ids and not isinstance(selected, list):
        raise ValueError("object_ids requires an array pointer")
    if isinstance(selected, str):
        candidates = [(json_pointer, selected[offset:offset + text_limit], offset)] if offset < len(selected) else []
        total, step = len(selected), text_limit
        result["selection"]["unit"] = "characters"
    elif isinstance(selected, list):
        positions = [(i, row) for i, row in enumerate(selected) if not object_ids or
                     (isinstance(row, dict) and str(row.get("_id") or row.get("id") or row.get("object_id") or "") in object_ids)]
        total, step = len(positions), 1
        candidates = [(json_pointer + "/" + str(i), row, offset + j) for j, (i, row) in enumerate(positions[offset:offset + limit])]
        result["selection"]["unit"] = "matched_items" if object_ids else "items"
    else:
        if offset:
            raise ValueError("offset applies only to arrays and strings")
        total, step = 1, 1
        candidates = [(json_pointer, selected, 0)]
        result["selection"]["unit"] = "value"
    result["selection"]["available_in_result"] = total
    if not candidates:
        result["selection"]["status"] = ("offset_exhausted" if total else
            "empty_within_result" if completeness(payload) == "complete_within_scope" else
            "not_observed_in_partial_or_unknown_result")
    consumed = offset
    for pointer, value, position in candidates:
        states = None
        if fields is not None and isinstance(value, dict):
            states = {name: _state(value[name]) if name in value else "absent_in_saved_object" for name in fields}
            output = {name: value[name] for name in fields if name in value}
        else:
            output = value
        item = {"value": output, "value_state": _state(value),
                "evidence": {"result_id": result_id, "json_pointer": pointer}}
        if isinstance(value, dict):
            item["evidence"]["object_id"] = value.get("_id") or value.get("id") or value.get("object_id")
        if isinstance(selected, str):
            item["evidence"].update({"character_offset": position, "character_count": len(value)})
        if states is not None:
            item["field_states"] = states
        result["items"].append(item)
        if len(json_bytes(result)) > max_response_bytes - 1024:
            result["items"].pop()
            if not result["items"]:
                result["selection"].update({"status": "requires_narrower_selection", "blocked_item_path": pointer,
                    "available_fields": list(value)[:24] if isinstance(value, dict) else []})
            break
        consumed = position + (len(value) if isinstance(selected, str) else step)
    has_more = consumed < total
    result["selection"].update({"returned": len(result["items"]), "has_more": has_more,
        "next_offset": consumed if has_more and result["items"] else None})
    if len(json_bytes(result)) > max_response_bytes - 512:
        raise ValueError("Evidence envelope exceeds response budget")
    return result
