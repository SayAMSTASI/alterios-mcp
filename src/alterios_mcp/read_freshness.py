"""Exact-object evidence and opt-in pre-write optimistic freshness checks."""
from datetime import datetime, timezone

from .read_evidence import load_result, now
from .read_workflows import fingerprint
from .scoped_health import METHODS


def read_exact(client, kind, object_id):
    if kind not in METHODS or not isinstance(object_id, str) or not object_id.strip():
        raise ValueError("A supported kind and exact object_id are required")
    body = getattr(client, METHODS[kind])(object_id).body
    if not isinstance(body, dict) or (body.get("_id") or body.get("id")) != object_id:
        raise ValueError("Exact-object response has a different ID")
    if body.get("projectId") and body["projectId"] != client.config.project_id:
        raise ValueError("Exact-object response belongs to a different project")
    return body


def source_guard(client, kind, object_id):
    body = read_exact(client, kind, object_id)
    return body, {"kind": kind, "object_id": object_id, "fingerprint": fingerprint(body), "observed_at": now()}


def check_freshness(client, result_id, *, expected_kind=None, expected_id=None, max_age_seconds=300, _include_object=False):
    if not 1 <= max_age_seconds <= 3600:
        raise ValueError("max_age_seconds must be 1..3600")
    _, meta = load_result(result_id, profile=client.config.profile, project_id=client.config.project_id)
    guard = meta.get("guard")
    if not isinstance(guard, dict) or guard.get("kind") not in METHODS or not guard.get("object_id"):
        raise ValueError("This result contains no exact-object write evidence; use alterios_read_object_evidence")
    if expected_kind is not None and (guard["kind"] != expected_kind or guard["object_id"] != expected_id):
        raise ValueError("Read evidence does not match the object being written")
    observed = datetime.fromisoformat(guard["observed_at"].replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - observed).total_seconds()
    if age < 0 or age > max_age_seconds:
        return {"ok": False, "status": "expired", "result_id": result_id, "age_seconds": round(age, 3),
                "live_rechecked": False, "action": "Read a new exact-object result and review the change again"}
    fresh = read_exact(client, guard["kind"], guard["object_id"])
    matches = fingerprint(fresh) == guard["fingerprint"]
    result = {"ok": matches, "status": "unchanged" if matches else "changed", "result_id": result_id,
            "age_seconds": round(age, 3), "live_rechecked": True, "checked_at": now(),
            "kind": guard["kind"], "object_id": guard["object_id"],
            "atomic_server_precondition": False,
            "limitation": "A new change between this read and the write is still possible without server-side conditional writes"}
    if _include_object:
        result["_object"] = fresh
    return result


def guarded_existing(client, result_id, *, kind, existing):
    if result_id is None:
        return existing
    if not existing or not existing.get("_id"):
        raise ValueError("Read evidence requires an existing exact object")
    result = check_freshness(client, result_id, expected_kind=kind, expected_id=existing["_id"], _include_object=True)
    if not result["ok"]:
        raise ValueError("Read evidence is " + result["status"] + "; reread and review before writing")
    return result["_object"]


def assert_read_freshness(client, result_id, *, kind, object_id):
    if result_id is None:
        return None
    if not object_id:
        raise ValueError("Read evidence applies to an existing exact object, not an unverified create")
    result = check_freshness(client, result_id, expected_kind=kind, expected_id=object_id)
    if not result["ok"]:
        raise ValueError("Read evidence is " + result["status"] + "; reread and review before writing")
    return result
